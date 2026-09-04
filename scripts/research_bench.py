#!/usr/bin/env python
"""Vector Prediction — research benchmark: TimesFM 2.5 vs 3.0 (КОНТУР B).

ВНУТРЕННЕЕ ИССЛЕДОВАНИЕ. Результаты — только для сравнения моделей.
Прогнозы 3.0 не должны попадать в производственные решения
(см. docs/license-compliance.md).

Сравнивает на одном ряде:
  - точечный прогноз 2.5 (базовый)
  - 2.5 + XReg (промо-ковариат)
  - 3.0 нативный ковариат (past_future_covariates)

Метрики: MAE на holdout (последние --holdout строк исключаются из контекста),
lift ковариата, тайминги.

Использование:
  python scripts/research_bench.py --input data/sample/history.csv \
      --date-col date --value-col sales --covariate-col promo --holdout 14
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd


def load_series(path: str, date_col: str, value_col: str, cov_col: str | None,
                holdout: int):
    df = pd.read_csv(path, parse_dates=[date_col]).sort_values(date_col)
    values = df[value_col].to_numpy(np.float32)
    cov = df[cov_col].to_numpy(np.float32) if cov_col else None
    train_v, actual = values[:-holdout], values[-holdout:]
    train_c, actual_c = (cov[:-holdout], cov[-holdout:]) if cov is not None else (None, None)
    return df, train_v, actual, train_c, actual_c


def mae(true, pred):
    return float(np.mean(np.abs(np.asarray(true) - np.asarray(pred))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--date-col", default="date")
    ap.add_argument("--value-col", default="sales")
    ap.add_argument("--covariate-col", default="promo")
    ap.add_argument("--holdout", type=int, default=14)
    args = ap.parse_args()

    import timesfm  # noqa: E402

    df, train_v, actual, train_c, actual_c = load_series(
        args.input, args.date_col, args.value_col, args.covariate_col, args.holdout)
    T, H = len(train_v), len(actual)
    print(f"контекст {T} точек, горизонт {H}, ряд {args.value_col}")

    results = {"input": args.input, "value_col": args.value_col,
               "context": int(T), "horizon": int(H), "runs": []}

    # --- 2.5 базовый ---
    m25 = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    m25.compile(timesfm.ForecastConfig(
        max_context=512, max_horizon=64, normalize_inputs=True,
        use_continuous_quantile_head=True, force_flip_invariance=True,
        infer_is_positive=True, fix_quantile_crossing=True))
    t0 = time.time()
    p25 = np.asarray(m25.forecast(horizon=H, inputs=[train_v])[0], dtype=np.float32).ravel()
    t25 = time.time() - t0
    results["runs"].append({"engine": "2.5-base", "mae": mae(actual, p25), "sec": round(t25, 3)})
    print(f"2.5 базовый:        MAE {mae(actual, p25):.4f}  ({t25:.2f}s)")

    # --- 2.5 + XReg ---
    if train_c is not None:
        m25c = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
        m25c.compile(timesfm.ForecastConfig(
            max_context=512, max_horizon=64, normalize_inputs=True,
            use_continuous_quantile_head=True, force_flip_invariance=True,
            infer_is_positive=True, fix_quantile_crossing=True, return_backcast=True))
        cov_full = np.concatenate([train_c,
                                   np.zeros(H, dtype=np.float32)]).astype(np.float32)
        t0 = time.time()
        p25x = m25c.forecast_with_covariates(
            inputs=[train_v], dynamic_numerical_covariates={"cov": [cov_full]},
            xreg_mode="xreg + timesfm")[0]
        t25x = time.time() - t0
        p25x = np.asarray(p25x[0], dtype=np.float32).ravel()
        if p25x.size != H:
            p25x = p25x[-H:]
        results["runs"].append({"engine": "2.5-xreg", "mae": mae(actual, p25x), "sec": round(t25x, 3)})
        print(f"2.5 + XReg:         MAE {mae(actual, p25x):.4f}  ({t25x:.2f}s)")

    # --- 3.0 базовый ---
    fc3 = timesfm.TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch", device="cpu")
    t0 = time.time()
    p30 = np.asarray(fc3.predict(context=train_v, horizon=H).forecast, dtype=np.float32)
    t30 = time.time() - t0
    results["runs"].append({"engine": "3.0-base", "mae": mae(actual, p30), "sec": round(t30, 3)})
    print(f"3.0 базовый:        MAE {mae(actual, p30):.4f}  ({t30:.2f}s)")

    # --- 3.0 нативный ковариат ---
    if train_c is not None:
        # будущие значения ковариата: факт holdout известен постфактум для оценки
        cov_full = np.concatenate([train_c, actual_c]).astype(np.float32)
        t0 = time.time()
        p30c = np.asarray(fc3.predict(context=train_v, horizon=H,
                                      past_future_covariates=cov_full[None, :]).forecast,
                          dtype=np.float32)
        t30c = time.time() - t0
        results["runs"].append({"engine": "3.0-cov", "mae": mae(actual, p30c), "sec": round(t30c, 3)})
        print(f"3.0 + ковариат:     MAE {mae(actual, p30c):.4f}  ({t30c:.2f}s)")

    results["compliance"] = ("Kontur B (research): results for internal model "
                             "comparison only — NOT for production decisions.")
    outdir = os.environ.get("VP_OUT", "out")
    os.makedirs(outdir, exist_ok=True)
    out_path = os.path.join(outdir, "research_bench.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nсохранено: {out_path}")
    print("ВАЖНО: контур B — только внутреннее сравнение моделей, не для прод-решений.")


if __name__ == "__main__":
    sys.exit(main())
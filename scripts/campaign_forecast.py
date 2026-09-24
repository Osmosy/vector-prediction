#!/usr/bin/env python
"""TimesFM Marketing Toolkit — прогноз кампаний, промо-эффект, аномалии.

Полный пайплайн для маркетинговых временных рядов на TimesFM 2.5 (CPU):
  CSV кампании → прогноз с интервалами → (опц.) промо-ковариат →
  аномалии в истории → PNG + CSV отчёт.

Использование:
  # базовый прогноз по колонке clicks, горизонт 14 дней
  python scripts/campaign_forecast.py --input data/sample/history.csv \
      --date-col date --value-cols clicks --horizon 14

  # с промо-календарём и с проверкой точности на holdout
  python scripts/campaign_forecast.py --input data/sample/history.csv \
      --date-col date --value-cols clicks,conversions --horizon 14 \
      --covariate-col promo --holdout 14 --outdir out

Вход:
  --input        CSV с колонкой дат и >=1 метрическими колонками
  --date-col     имя колонки даты (парсится pandas)
  --value-cols   через запятую: колонки-ряды (клики, конверсии, расход...)
  --horizon      горизонт прогноза (по умолчанию 14)
  --covariate-col
                 опционально: числовой ковариат (промо 0/1, праздники, цена).
                 План на будущее задаётся строками в конце CSV, где у всех
                 --value-cols пустые ячейки, а ковариат заполнен (склейка
                 history.csv + plan.csv). Если плана меньше, чем --horizon,
                 недостающие дни заполняются 0 («акций не запланировано»).
  --holdout N    отрезать последние N точек истории, замерить MAE/RMSE/MAPE и
                 покрытие 80% PI (по умолчанию 0 — прогноз от конца истории).
                 Требует --horizon >= N. Ковариат на отрезанные дни берётся из
                 CSV: план акций на эти дни был известен заранее.
  --outdir       каталог для результатов (по умолчанию ./forecast_out)

Выход (в outdir, по колонке):
  <col>_forecast.csv     date, forecast, lower_60, upper_60, lower_80, upper_80
                         (+ actual при --holdout, + ковариат при --covariate-col).
                         Даты идут сразу после последней точки контекста.
  <col>_forecast.png     история + прогноз + 80% интервал
  <col>_anomalies.csv    последние 60 точек контекста с флагами OK/WARNING/CRITICAL
                         (факт вне 60%/80% интервала одношагового бэккаста)
  metrics.json           тайминги и (если --holdout) метрики точности

Требования: venv с timesfm[torch,xreg]; минимум 32 точки истории на ряд.
Веса ~800 МБ кэшируются в ~/.cache/huggingface при первом запуске.
"""
import argparse
import json
import os
import sys
import time

import matplotlib

matplotlib.use("Agg")  # headless — до импорта pyplot
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import timesfm

IDX_Q10, IDX_Q20, IDX_Q80, IDX_Q90 = 1, 2, 8, 9  # квантильные индексы (0 = mean!)
MIN_CONTEXT = 32  # минимум модели
ANOMALY_TAIL = 60  # сколько последних точек контекста размечать


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="TimesFM: прогноз маркетинговых метрик")
    p.add_argument("--input", required=True, help="CSV с датой и метриками")
    p.add_argument("--date-col", default="date", help="имя колонки даты")
    p.add_argument("--value-cols", required=True,
                   help="колонки-ряды через запятую, напр. clicks,conversions")
    p.add_argument("--horizon", type=int, default=14, help="горизонт прогноза")
    p.add_argument("--covariate-col", default=None,
                   help="опционально: колонка ковариата (промо 0/1, расходы)")
    p.add_argument("--holdout", type=int, default=0,
                   help="N последних точек для замера точности")
    p.add_argument("--outdir", default="forecast_out")
    p.add_argument("--batch-size", type=int, default=8,
                   help="per_core_batch_size (меньше при нехватке RAM)")
    args = p.parse_args(argv)
    if args.horizon < 1:
        p.error("--horizon должен быть >= 1")
    if args.holdout < 0:
        p.error("--holdout не может быть отрицательным")
    if args.holdout > args.horizon:
        p.error(f"--holdout {args.holdout} больше --horizon {args.horizon}: "
                f"прогноз не покроет отрезанные точки")
    return args


def load_csv(args):
    """Возвращает (history, plan, cols): history — строки с фактом, plan — хвост
    CSV без факта (только ковариат на будущие дни)."""
    if not os.path.exists(args.input):
        sys.exit(f"нет файла: {args.input}")
    df = pd.read_csv(args.input)
    cols = [c.strip() for c in args.value_cols.split(",")]
    missing = [c for c in [args.date_col] + cols + ([args.covariate_col] if args.covariate_col else [])
               if c not in df.columns]
    if missing:
        sys.exit(f"нет колонок {missing}; есть: {list(df.columns)}")
    df[args.date_col] = pd.to_datetime(df[args.date_col])
    df = df.sort_values(args.date_col).reset_index(drop=True)

    # План — хвостовые строки, где нет ни одного факта. Их нельзя интерполировать
    # как историю: это будущее, известное только по ковариату.
    has_fact = df[cols].notna().any(axis=1).to_numpy()
    if not has_fact.any():
        sys.exit(f"в колонках {cols} нет ни одного значения")
    last_fact = int(np.flatnonzero(has_fact)[-1])
    history = df.iloc[:last_fact + 1].reset_index(drop=True)
    plan = df.iloc[last_fact + 1:].reset_index(drop=True)

    if len(history) < MIN_CONTEXT + args.holdout:
        sys.exit(f"слишком мало точек: {len(history)} < {MIN_CONTEXT}+{args.holdout}. "
                 f"TimesFM требует контекст >= {MIN_CONTEXT}.")
    for c in cols:
        n_nan = history[c].isna().sum()
        if n_nan:
            print(f"[warn] {c}: {n_nan} NaN — заполнены интерполяцией")
            history[c] = history[c].interpolate().ffill().bfill()
    if args.covariate_col:
        for part, name in ((history, "истории"), (plan, "плане")):
            n_nan = part[args.covariate_col].isna().sum()
            if n_nan:
                print(f"[warn] {args.covariate_col}: {n_nan} пустых в {name} — заполнены 0")
                part[args.covariate_col] = part[args.covariate_col].fillna(0)
    elif len(plan):
        print(f"[warn] {len(plan)} строк без факта в конце CSV пропущены: "
              f"ковариат не задан (--covariate-col)")
    return history, plan, cols


def future_dates(history, date_col, start_idx, horizon):
    """Даты горизонта: сразу после точки start_idx-1, шаг — как в истории."""
    dates = history[date_col]
    freq = pd.infer_freq(dates) if len(dates) >= 3 else None
    anchor = dates.iloc[start_idx - 1]
    return pd.date_range(anchor, periods=horizon + 1, freq=freq or "D")[1:]


def build_model(args):
    t0 = time.time()
    model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
    model.compile(timesfm.ForecastConfig(
        max_context=512,
        max_horizon=max(32, args.horizon),
        per_core_batch_size=args.batch_size,
        normalize_inputs=True,
        use_continuous_quantile_head=True,
        fix_quantile_crossing=True,
        # backcast нужен и XReg, и разметке аномалий в истории
        return_backcast=True,
    ))
    return model, time.time() - t0


def forecast(model, values, horizon, cov_full=None):
    """Прогноз на horizon шагов: (point (1, H), quant (1, H, 10), backcast_quant, сек).

    С return_backcast=True `model.forecast` отдаёт бэккаст + горизонт; горизонт —
    хвост. `forecast_with_covariates` отдаёт только горизонт, поэтому бэккаст для
    аномалий берём всегда из базового прогона.
    """
    t0 = time.time()
    base_point, base_quant = model.forecast(horizon=horizon, inputs=[values])
    base_point, base_quant = np.asarray(base_point), np.asarray(base_quant)
    point, quant = base_point[:, -horizon:], base_quant[:, -horizon:, :]
    backcast = base_quant[:, :-horizon, :]
    if cov_full is not None:
        p, q = model.forecast_with_covariates(
            inputs=[values],
            dynamic_numerical_covariates={"cov": [cov_full]},
            xreg_mode="xreg + timesfm",
        )
        point = np.asarray(p[0])[None, :horizon]
        quant = np.asarray(q[0])[None, :horizon, :]
    return point, quant, backcast, time.time() - t0


def detect_anomalies(values, backcast, tail=ANOMALY_TAIL):
    """Аномалии в истории: факт вне 60%/80% интервала одношагового бэккаста.

    Бэккаст выровнен по концу контекста (последняя его точка — прогноз на
    последний факт), но короче контекста на один патч, поэтому берём хвост.
    """
    q = backcast[0]
    n = min(len(values), q.shape[0], tail)
    q = q[-n:]
    actual = values[-n:]
    lower80, upper80 = q[:, IDX_Q10], q[:, IDX_Q90]
    lower60, upper60 = q[:, IDX_Q20], q[:, IDX_Q80]
    sev = np.where((actual < lower80) | (actual > upper80), "CRITICAL",
          np.where((actual < lower60) | (actual > upper60), "WARNING", "OK"))
    return pd.DataFrame({
        "idx": np.arange(len(values) - n, len(values)),
        "actual": actual,
        "lower_80": lower80, "upper_80": upper80,
        "severity": sev,
    })


def main(argv=None):
    args = parse_args(argv)
    os.makedirs(args.outdir, exist_ok=True)
    history, plan, cols = load_csv(args)
    n_train = len(history) - args.holdout
    dates = future_dates(history, args.date_col, n_train, args.horizon)

    metrics = {"model": "google/timesfm-2.5-200m-pytorch", "backend": "cpu"}
    model, t_load = build_model(args)
    metrics["load_s"] = round(t_load, 2)

    # ковариат: контекст + горизонт. Горизонт = отрезанный holdout (план на эти
    # дни известен из CSV) + строки плана; недостающее будущее = 0.
    with_cov = args.covariate_col is not None
    cov_full = None
    if with_cov:
        known = np.concatenate([
            history[args.covariate_col].to_numpy(np.float32),
            plan[args.covariate_col].to_numpy(np.float32),
        ])
        need = n_train + args.horizon
        if len(known) < need:
            print(f"[warn] план ковариата покрывает {len(known) - n_train} из "
                  f"{args.horizon} шагов горизонта — остальные заполнены 0")
        cov_full = np.zeros(need, dtype=np.float32)
        cov_full[:min(need, len(known))] = known[:need]
        metrics["covariate"] = args.covariate_col

    for col in cols:
        values = history[col].to_numpy(np.float32)
        train = values[:n_train]

        point, quant, backcast, t_fc = forecast(model, train, args.horizon, cov_full)

        out = {
            "date": dates,
            "forecast": point[0],
            "lower_60": quant[0, :, IDX_Q20],
            "upper_60": quant[0, :, IDX_Q80],
            "lower_80": quant[0, :, IDX_Q10],
            "upper_80": quant[0, :, IDX_Q90],
        }

        # holdout-метрики: первые N шагов прогноза против отрезанного факта
        if args.holdout:
            actual = values[n_train:]
            pred = point[0, :args.holdout]
            mae = float(np.mean(np.abs(actual - pred)))
            rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
            mape = float(np.mean(np.abs((actual - pred) / np.maximum(actual, 1))) * 100)
            lo, hi = quant[0, :args.holdout, IDX_Q10], quant[0, :args.holdout, IDX_Q90]
            cov80 = float(np.mean((actual >= lo) & (actual <= hi)) * 100)
            metrics[col] = {"MAE": round(mae, 1), "RMSE": round(rmse, 1),
                            "MAPE_%": round(mape, 1), "PI80_coverage_%": round(cov80, 1)}
            out["actual"] = np.concatenate(
                [actual, np.full(args.horizon - args.holdout, np.nan)])
        if with_cov:
            out[args.covariate_col] = cov_full[n_train:]

        pd.DataFrame(out).to_csv(os.path.join(args.outdir, f"{col}_forecast.csv"), index=False)

        plot_path = os.path.join(args.outdir, f"{col}_forecast.png")
        tail = history.tail(min(len(history), 90))
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(tail[args.date_col], tail[col], label="История", color="#2b6cb0")
        ax.plot(dates, point[0], label="Прогноз", color="#dd6b20")
        ax.fill_between(dates, quant[0, :, IDX_Q10], quant[0, :, IDX_Q90],
                        alpha=0.2, color="#dd6b20", label="80% интервал")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.legend()
        ax.set_title(f"{col}: прогноз на {args.horizon} шагов (TimesFM 2.5, CPU)")
        fig.tight_layout()
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)

        # аномалии в истории (контекст прогноза, без holdout)
        anom = detect_anomalies(train, backcast)
        anom.insert(1, args.date_col, history[args.date_col].iloc[anom["idx"]].to_numpy())
        anom.to_csv(os.path.join(args.outdir, f"{col}_anomalies.csv"), index=False)
        metrics.setdefault("anomalies", {})[col] = int((anom["severity"] == "CRITICAL").sum())

        print(f"[{col}] прогноз {t_fc*1000:.0f} ms → {col}_forecast.csv/.png, {col}_anomalies.csv")

    with open(os.path.join(args.outdir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"метрики → {args.outdir}/metrics.json: {json.dumps(metrics, ensure_ascii=False)}")


if __name__ == "__main__":
    main()

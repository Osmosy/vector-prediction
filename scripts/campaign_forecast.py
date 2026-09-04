#!/usr/bin/env python
"""TimesFM Marketing Toolkit — прогноз кампаний, промо-эффект, аномалии.

Полный пайплайн для маркетинговых временных рядов на TimesFM 2.5 (CPU):
  CSV кампании → прогноз с интервалами → (опц.) промо-ковариат →
  аномалии в истории → PNG + CSV отчёт.

Использование:
  # базовый прогноз по колонке clicks, горизонт 14 дней
  python campaign_forecast.py --input campaign.csv --date-col date \
      --value-cols clicks --horizon 14

  # с промо-календарём (колонка promo: 0/1, должна покрывать контекст+горизонт)
  # и с проверкой точности на holdout
  python campaign_forecast.py --input campaign.csv --date-col date \
      --value-cols clicks,conversions --horizon 14 --covariate-col promo \
      --holdout 14 --outdir out

Вход:
  --input        CSV с колонкой дат и >=1 метрическими колонками
  --date-col     имя колонки даты (парсится pandas)
  --value-cols   через запятую: колонки-ряды (клики, конверсии, расход...)
  --horizon      горизонт прогноза (по умолчанию 14)
  --covariate-col
                 опционально: бинарный/числовой ковариат (промо, праздники).
                 Должен иметь значения для ВСЕЙ истории + горизонта. Если в
                 CSV меньше строк, чем контекст+горизонт, будущие значения
                 заполняются последним известным (для бинарного промо — 0:
                 «акций не запланировано»).
  --holdout N    отрезать последние N точек, замерить MAE/RMSE/MAPE и
                 покрытие 80% PI (по умолчанию 0 — прогноз на всём хвосте)
  --outdir       каталог для результатов (по умолчанию ./forecast_out)

Выход (в outdir, по колонке):
  <col>_forecast.csv     date, forecast, lower_80, upper_80, lower_60, upper_60
  <col>_forecast.png     история + прогноз + 80% интервал
  <col>_anomalies.csv    последние 60 фактических точек с флагами WARNING/CRITICAL
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
    return p.parse_args(argv)


def load_csv(args):
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
    if len(df) < MIN_CONTEXT + args.holdout:
        sys.exit(f"слишком мало точек: {len(df)} < {MIN_CONTEXT}+{args.holdout}. "
                 f"TimesFM требует контекст >= {MIN_CONTEXT}.")
    for c in cols:
        n_nan = df[c].isna().sum()
        if n_nan:
            print(f"[warn] {c}: {n_nan} NaN — заполнены интерполяцией")
            df[c] = df[c].interpolate().ffill().bfill()
    return df, cols


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
        return_backcast=args.covariate_col is not None,  # XReg требует backcast
    ))
    return model, time.time() - t0


def forecast(args, model, values, promo_full=None):
    """values: 1-D массив; promo_full: массив контекст+горизонт или None.
    Возвращает (point, quant, elapsed): numpy-массивы в любом случае."""
    if promo_full is None:
        t0 = time.time()
        point, quant = model.forecast(horizon=args.horizon, inputs=[values])
    else:
        t0 = time.time()
        point, quant = model.forecast_with_covariates(
            inputs=[values],
            dynamic_categorical_covariates={"promo": [promo_full]},
            xreg_mode="xreg + timesfm",
        )
    point = np.asarray(point)
    quant = np.asarray(quant)
    if point.ndim == 2 and point.shape[0] == 1:
        pass
    else:
        point = np.atleast_2d(point)
        quant = np.asarray(quant)
        if quant.ndim == 3 and quant.shape[0] != 1:
            quant = quant[:1]
    return point, quant, time.time() - t0


def slice_horizon(point, quant, args, with_cov):
    """XReg+backcast возвращает контекст+горизонт — отрезаем хвост."""
    if with_cov and point.shape[1] > args.horizon:
        return point[:, -args.horizon:], quant[:, -args.horizon:, :]
    return point, quant


def detect_anomalies(values, quant_full, backcast):
    """Аномалии в истории: факт вне 80%/90% PI бэккаста."""
    n = len(values)
    q = quant_full[0]  # (n_points, 10)
    if q.shape[0] < n:  # backcast короче истории — берём хвост
        offset = n - q.shape[0]
    else:
        offset = q.shape[0] - n
        q = q[-n:]
    actual = values[-q.shape[0]:]
    lower80, upper80 = q[:, IDX_Q10], q[:, IDX_Q90]
    lower60, upper60 = q[:, IDX_Q20], q[:, IDX_Q80]
    sev = np.where((actual < lower80) | (actual > upper80), "CRITICAL",
          np.where((actual < lower60) | (actual > upper60), "WARNING", "OK"))
    return pd.DataFrame({
        "idx": np.arange(offset, n),
        "actual": actual,
        "lower_80": lower80, "upper_80": upper80,
        "severity": sev,
    })


def plot_forecast(df, col, point, quant, future_dates, path):
    fig, ax = plt.subplots(figsize=(12, 5))
    tail = df.tail(min(len(df), 90))
    ax.plot(tail[args_date_col], tail[col], label="История", color="#2b6cb0")
    ax.plot(future_dates, point[0], label="Прогноз", color="#dd6b20")
    ax.fill_between(future_dates, quant[0, :, IDX_Q10], quant[0, :, IDX_Q90],
                    alpha=0.2, color="#dd6b20", label="80% интервал")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.legend()
    ax.set_title(f"Прогноз {col} на {len(future_dates)} шагов (TimesFM 2.5)")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None):
    global args_date_col
    args = parse_args(argv)
    args_date_col = args.date_col
    os.makedirs(args.outdir, exist_ok=True)
    df, cols = load_csv(args)

    metrics = {"model": "google/timesfm-2.5-200m-pytorch", "backend": "cpu"}
    model, t_load = build_model(args)
    metrics["load_s"] = round(t_load, 2)

    # ковариат: контекст+горизонт; недостающее будущее = 0 (промо не запланировано)
    with_cov = args.covariate_col is not None
    promo_full = None
    if with_cov:
        cov = df[args.covariate_col].values.astype(np.float32)
        need = len(cov) - args.holdout + args.horizon
        promo_full = np.zeros(need, dtype=np.float32)
        promo_full[:len(cov) - args.holdout] = cov[:len(cov) - args.holdout]
        # будущие значения ковариата берём из «плана» — доп. строк CSV нет,
        # поэтому по умолчанию 0 (нет акций). Для планового промо расширьте CSV.

    for col in cols:
        values = df[col].values.astype(np.float32)
        train = values[:len(values) - args.holdout] if args.holdout else values

        point, quant, t_fc = forecast(args, model, train, promo_full)
        if with_cov and point.shape[1] > args.horizon:
            point, quant = point[:, -args.horizon:], quant[:, -args.horizon:, :]

        # holdout-метрики
        if args.holdout:
            actual = values[-args.holdout:]
            pred = point[0, -args.holdout:] if point.shape[1] >= args.holdout else point[0]
            mae = float(np.mean(np.abs(actual - pred)))
            rmse = float(np.sqrt(np.mean((actual - pred) ** 2)))
            mape = float(np.mean(np.abs((actual - pred) / np.maximum(actual, 1))) * 100)
            lo, hi = quant[0, -args.holdout:, IDX_Q10], quant[0, -args.holdout:, IDX_Q90]
            cov80 = float(np.mean((actual >= lo) & (actual <= hi)) * 100)
            metrics[col] = {"MAE": round(mae, 1), "RMSE": round(rmse, 1),
                            "MAPE_%": round(mape, 1), "PI80_coverage_%": round(cov80, 1)}

        # forecast.csv — прогноз на будущее
        future_dates = pd.date_range(df[args.date_col].iloc[-1],
                                     periods=args.horizon + 1, freq="D")[1:]
        pd.DataFrame({
            "date": future_dates,
            "forecast": point[0, :args.horizon],
            "lower_60": quant[0, :args.horizon, IDX_Q20],
            "upper_60": quant[0, :args.horizon, IDX_Q80],
            "lower_80": quant[0, :args.horizon, IDX_Q10],
            "upper_80": quant[0, :args.horizon, IDX_Q90],
        }).to_csv(os.path.join(args.outdir, f"{col}_forecast.csv"), index=False)

        plot_path = os.path.join(args.outdir, f"{col}_forecast.png")
        tail = df.tail(min(len(df), 90))
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(tail[args.date_col], tail[col], label="История", color="#2b6cb0")
        ax.plot(future_dates, point[0, :args.horizon], label="Прогноз", color="#dd6b20")
        ax.fill_between(future_dates, quant[0, :args.horizon, IDX_Q10],
                        quant[0, :args.horizon, IDX_Q90],
                        alpha=0.2, color="#dd6b20", label="80% интервал")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.legend()
        ax.set_title(f"{col}: прогноз на {args.horizon} шагов (TimesFM 2.5, CPU)")
        fig.tight_layout()
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)

        # аномалии в истории (только при with_cov: есть backcast)
        if with_cov and quant.shape[1] >= len(df) - args.holdout:
            anom = detect_anomalies(train, quant, None)
            anom = anom.merge(df[[args.date_col]], left_on="idx", right_index=True)
            anom.to_csv(os.path.join(args.outdir, f"{col}_anomalies.csv"), index=False)
            n_crit = int((anom["severity"] == "CRITICAL").sum())
            metrics.setdefault("anomalies", {})[col] = n_crit

        print(f"[{col}] прогноз {t_fc*1000:.0f} ms → {col}_forecast.csv/.png")

    with open(os.path.join(args.outdir, "metrics.json"), "w") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"метрики → {args.outdir}/metrics.json: {json.dumps(metrics, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python
"""Пилотный прогон TimesFM 2.5: прогноз campaign-метрик с промо-эффектом.

Синтетические данные: ежедневные клики/конверсии маркетинговой кампании
(90 дней истории), сезонность по дням недели + тренд + промо-подъёмы.
Проверяем: (1) скорость прогноза на CPU, (2) ловит ли модель промо-эффект
через dynamic covariates, (3) аномалии по квантильным интервалам.
"""
import time
import numpy as np
import timesfm

rng = np.random.default_rng(42)
N = 90  # дней истории
days = np.arange(N)

# --- синтетическая campaign-метрика: клики по дням ---
weekday_effect = np.array([0.9, 1.0, 1.05, 1.1, 1.2, 1.3, 1.1])  # пн..вс
trend = 1000 * (1 + 0.002 * days)
seasonal = weekday_effect[days % 7]
# промо-акции: 3 всплеска по 3 дня в истории, +40%
promo_hist = np.zeros(N)
for start in (20, 45, 70):
    promo_hist[start:start + 3] = 1
promo_lift = promo_hist * 0.4
noise = rng.normal(0, 40, N)
clicks = (trend * seasonal * (1 + promo_lift) + noise).astype(np.float32)

# будущий горизонт: 14 дней, промо запланировано на дни 95-97 (+40%)
H = 14
future_promo = np.zeros(H)
future_promo[5:8] = 1  # дни 95-97 от начала

# --- модель ---
t0 = time.time()
model = timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")
t_load = time.time() - t0

t0 = time.time()
model.compile(timesfm.ForecastConfig(
    max_context=128,
    max_horizon=32,
    per_core_batch_size=8,
    normalize_inputs=True,
    use_continuous_quantile_head=True,
    fix_quantile_crossing=True,
    return_backcast=True,
))
t_compile = time.time() - t0

# --- 1) базовый прогноз без ковариат ---
t0 = time.time()
point, quant = model.forecast(horizon=H, inputs=[clicks])
t_base = time.time() - t0

# --- 2) прогноз с промо-ковариатом (динамическая категориальная) ---
# ковариат должен покрывать контекст + горизонт
promo_full = np.concatenate([promo_hist, future_promo]).astype(np.float32)
t0 = time.time()
try:
    point_x, quant_x = model.forecast_with_covariates(
        inputs=[clicks],
        dynamic_categorical_covariates={"promo": [promo_full]},
        xreg_mode="xreg + timesfm",
    )
    t_cov = time.time() - t0
    has_xreg = True
except Exception as e:
    print(f"XReg недоступен: {type(e).__name__}: {e}")
    t_cov = 0.0
    has_xreg = False

# --- отчёт ---
print(f"\n=== Тайминги (CPU, 20 ядер) ===")
print(f"load:    {t_load:6.1f}s")
print(f"compile: {t_compile:6.1f}s")
print(f"базовый прогноз {H} шагов: {t_base*1000:.0f} ms")
if has_xreg:
    print(f"прогноз с ковариатами:  {t_cov*1000:.0f} ms")

print(f"\n=== Базовый прогноз (без промо-календаря) ===")
print(f"point shape: {point.shape}, quantiles shape: {quant.shape}")
for d in range(H):
    bar = "#" * int(max(0, (point[0, d] - 700) / 15))
    print(f"день {N+d+1:3d}: {point[0, d]:7.0f} [{quant[0,d,1]:6.0f}..{quant[0,d,9]:6.0f}] {bar}")

if has_xreg:
    print(f"\n=== Прогноз с промо-ковариатом ===")
    lift_days = [5, 6, 7]
    base_avg = np.mean(point[0])
    xreg_avg_promo = np.mean(point_x[0][lift_days])
    xreg_avg_norm = np.mean(np.delete(point_x[0], lift_days))
    print(f"среднее в дни промо:     {xreg_avg_promo:7.0f}")
    print(f"среднее вне промо:       {xreg_avg_norm:7.0f}")
    print(f"подъём в промо-дни:      {(xreg_avg_promo/xreg_avg_norm-1)*100:+.1f}% (ожидалось ~+35-40%)")
    print(f"базовый (без ковариат) в те же дни: {np.mean(point[0][lift_days]):7.0f} — промо НЕ видит")

np.save("/tmp/timesfm_pilot_point.npy", point)
np.save("/tmp/timesfm_pilot_quant.npy", quant)
print("\nOK — /tmp/timesfm_pilot_point.npy сохранён")
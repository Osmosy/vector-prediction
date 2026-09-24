"""Заглушка timesfm для тестов логики скриптов (без torch и весов).

Повторяет контракт timesfm 3.0.1, на котором ломались скрипты:

- `forecast()` при `return_backcast=True` отдаёт бэккаст + горизонт; бэккаст
  длиной max_context - 32 выровнен по концу контекста (последняя точка —
  прогноз на последний факт), как у TimesFM_2p5_200M_torch;
- `forecast_with_covariates()` отдаёт только горизонт (списки массивов) и
  требует return_backcast.

Числа детерминированные и простые, чтобы тесты проверяли выравнивание:
прогноз = среднее последних 7 точек, бэккаст = наивный (предыдущая точка),
ковариат добавляет +100 за единицу.
"""
from __future__ import annotations

import numpy as np

PATCH = 32
COV_EFFECT = 100.0


class ForecastConfig:
    def __init__(self, **kw):
        self.max_context = kw.get("max_context", 512)
        self.max_horizon = kw.get("max_horizon", 128)
        self.return_backcast = kw.get("return_backcast", False)
        self.__dict__.update(kw)


def _quantiles(point: np.ndarray, spread: float) -> np.ndarray:
    # индекс 0 — среднее, 1..9 — квантили 10..90%
    offs = np.array([0, -1.28, -0.84, -0.52, -0.25, 0, 0.25, 0.52, 0.84, 1.28])
    return point[..., None] + spread * offs


class TimesFM_2p5_200M_torch:
    def __init__(self):
        self.cfg: ForecastConfig | None = None

    @classmethod
    def from_pretrained(cls, name: str):
        assert name == "google/timesfm-2.5-200m-pytorch", name
        return cls()

    def compile(self, cfg: ForecastConfig) -> None:
        self.cfg = cfg

    def forecast(self, horizon: int, inputs):
        assert self.cfg is not None, "compile() first"
        points, quants = [], []
        for x in inputs:
            x = np.asarray(x, dtype=np.float64)[-self.cfg.max_context:]
            spread = float(np.std(np.diff(x))) or 1.0
            point = np.full(horizon, x[-7:].mean())
            if self.cfg.return_backcast:
                padded = np.concatenate([np.zeros(self.cfg.max_context - len(x)), x])
                # бэккаст[j] — прогноз на позицию j + PATCH паддинга: предыдущая точка
                back = padded[PATCH - 1:-1]
                point = np.concatenate([back, point])
            points.append(point)
            quants.append(_quantiles(point, spread))
        return np.stack(points), np.stack(quants)

    def forecast_with_covariates(self, inputs, dynamic_numerical_covariates=None,
                                 dynamic_categorical_covariates=None, xreg_mode="xreg + timesfm", **_):
        assert self.cfg is not None and self.cfg.return_backcast, "XReg требует return_backcast"
        covs = dynamic_numerical_covariates or dynamic_categorical_covariates
        (cov_list,) = covs.values()
        points, quants = [], []
        for x, cov in zip(inputs, cov_list):
            cov = np.asarray(cov, dtype=np.float64)
            h = len(cov) - len(x)
            assert 0 < h <= self.cfg.max_horizon, h
            base, _ = self.forecast(h, [x])
            point = base[0, -h:] + COV_EFFECT * cov[len(x):]
            points.append(point)
            quants.append(_quantiles(point, float(np.std(np.diff(x))) or 1.0))
        return points, quants

#!/usr/bin/env python3
"""Тесты логики прогнозных скриптов на заглушке timesfm (tests/fake_timesfm).

Каждый тест — дефект, найденный при аудите 24.09.2026 прогоном на реальном API
timesfm 3.0.1 со случайными весами:

- с --holdout даты forecast.csv были сдвинуты на holdout вперёд, а метрики
  считались по хвосту прогноза, а не по отрезанным дням;
- --horizon < --holdout ронял скрипт на broadcast-ошибке;
- строки плана в конце CSV интерполировались как история;
- <col>_anomalies.csv не создавался ни разу (XReg не отдаёт бэккаст);
- research_bench.py по умолчанию брал колонку sales и падал KeyError,
  --holdout 0 падал внутри модели;
- run_pilot.py печатал бэккаст под видом прогноза.

Нужны numpy, pandas, matplotlib (без torch и весов).
Запуск:  python3 tests/test_scripts.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FAKE = REPO_ROOT / "tests" / "fake_timesfm"
SAMPLE = REPO_ROOT / "data" / "sample" / "history.csv"

try:
    import numpy as np
    import pandas as pd
except ImportError:  # pragma: no cover
    np = pd = None


def run(script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ, PYTHONPATH=str(FAKE), MPLBACKEND="Agg")
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
        cwd=cwd or REPO_ROOT, env=env, capture_output=True, text=True,
    )


@unittest.skipIf(pd is None, "нужны numpy и pandas")
class CampaignForecastTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.hist = pd.read_csv(SAMPLE, parse_dates=["date"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def forecast(self, *args: str, input: Path = SAMPLE) -> tuple[subprocess.CompletedProcess[str], Path]:
        out = self.tmp / "out"
        r = run("campaign_forecast.py", "--input", str(input), "--value-cols", "clicks",
                "--outdir", str(out), *args)
        return r, out

    def test_holdout_даты_и_метрики_по_отрезанным_дням(self) -> None:
        r, out = self.forecast("--holdout", "14", "--horizon", "21")
        self.assertEqual(r.returncode, 0, r.stderr)
        fc = pd.read_csv(out / "clicks_forecast.csv", parse_dates=["date"])
        holdout = self.hist.tail(14)
        # прогноз начинается с первого отрезанного дня, а не после конца CSV
        self.assertEqual(fc["date"].iloc[0], holdout["date"].iloc[0])
        self.assertEqual(len(fc), 21)
        self.assertEqual(fc["actual"].head(14).tolist(), holdout["clicks"].astype(float).tolist())
        self.assertTrue(fc["actual"].tail(7).isna().all())
        # MAE — по первым 14 шагам прогноза (при горизонте 21 хвост не участвует)
        mae = float(np.mean(np.abs(fc["actual"].head(14) - fc["forecast"].head(14))))
        metrics = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(metrics["clicks"]["MAE"], round(mae, 1), places=1)

    def test_holdout_больше_горизонта_понятная_ошибка(self) -> None:
        r, _ = self.forecast("--holdout", "14", "--horizon", "7")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--holdout 14 больше --horizon 7", r.stderr)

    def test_строки_плана_это_будущее_ковариата(self) -> None:
        plan_dates = pd.date_range(self.hist["date"].iloc[-1], periods=6, freq="D")[1:]
        plan = pd.DataFrame({"date": plan_dates, "promo": [0, 1, 1, 0, 0]})
        path = self.tmp / "with_plan.csv"
        pd.concat([self.hist, plan]).to_csv(path, index=False, date_format="%Y-%m-%d")

        r, out = self.forecast("--covariate-col", "promo", "--horizon", "7", input=path)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("покрывает 5 из 7", r.stdout)
        fc = pd.read_csv(out / "clicks_forecast.csv", parse_dates=["date"])
        # прогноз стартует с первой строки плана, план попал в ковариат
        self.assertEqual(fc["date"].head(5).tolist(), list(plan_dates))
        self.assertEqual(fc["promo"].tolist(), [0, 1, 1, 0, 0, 0, 0])
        lift = fc["forecast"][fc["promo"] == 1].mean() - fc["forecast"][fc["promo"] == 0].mean()
        self.assertAlmostEqual(lift, 100.0, places=3)

    def test_аномалии_пишутся_и_ловят_выброс(self) -> None:
        spiked = self.hist.copy()
        spike_row = len(spiked) - 10
        spiked.loc[spike_row, "clicks"] = spiked["clicks"].max() * 3
        path = self.tmp / "spike.csv"
        spiked.to_csv(path, index=False, date_format="%Y-%m-%d")

        for extra in ([], ["--covariate-col", "promo"]):  # оба режима, в т.ч. XReg
            with self.subTest(extra=extra):
                r, out = self.forecast("--horizon", "14", *extra, input=path)
                self.assertEqual(r.returncode, 0, r.stderr)
                anom = pd.read_csv(out / "clicks_anomalies.csv", parse_dates=["date"])
                self.assertEqual(len(anom), 60)
                self.assertEqual(anom["date"].iloc[-1], spiked["date"].iloc[-1])
                crit = anom.loc[anom["severity"] == "CRITICAL", "date"].tolist()
                self.assertIn(spiked["date"].iloc[spike_row], crit)

    def test_неверная_колонка_код_1_и_список_колонок(self) -> None:
        r, _ = self.forecast("--horizon", "7", "--value-cols", "sales")
        self.assertEqual(r.returncode, 1)
        self.assertIn("нет колонок ['sales']", r.stderr)


@unittest.skipIf(pd is None, "нужны numpy и pandas")
class ResearchBenchInputTest(unittest.TestCase):
    """Проверки входа срабатывают до импорта timesfm — заглушка 3.0 не нужна."""

    def test_дефолтная_колонка_есть_в_sample(self) -> None:
        header = SAMPLE.read_text(encoding="utf-8").splitlines()[0].split(",")
        src = (REPO_ROOT / "scripts" / "research_bench.py").read_text(encoding="utf-8")
        default = src.split('"--value-col", default="')[1].split('"')[0]
        self.assertIn(default, header)

    def test_неверная_колонка(self) -> None:
        r = run("research_bench.py", "--input", str(SAMPLE), "--value-col", "sales")
        self.assertEqual(r.returncode, 1)
        self.assertIn("нет колонок ['sales']", r.stderr)

    def test_holdout_0(self) -> None:
        r = run("research_bench.py", "--input", str(SAMPLE), "--holdout", "0")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--holdout 0", r.stderr)


@unittest.skipIf(pd is None, "нужны numpy и pandas")
class RunPilotTest(unittest.TestCase):
    def test_печатает_прогноз_а_не_бэккаст(self) -> None:
        r = run("run_pilot.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("point shape: (1, 14)", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""Тесты валидатора документации Vector Prediction.

Проверяются не «снимки» документации, а поведение проверок: каждая должна
падать на том дефекте, ради которого написана, и молчать на исправленном
дереве. Копия репозитория уходит во временный каталог — рабочий не трогается.

Запуск:  python3 tests/test_validate_docs.py       (только stdlib)
Или:     python3 -m pytest tests/ -q
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def validate(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_docs.py", "--repo-root", str(repo)],
        cwd=repo, capture_output=True, text=True,
    )


class RepoCopy:
    def __enter__(self) -> Path:
        self._tmp = Path(tempfile.mkdtemp())
        self.path = self._tmp / "vector-prediction"
        shutil.copytree(
            REPO_ROOT, self.path,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )
        return self.path

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)


class ValidDocsTest(unittest.TestCase):
    def test_чистое_дерево_проходит(self) -> None:
        with RepoCopy() as repo:
            r = validate(repo)
            self.assertEqual(r.returncode, 0, r.stdout)
            self.assertIn("ошибок 0", r.stdout)


class LicenseTest(unittest.TestCase):
    def test_бейдж_не_может_расходиться_с_license(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "License-MIT-green", "License-Apache_2.0-yellow"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("бейдж", r.stdout.lower())

    def test_раздел_license_сверяется_с_файлом(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "Код репозитория — **MIT**", "Код репозитория — **Apache 2.0**"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("License", r.stdout)


class QuickstartTest(unittest.TestCase):
    def test_колонка_не_из_sample_ловится(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "--value-cols clicks", "--value-cols sales"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("sales", r.stdout)

    def test_колонка_bench_тоже_проверяется(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "--value-col clicks", "--value-col revenue"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("revenue", r.stdout)


class DeckTest(unittest.TestCase):
    def test_число_слайдов_сверяется_с_pptx(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace("13 слайдов", "12 слайдов"),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("слайдов", r.stdout)


class BoundaryTest(unittest.TestCase):
    def test_ноль_три_в_прод_скрипте_ловится(self) -> None:
        with RepoCopy() as repo:
            prod = repo / "scripts" / "campaign_forecast.py"
            prod.write_text(
                prod.read_text(encoding="utf-8").replace(
                    'timesfm.TimesFM_2p5_200M_torch.from_pretrained("google/timesfm-2.5-200m-pytorch")',
                    'timesfm.TimesFM3Forecaster.from_pretrained("google/timesfm-3.0-pytorch")',
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("3.0", r.stdout)

    def test_research_скрипт_обязан_держать_3_0(self) -> None:
        with RepoCopy() as repo:
            research = repo / "scripts" / "research_bench.py"
            research.write_text(
                research.read_text(encoding="utf-8").replace(
                    "timesfm-3.0-pytorch", "timesfm-2.5-200m-pytorch"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("3.0", r.stdout)


class ReferencesTest(unittest.TestCase):
    def test_ссылка_на_несуществующий_файл_ловится(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "`scripts/run_pilot.py`", "`scripts/nonexistent.py`"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("несуществующий", r.stdout)


class MetricsTest(unittest.TestCase):
    def test_таблица_метрик_без_команды_ловится(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            text = readme.read_text(encoding="utf-8")
            text = text.replace(
                "python scripts/research_bench.py --input data/sample/history.csv --value-col clicks",
                "прогон не указан",
            )
            readme.write_text(text, encoding="utf-8")
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("Замеры", r.stdout)


class DocumentedScriptsTest(unittest.TestCase):
    def test_неописанный_скрипт_ловится(self) -> None:
        with RepoCopy() as repo:
            (repo / "scripts" / "new_tool.py").write_text("print('x')\n", encoding="utf-8")
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("new_tool.py", r.stdout)


class DeckFooterTest(unittest.TestCase):
    def _rewrite_slide(self, repo: Path, old: str, new: str) -> None:
        pptx = repo / "docs" / "vector-prediction-obsidian-neon.pptx"
        tmp = pptx.with_suffix(".tmp")
        with zipfile.ZipFile(pptx) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data = src.read(item.filename)
                if item.filename == "ppt/slides/slide9.xml":
                    text = data.decode("utf-8")
                    self.assertIn(old, text)
                    data = text.replace(old, new).encode("utf-8")
                dst.writestr(item, data)
        tmp.replace(pptx)

    def test_колонтитул_со_старым_числом_слайдов_ловится(self) -> None:
        with RepoCopy() as repo:
            self._rewrite_slide(repo, "<a:t>9 / 13</a:t>", "<a:t>9 / 12</a:t>")
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("9 / 12", r.stdout)

    def test_колонтитул_чужой_деки_ловится(self) -> None:
        with RepoCopy() as repo:
            self._rewrite_slide(repo, "Vector Prediction · Hermes · Osmosy",
                                "Vector Legal · Hermes Agent · Osmosy")
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("Vector Legal", r.stdout)

    def test_невоспроизводимое_число_в_pptx_ловится(self) -> None:
        with RepoCopy() as repo:
            self._rewrite_slide(repo, "<a:t>40.55</a:t>", "<a:t>0.105</a:t>")
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("0.105", r.stdout)


class BenchNumbersTest(unittest.TestCase):
    def test_время_в_readme_сверяется_с_json(self) -> None:
        with RepoCopy() as repo:
            readme = repo / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8").replace(
                    "| 2.5 базовый | 33.75 | 0.15 с |", "| 2.5 базовый | 33.75 | 0.16 с |"
                ),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("0.16 с", r.stdout)

    def test_mae_в_license_compliance_сверяется_с_json(self) -> None:
        with RepoCopy() as repo:
            doc = repo / "docs" / "license-compliance.md"
            doc.write_text(
                doc.read_text(encoding="utf-8").replace("| 40.55 |", "| 0.105 |"),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("license-compliance", r.stdout)

    def test_число_в_исходнике_деки_сверяется_с_json(self) -> None:
        with RepoCopy() as repo:
            deck = repo / "docs" / "deck-prediction.py"
            deck.write_text(
                deck.read_text(encoding="utf-8").replace("'31.42'", "'0.107'"),
                encoding="utf-8",
            )
            r = validate(repo)
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertIn("0.107", r.stdout)


class SampleConsistencyTest(unittest.TestCase):
    """Согласованность sample и README — та связка, что сломалась в реальности."""

    def test_колонки_readme_совпадают_с_заголовком_sample(self) -> None:
        sample = REPO_ROOT / "data" / "sample" / "history.csv"
        header = sample.read_text(encoding="utf-8").splitlines()[0].strip()
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        quickstart = readme.split("## Быстрый старт")[1].split("## ")[0]
        self.assertIn(header, quickstart.replace(" ", "").replace("\n", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

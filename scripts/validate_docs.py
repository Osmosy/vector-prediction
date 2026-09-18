#!/usr/bin/env python3
"""Валидатор документации и лицензионных границ Vector Prediction.

Каждая проверка здесь появилась из реального дефекта, который нашёлся при аудите
репозитория 18.09.2026:

- README заявлял Apache-2.0, а файл LICENSE — MIT (самый дорогой дефект: репо
  построен на лицензионной дисциплине, и неверная лицензия своего кода ломает
  доверие ко всей остальной документации);
- quickstart предлагал `--value-cols sales`, а в sample такой колонки нет;
- README и index.html писали «13 слайдов», исходник деки — «12 слайдов»;
- числа бенчмарка (MAE 0.107 / 0.105) не воспроизводились ни на одном датасете
  в репозитории;
- `run_pilot.py` не был описан нигде;
- прод-скрипт и скрипт тест-прогона должны быть разделены: 2.5 в проде, 3.0 в
  research (иначе лицензионный принцип держится только на честном слове).

Запуск:  python3 scripts/validate_docs.py [--repo-root DIR] [--json]
Выход:   0 — всё чисто; 1 — есть ошибки.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Регулярка для «числа о качестве модели»: MAE 31.42, MAPE 2.4% и т.п.
METRIC_RE = re.compile(r"\b(MAE|RMSE|MAPE)\b[^\n]{0,20}?(\d+[.,]\d+)", re.I)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


# --- проверка 1: лицензия кода -------------------------------------------------


def check_license(repo_root: Path) -> list[str]:
    """README (бейдж и раздел License) должен совпадать с файлом LICENSE."""
    errors: list[str] = []
    license_file = repo_root / "LICENSE"
    readme = repo_root / "README.md"
    if not license_file.is_file():
        return ["нет файла LICENSE"]
    if not readme.is_file():
        return ["нет README.md"]

    lic_text = read(license_file)
    # Первая строка MIT/Apache-файла называет лицензию.
    if "MIT License" in lic_text.splitlines()[0]:
        actual = "MIT"
    elif "Apache License" in lic_text:
        actual = "Apache-2.0"
    else:
        actual = "unknown"

    md = read(readme)
    # Бейдж: License-<name>
    badge = re.search(r"badge/License-([A-Za-z0-9._%\-]+)", md)
    if badge:
        declared = badge.group(1).replace("%20", " ").replace("--", "-")
        if actual == "MIT" and "MIT" not in declared:
            errors.append(
                f"README: бейдж лицензии «{declared}», а LICENSE — {actual}"
            )
        elif actual == "Apache-2.0" and "Apache" not in declared:
            errors.append(
                f"README: бейдж лицензии «{declared}», а LICENSE — {actual}"
            )
    else:
        errors.append("README: нет бейджа лицензии")

    # Раздел «## License»
    section = re.search(r"^## License\n(.*?)(?=^## |\Z)", md, re.S | re.M)
    if not section:
        errors.append("README: нет раздела «## License»")
    else:
        body = section.group(1)
        if actual == "MIT" and re.search(r"код\s+репозитория\s*—\s*\*{0,2}Apache", body, re.I):
            errors.append("README: в разделе License код назван Apache, а LICENSE — MIT")
        if actual == "Apache-2.0" and re.search(r"код\s+репозитория\s*—\s*\*{0,2}MIT", body, re.I):
            errors.append("README: в разделе License код назван MIT, а LICENSE — Apache-2.0")
    return errors


# --- проверка 2: quickstart выполним ------------------------------------------


def check_quickstart(repo_root: Path) -> list[str]:
    """Имена колонок из команд README должны существовать в data/sample/history.csv."""
    errors: list[str] = []
    readme = repo_root / "README.md"
    sample = repo_root / "data" / "sample" / "history.csv"
    if not readme.is_file() or not sample.is_file():
        return []

    header = read(sample).splitlines()[0].strip()
    columns = {c.strip() for c in header.split(",")}

    md = read(readme)
    block = re.search(r"^## Быстрый старт\n(.*?)(?=^## )", md, re.S | re.M)
    if not block:
        return ["README: нет секции «## Быстрый старт»"]

    for m in re.finditer(r"--value-cols?\s+([^\s\\|]+)", block.group(1)):
        for col in m.group(1).split(","):
            col = col.strip()
            if not col or not re.fullmatch(r"[A-Za-z0-9_]+", col):
                continue
            if col not in columns:
                errors.append(
                    f"README quickstart: колонки «{col}» нет в data/sample/history.csv "
                    f"(есть: {sorted(columns)})"
                )
    return errors


# --- проверка 3: числа в деке -------------------------------------------------


def check_deck(repo_root: Path) -> list[str]:
    """Число слайдов в README/index.html/комментарии деки и в самом PPTX совпадает."""
    errors: list[str] = []
    pptx = repo_root / "docs" / "vector-prediction-obsidian-neon.pptx"
    deck_src = repo_root / "docs" / "deck-prediction.py"

    if not pptx.is_file():
        return ["нет docs/vector-prediction-obsidian-neon.pptx"]

    import zipfile

    with zipfile.ZipFile(pptx) as z:
        real = len(
            [n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)]
        )

    claims: list[tuple[str, int]] = []
    for rel in ("README.md", "docs/index.html"):
        path = repo_root / rel
        if not path.is_file():
            continue
        for m in re.finditer(r"(\d+)\s+слайд", read(path)):
            claims.append((rel, int(m.group(1))))
    if deck_src.is_file():
        for m in re.finditer(r"^#\s*(\d+)\s+слайд", read(deck_src), re.M):
            claims.append(("docs/deck-prediction.py", int(m.group(1))))

    for where, claimed in claims:
        if claimed != real:
            errors.append(
                f"{where}: заявлено {claimed} слайдов, в PPTX их {real}"
            )
    return errors


# --- проверка 4: лицензионная граница в коде ----------------------------------


def check_license_boundary(repo_root: Path) -> list[str]:
    """Прод-скрипт не должен грузить 3.0; 3.0 живёт только в research-скрипте."""
    errors: list[str] = []
    prod = repo_root / "scripts" / "campaign_forecast.py"
    research = repo_root / "scripts" / "research_bench.py"

    if prod.is_file():
        body = read(prod)
        if "3.0" in body and "TimesFM3" in body:
            errors.append(
                "scripts/campaign_forecast.py: прод-контур ссылается на TimesFM 3.0 — "
                "нарушение лицензионной границы"
            )
        if "timesfm-3.0" in body:
            errors.append(
                "scripts/campaign_forecast.py: загрузка весов 3.0 в прод-скрипте"
            )
    if research.is_file():
        body = read(research)
        if "timesfm-3.0-pytorch" not in body:
            errors.append(
                "scripts/research_bench.py: не грузит 3.0 — тест-прогон потерял контур B"
            )
    return errors


# --- проверка 5: ссылки на файлы ----------------------------------------------


def check_referenced_files(repo_root: Path) -> list[str]:
    """Файлы и скрипты, упомянутые в README, должны существовать."""
    errors: list[str] = []
    readme = repo_root / "README.md"
    if not readme.is_file():
        return []
    md = read(readme)

    for rel in sorted(set(re.findall(r"`((?:scripts|docs|data)/[A-Za-z0-9_./\-]+)`", md))):
        if any(ch in rel for ch in "*<"):
            continue
        if not (repo_root / rel).exists():
            errors.append(f"README: ссылка на несуществующий файл «{rel}»")
    return errors


# --- проверка 6: воспроизводимость чисел --------------------------------------


def check_metric_numbers(repo_root: Path) -> list[str]:
    """Числа о качестве рядом с MAE/RMSE/MAPE должны иметь команду воспроизведения.

    Дефект, из-за которого проверка появилась: README приводил MAE 0.107/0.105
    без датасета, и эти числа нельзя было получить ни на одном файле репозитория.
    """
    errors: list[str] = []
    readme = repo_root / "README.md"
    if not readme.is_file():
        return []
    md = read(readme)
    for block in re.finditer(r"^## [^\n]*[Зз]амеры[^\n]*\n(.*?)(?=^## |\Z)", md, re.S | re.M):
        body = block.group(1)
        has_command = "research_bench.py" in body or "campaign_forecast.py" in body
        # Числа берём из строк таблицы, а не из заголовка: MAE там встречается как
        # имя колонки, и по нему одного ложного срабатывания хватило бы, чтобы
        # проверку отключили. Считаем только строки вида "| ... | 31.42 | ... |".
        measured = [
            line for line in body.splitlines()
            if line.strip().startswith("|") and re.search(r"\d+[.,]\d+", line)
        ]
        if measured and not has_command:
            errors.append(
                f"README «Замеры»: в таблице метрики ({len(measured)} строк), "
                f"но нет команды воспроизведения"
            )
    return errors


# --- проверка 7: описанность скриптов -----------------------------------------


def check_scripts_documented(repo_root: Path) -> list[str]:
    """Каждый скрипт из scripts/ должен быть упомянут в README."""
    errors: list[str] = []
    readme = repo_root / "README.md"
    scripts_dir = repo_root / "scripts"
    if not readme.is_file() or not scripts_dir.is_dir():
        return []
    md = read(readme)
    for script in sorted(scripts_dir.glob("*.py")):
        if script.name.startswith("validate_"):
            continue
        if script.name not in md:
            errors.append(f"README: скрипт scripts/{script.name} не описан")
    return errors


CHECKS = (
    ("лицензия кода", check_license),
    ("quickstart", check_quickstart),
    ("дека", check_deck),
    ("лицензионная граница", check_license_boundary),
    ("ссылки на файлы", check_referenced_files),
    ("воспроизводимость чисел", check_metric_numbers),
    ("описанность скриптов", check_scripts_documented),
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Валидация документации Vector Prediction")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    errors: list[str] = []
    for _, fn in CHECKS:
        errors.extend(fn(repo_root))

    if args.json:
        print(json.dumps({"errors": errors}, ensure_ascii=False, indent=2))
    else:
        for e in errors:
            print(f"ERROR {e}")
        print(f"\nИтог: ошибок {len(errors)}, проверок {len(CHECKS)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

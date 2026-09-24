#!/usr/bin/env python3
"""Контракт CLI: аргументы скриптов против команд в README.

Проверяет, что флаги, которые README предлагает пользователю, действительно
объявлены в argparse соответствующего скрипта. Флаги разбираем статически
(`ast`), без импорта модуля: скрипты тянут numpy/matplotlib/timesfm на уровне
модуля, и в CI без модели их не импортировать.

Дефект, из-за которого проверка появилась: README показывал
`--value-cols sales` и `--value-col sales` при sample без колонки sales —
пользователь копировал команду и получал ошибку.

Проверяются README и гайды из `DOCS`: user-guide тоже даёт команды на копирование.

Запуск:  python3 tests/check_cli_contract.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def declared_flags(script: Path) -> set[str]:
    """Все --flags, объявленные через add_argument в скрипте."""
    tree = ast.parse(script.read_text(encoding="utf-8"))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value.startswith("--"):
                    flags.add(arg.value)
    return flags


# Документы, из которых пользователь копирует команды.
DOCS = ("README.md", "docs/user-guide.md", "docs/data-guide.md", "docs/license-compliance.md")


def commands_in_readme() -> list[tuple[str, set[str]]]:
    """Команды из README и гайдов: (имя скрипта, использованные в ней --flags)."""
    md = "\n".join(
        (REPO_ROOT / rel).read_text(encoding="utf-8")
        for rel in DOCS if (REPO_ROOT / rel).is_file()
    )
    found: list[tuple[str, set[str]]] = []
    for line in md.splitlines():
        m = re.search(r"(scripts/[a-z_]+\.py)", line)
        if not m:
            continue
        script = Path(m.group(1)).name
        flags = set(re.findall(r"(--[a-z][a-z0-9-]+)", line))
        found.append((script, flags))
    # Команды могут быть разбиты переносом строки: подхватываем продолжения.
    for block in re.finditer(r"scripts/([a-z_]+\.py)([^\n]*(?:\n\s+--[^\n]*)*)", md):
        flags = set(re.findall(r"(--[a-z][a-z0-9-]+)", block.group(2)))
        if flags:
            found.append((block.group(1), flags))
    return found


def main() -> int:
    errors: list[str] = []
    for script_name, used in commands_in_readme():
        script = REPO_ROOT / "scripts" / script_name
        if not script.is_file():
            errors.append(f"README: команда для scripts/{script_name}, которого нет")
            continue
        known = declared_flags(script)
        for flag in sorted(used - known):
            errors.append(
                f"README: у scripts/{script_name} использован «{flag}», "
                f"но он не объявлен (есть: {sorted(known)})"
            )

    for e in errors:
        print(f"ERROR {e}")
    print(f"\nИтог: ошибок {len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

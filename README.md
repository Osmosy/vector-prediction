<div align="center">

<img src="assets/vector-logo.png" alt="Vector Prediction" width="200"/>

# Vector Prediction

[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-blue.svg)](https://github.com/NousResearch/hermes-agent)
[![Ecosystem: Vector](https://img.shields.io/badge/Ecosystem-Vector-blue.svg)](https://osmosy.github.io/)
[![Engine: TimesFM 2.5](https://img.shields.io/badge/Engine-TimesFM__2.5__Apache--2.0-yellow.svg)](https://github.com/google-research/timesfm)
[![Research: TimesFM 3.0](https://img.shields.io/badge/Research-TimesFM__3.0__non__commercial-lightgrey.svg)](https://research.google/blog/timesfm-3-a-zero-shot-foundation-model-for-multivariate-forecasting/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Гибридный прогнозный пайплайн: коммерческое прогнозирование на TimesFM 2.5 (Apache-2.0),
исследовательский контур на TimesFM 3.0 — разделены по лицензии и по роли в процессе**

[Сайт доков](https://osmosy.github.io/vector-prediction/) · [Юзер-гайд: роли и шаги](docs/user-guide.md) · [Гайд по данным](docs/data-guide.md) · [Лицензионные правила](docs/license-compliance.md) · [Живая диаграмма (открыть)](https://osmosy.github.io/vector-prediction/vector-prediction.architecture.html)

</div>

---

## Что это

Прогнозный движок экосистемы Osmosy Vector: спрос, продажи, трафик кампаний,
нагрузка — zero-shot, без обучения под задачу, локально на CPU.

Ядро — **двухконтурная схема**:

```
Данные (CSV: история + план)
        │
        ├──► КОНТУР A — ПРОД (TimesFM 2.5, Apache-2.0)
        │      • прогноз, который попадает в боевые планы/отчёты
        │      • XReg-ковариаты: промо-календарь, праздники, цены
        │      • holdout-метрики, аномалии по квантилям
        │
        └──► КОНТУР B — RESEARCH (TimesFM 3.0, non-commercial)
               • тест-прогон и бенчмарк (внутренний отчёт)
               • нативная мультисерийность: несколько целей +
                 past-future ковариаты за один проход (~5x быстрее)
               • НЕ попадает в производственные решения
```

**Рабочий принцип: тест на 3.0 → прогноз на 2.5.** Сначала внутренний прогон на 3.0
отвечает на вопросы о самом ряде (есть ли промо-эффект, какая сезонность, какой
горизонт и порог аномалий держать), а боевой прогноз для клиента считает 2.5 —
под Apache-2.0 и без лицензионных ограничений. Из теста в прод переходят
структурные выводы, а не сами числа прогноза: они остаются внутри исследования
(так требует Non-Commercial Purpose). Проверка границы — если из плана убрать
все артефакты 3.0, план не должен измениться.

Лицензионная граница проведена в коде: `campaign_forecast.py` импортирует только
2.5 API, 3.0 живёт в отдельном `research_bench.py`. Подробности, точные
формулировки лицензии и разбор спорных сценариев — в `docs/license-compliance.md`.

## Состав

| Файл | Что это |
|------|---------|
| `scripts/campaign_forecast.py` | Прод-пайплайн: CSV → прогноз + 60/80% интервалы + аномалии + метрики (2.5) |
| `scripts/research_bench.py` | Тест-прогон 2.5 vs 3.0 на одном ряде (контур B) |
| `scripts/check_system.py` | Preflight: RAM/GPU/диск перед первой загрузкой модели |
| `scripts/run_pilot.py` | Ранний пилот на синтетике (90 дней): скорость на CPU, ловит ли модель промо через ковариаты, аномалии по квантилям. 2.5, свои данные внутри скрипта — для проверки окружения, не для боевых расчётов |
| `docs/data-guide.md` | Какие данные собирать: период, шаг, ковариаты, частые ошибки |
| `docs/user-guide.md` | Юзер-гайд: роли (люди/агенты), путь данных по шагам, каденция |
| `docs/license-compliance.md` | Как разделены контуры по лицензии TimesFM + принцип «тест на 3.0 → прогноз на 2.5» |
| `docs/agent-tasks.md` | Открытые задачи для агента: бенчмарк на реальных весах, титульный арт, пересборка деки, диаграмма |
| `docs/index.html` | Сайт доков для GitHub Pages: навигация по диаграмме, гайдам, презентации |
| `docs/vector-prediction.architecture.html` | Интерактивная диаграмма пайплайна (исходник — `docs/diagram-prediction.json`) |
| `docs/vector-prediction-obsidian-neon.pptx` | [Скачать презентацию (PPTX, 13 слайдов, obsidian-neon)](docs/vector-prediction-obsidian-neon.pptx) · [PDF для просмотра/печати](docs/vector-prediction-obsidian-neon.pdf) |
| `docs/vector-prediction-obsidian-neon.pdf` | PDF-версия презентации — для отправки/печати |
| `docs/deck-prediction.py` | Исходник деки (13 слайдов) — пересборка движком [vector-deck-themes](https://github.com/Osmosy/vector-deck-themes): `python <vector-deck-themes>/deck_builder.py docs/deck-prediction.py 01-obsidian-neon` (PPTX пишется в `docs/`; арты — в `VECTOR_DECK_ASSETS`, PDF — `soffice --convert-to pdf`) |
| `data/sample/history.csv` | Пример входных CSV: `date,clicks,conversions,promo`, 120 дней |
| `out/` | Артефакты прогонов (`metrics.json`, `research_bench.json`, графики) |

## Быстрый старт

> **Если вы не программист** — начните с [docs/user-guide.md](docs/user-guide.md):
> кто что делает (люди и агенты), какие данные готовить, как читать прогноз.
> Про сами данные: [docs/data-guide.md](docs/data-guide.md).

```bash
uv venv ~/.venvs/timesfm && uv pip install --python ~/.venvs/timesfm/bin/python "timesfm[torch,xreg]==3.0.1"
source ~/.venvs/timesfm/bin/activate

# проверка точности: последние 14 дней отрезаны и спрогнозированы (колонки как в sample)
python scripts/campaign_forecast.py --input data/sample/history.csv \
    --date-col date --value-cols clicks --covariate-col promo \
    --holdout 14 --horizon 14 --outdir out/holdout

# прод-прогноз: клики на 14 дней вперёд от конца истории с промо-календарём
python scripts/campaign_forecast.py --input data/sample/history.csv \
    --date-col date --value-cols clicks --covariate-col promo \
    --horizon 14 --outdir out

# тест-прогон 2.5 vs 3.0 (внутренний, не для прод-решений)
python scripts/research_bench.py --input data/sample/history.csv --value-col clicks
```

Выход `out/`: `<col>_forecast.csv` (прогноз + 60/80% интервалы; с `--holdout` —
ещё колонка `actual`, с ковариатом — его план), `<col>_forecast.png`,
`<col>_anomalies.csv` (последние 60 точек истории: OK/WARNING/CRITICAL),
`metrics.json` (MAE/RMSE/MAPE и покрытие 80% интервала на holdout).
С `--holdout N` прогноз строится от точки перед отрезанным хвостом: первые N дат
`forecast.csv` совпадают с отрезанными днями (`--horizon` должен быть ≥ N).

Колонки своего файла смотрите заголовком: у `data/sample/history.csv` это
`date,clicks,conversions,promo`. Имена метрик передаются флагом `--value-cols`
(через запятую), поэтому `sales` — только пример названия. Неверное имя колонки
скрипт не проглатывает: `campaign_forecast.py` и `research_bench.py` выходят
с кодом 1 и печатают список доступных колонок.

## Требования к данным

- CSV: колонка даты + ≥1 метрика; минимум 32 точки, для внятного прогноза — от 100+
- Ковариат-план (промо 0/1) на будущие дни: то, что известно заранее (акции, праздники, цены).
  План — строки в конце того же CSV с датой и ковариатом, но с пустыми метриками:
  `campaign_forecast.py` не считает их историей, а подаёт ковариат на горизонт.
  Нет плана — будущие дни ковариата = 0 («акций не запланировано»)
- Один шаг = одна строка, единицы одинаковые, числа с точкой
- Полный человекоязычный гайд: `docs/data-guide.md`

## Замеры (04.09.2026, Ryzen AI 9 H 365, 20 CPU-ядер)

Воспроизводимые числа — прогон на датасете из репозитория
(`data/sample/history.csv`, контекст 106 точек, горизонт 14, ряд `clicks`):

```bash
python scripts/research_bench.py --input data/sample/history.csv --value-col clicks
```

| Движок | MAE | Время |
|--------|-----|-------|
| 2.5 базовый | 33.75 | 0.15 с |
| 2.5 + XReg | **31.42** | 1.29 с |
| 3.0 базовый | 67.77 | 0.22 с |
| 3.0 + ковариат | 40.55 | 0.24 с |

Результат прогона сохраняется в `out/research_bench.json`.

Вывод: на этом ряде точнее **2.5 + XReg** (31.42 против 40.55 у 3.0) — прод-выбор
оправдан не только лицензией, но и точностью. 3.0 выигрывает в скорости
ковариатного прогноза (0.24 с против 1.29 с), поэтому он и удобен как быстрый
тест-прогон перед боевым расчётом на 2.5. RAM: ~1.5 ГБ у 2.5, ~2 ГБ у 3.0.

Числа на других датасетах приводятся только вместе с указанием датасета и его
расположения — иначе их нельзя перепроверить.

## Проверки перед коммитом

То же гоняет CI (`.github/workflows/validate.yml`):

```bash
python3 scripts/validate_docs.py      # документация и лицензионные границы
python3 tests/test_validate_docs.py   # тесты самих проверок
python3 tests/check_cli_contract.py   # флаги в README и гайдах против argparse
python3 tests/test_scripts.py         # логика скриптов на заглушке timesfm (нужны numpy/pandas/matplotlib)
python3 -m compileall -q scripts docs/deck-prediction.py
```

Что сверяет `validate_docs.py` (каждая проверка появилась из реального дефекта):

| Проверка | Что ловит |
|----------|-----------|
| Лицензия кода | Бейдж и раздел `## License` в README против файла `LICENSE` |
| Quickstart | Имена колонок из команд README против заголовка `data/sample/history.csv` |
| Дека | Число слайдов в README/`index.html`/комментарии против реального PPTX |
| Лицензионная граница | Загрузку 3.0 в прод-скрипте и пропажу 3.0 из тест-скрипта |
| Ссылки на файлы | Упоминания `scripts/*`, `docs/*`, `data/*` без файла на диске |
| Воспроизводимость чисел | Таблицу метрик в README без команды, которой её можно повторить |
| Описанность скриптов | Новый скрипт в `scripts/`, не упомянутый в README |
| Замеры = прогон | MAE и время в README, `docs/license-compliance.md` и деке против `out/research_bench.json` |
| Колонтитулы деки | «N / M» против числа слайдов, чужой бренд, фигуры поверх колонтитула |

## Для агентов

- Читай README.md первым
- Контур B (3.0) — только `scripts/research_bench.py`, не встраивать в прод-пайплайны
- Соблюдай `docs/license-compliance.md`; порядок работы — тест на 3.0 → прогноз на 2.5
- Числа о качестве моделей приводи только воспроизводимые (прогон на `data/sample/history.csv`) или с указанием датасета

## Экосистема Vector

- Хаб: https://github.com/Osmosy/vector-work
- Методология: https://github.com/Osmosy/vector-agent-ready

## License

Код репозитория — **MIT** (`LICENSE`, Copyright (c) 2026 Osmosy).

Движки:

- **TimesFM 2.5 weights** (`google/timesfm-2.5-200m-pytorch`) — Apache-2.0
  (Google Research): коммерческое использование разрешено.
- **TimesFM 3.0 weights** (`google/timesfm-3.0-pytorch`) — TimesFM Non-Commercial
  License v1.0: только исследовательский контур, в производственные решения
  не попадает.
- **TimesFM package code** (github.com/google-research/timesfm) — Apache-2.0.

Точные формулировки лицензии 3.0, границы применимости и разбор спорных
сценариев — в [docs/license-compliance.md](docs/license-compliance.md).
<div align="center">

<img src="assets/vector-logo.png" alt="Vector Prediction" width="200"/>

# Vector Prediction

[![Hermes Agent](https://img.shields.io/badge/Hermes-Agent-blue.svg)](https://github.com/NousResearch/hermes-agent)
[![Ecosystem: Vector](https://img.shields.io/badge/Ecosystem-Vector-blue.svg)](https://osmosy.github.io/)
[![Engine: TimesFM 2.5](https://img.shields.io/badge/Engine-TimesFM__2.5__Apache--2.0-yellow.svg)](https://github.com/google-research/timesfm)
[![Research: TimesFM 3.0](https://img.shields.io/badge/Research-TimesFM__3.0__non__commercial-lightgrey.svg)](https://research.google/blog/timesfm-3-a-zero-shot-foundation-model-for-multivariate-forecasting/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-yellow.svg)](LICENSE)

**Гибридный прогнозный пайплайн: коммерческое прогнозирование на TimesFM 2.5 (Apache-2.0),
исследовательский контур на TimesFM 3.0 — разделены по лицензии и по роли в процессе**

[Документация](docs/) · [Юзер-гайд: роли и шаги](docs/user-guide.md) · [Гайд по данным](docs/data-guide.md) · [Лицензионные правила](docs/license-compliance.md)

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
               • бенчмарк против контура A (внутренний отчёт)
               • нативная мультисерийность: несколько целей +
                 past-future ковариаты за один проход (~6x быстрее)
               • НЕ попадает в производственные решения
```

Лицензионная граница проведена в коде и в описании: TimesFM 3.0 используется
только как внутреннее сравнение подходов (Non-Commercial Purpose по
лицензии Google), финальные цифры всегда даёт контур A. Подробности —
в `docs/license-compliance.md`.

## Состав

| Файл | Что это |
|------|---------|
| `scripts/campaign_forecast.py` | Прод-пайплайн: CSV → прогноз + 60/80% интервалы + аномалии + метрики (2.5) |
| `scripts/research_bench.py` | Исследовательский бенчмарк 2.5 vs 3.0 на одном ряде (контур B) |
| `scripts/check_system.py` | Preflight: RAM/GPU/диск перед первой загрузкой модели |
| `docs/data-guide.md` | Какие данные собирать: период, шаг, ковариаты, частые ошибки |
| `docs/user-guide.md` | Юзер-гайд: роли (люди/агенты), путь данных по шагам, каденция |
| `docs/license-compliance.md` | Как разделены контуры по лицензии TimesFM |
| `docs/vector-prediction-obsidian-neon.pptx` | [Скачать презентацию (PPTX, тема obsidian-neon, 5 слайдов)](docs/vector-prediction-obsidian-neon.pptx) · [PDF для просмотра/печати](docs/vector-prediction-obsidian-neon.pdf) |
| `docs/vector-prediction-obsidian-neon.pdf` | PDF-версия презентации — для отправки/печати |
| `docs/deck-prediction.py` | Исходник деки — пересборка: `deck_builder.py deck-prediction.py 01-obsidian-neon` |
| `data/sample/` | Пример входных CSV (история + план промо) |

## Быстрый старт

> **Если вы не программист** — начните с [docs/user-guide.md](docs/user-guide.md):
> кто что делает (люди и агенты), какие данные готовить, как читать прогноз.
> Про сами данные: [docs/data-guide.md](docs/data-guide.md).

```bash
uv venv ~/.venvs/timesfm && uv pip install --python ~/.venvs/timesfm/bin/python "timesfm[torch,xreg]"
source ~/.venvs/timesfm/bin/activate

# прод-прогноз: клики/конверсии/продажи на 14 дней с промо-календарём
python scripts/campaign_forecast.py --input data/sample/history.csv \
    --date-col date --value-cols sales --covariate-col promo \
    --holdout 14 --horizon 14 --outdir out

# исследовательский бенчмарк 2.5 vs 3.0 (внутренний, не для прод-решений)
python scripts/research_bench.py --input data/sample/history.csv
```

Выход `out/`: `<col>_forecast.csv` (прогноз + интервалы), `<col>_forecast.png`,
`<col>_anomalies.csv` (OK/WARNING/CRITICAL), `metrics.json` (MAE/RMSE/MAPE).

## Требования к данным

- CSV: колонка даты + ≥1 метрика; минимум 32 точки, для внятного прогноза — от 100+
- Ковариат-план (промо 0/1) на будущие дни: то, что известно заранее (акции, праздники, цены)
- Один шаг = одна строка, единицы одинаковые, числа с точкой
- Полный человекоязычный гайд: `docs/data-guide.md`

## Замеры (04.09.2026, Ryzen AI 9 H 365, 20 CPU-ядер)

| Сценарий | 2.5 (прод) | 3.0 (research) |
|----------|-----------|----------------|
| Базовый прогноз, 1 ряд | ~0.15 с | ~0.2 с |
| С промо-ковариатом | ~1.3 с | ~0.23 с (**~6x**) |
| MAE с ковариатом (T=400) | 0.107 | **0.105** |
| RAM | ~1.5 ГБ | ~2 ГБ |

Вывод: для прод-календаря акций 2.5+XReg достаточен; 3.0 — выигрыш в скорости
и на короткой истории, но некоммерческая лицензия ограничивает исследованием.

## Для агентов

- Читай README.md первым
- Контур B (3.0) — только `scripts/research_bench.py`, не встраивать в прод-пайплайны
- Соблюдай `docs/license-compliance.md`

## Экосистема Vector

- Хаб: https://github.com/Osmosy/vector-work
- Методология: https://github.com/Osmosy/vector-agent-ready

## License

Apache 2.0 (код репозитория). TimesFM 2.5 weights — Apache 2.0 (Google Research).
TimesFM 3.0 weights — TimesFM Non-Commercial License v1.0, используется только
в исследовательском контуре.
# Vector Prediction

Гибридный прогнозный пайплайн экосистемы Osmosy Vector на базе Hermes Agent.

## Связанные проекты
- Хаб: https://github.com/Osmosy/vector-work
- Методология: https://github.com/Osmosy/vector-agent-ready

## Для агентов
- Читай README.md первым
- Контур B (TimesFM 3.0) — только `scripts/research_bench.py`, НЕ встраивать в прод-пайплайны
- Соблюдай docs/license-compliance.md: прогнозы 3.0 не используются в производственных решениях
- Модель загружается из ~/.venvs/timesfm (timesfm[torch,xreg], 3.0.1)
- JAX-ошибка `cuInit 303` в логах безвредна (CUDA-плагин на AMD iGPU)
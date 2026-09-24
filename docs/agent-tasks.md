# Передача агенту: итоги аудита 24.09.2026 и открытые задачи

Документ для агента, который продолжает работу над `Osmosy/vector-prediction`
и движком дек `Osmosy/vector-deck-themes`. Часть 1 — что уже сделано и где это
лежит (не переделывать, опираться). Часть 2 — что осталось, по приоритету: у
каждой задачи предусловия, шаги и критерий готовности.

Общие правила — `AGENTS.md` и `docs/license-compliance.md` («тест на 3.0 →
прогноз на 2.5»; числа 3.0 не попадают в клиентские материалы). Перед любым
коммитом — все проверки из README, раздел «Проверки перед коммитом»:

```bash
python3 scripts/validate_docs.py      # документация, лицензионные границы, дека
python3 tests/test_validate_docs.py   # тесты валидатора
python3 tests/check_cli_contract.py   # флаги в README и гайдах против argparse
python3 tests/test_scripts.py         # логика скриптов на заглушке timesfm
python3 -m compileall -q scripts docs/deck-prediction.py
```

В vector-deck-themes: `python tests/smoke_build.py`.

---

## Часть 1. Что сделано

Аудит шёл в облачной сессии без доступа к HuggingFace. Скрипты запускались на
**настоящем коде timesfm 3.0.1 (PyPI) со случайными весами**: так проверены
формы данных, выравнивание и ветвления, но **не точность**. Числа MAE в
документации сверены с сохранённым `out/research_bench.json`, а не пересчитаны.

Влито в `main`:

| Репо | PR | Коммиты |
|---|---|---|
| vector-prediction | #1 | `b139f7c` — скрипты, документация, валидатор |
| vector-prediction | #2 | `74e559d` — вёрстка деки, тесты скриптов, этот план |
| vector-deck-themes | #1 | `d51eae4` — колонтитулы от деки |
| vector-deck-themes | #2 | `ae96fc4`, `431e36d` — пути, рендер, `{theme_short}`, тест + CI |

### 1.1. Скрипты vector-prediction

**`scripts/campaign_forecast.py`** (контур A, прод) — переписан:

- `<col>_anomalies.csv` не создавался никогда: `forecast_with_covariates`
  не возвращает бэккаст, а без ковариата бэккаст не заказывался. Теперь модель
  всегда компилируется с `return_backcast=True`, бэккаст берётся из базового
  `forecast()`, аномалии размечаются в обоих режимах: последние 60 точек
  контекста, OK/WARNING/CRITICAL по 60/80% интервалу одношагового бэккаста.
  Выравнивание (последняя точка бэккаста = прогноз на последний факт) выведено
  из исходника `timesfm_2p5_torch.py`, на реальных весах не проверялось — задача 2.2.
- С `--holdout N` даты `forecast.csv` были сдвинуты на N дней вперёд (прогноз
  отрезанных дней подписывался будущими датами). Теперь даты идут от последней
  точки контекста, шаг берётся из `pd.infer_freq` (по умолчанию D).
- Метрики holdout считались по хвосту прогноза (`point[-N:]`): при
  `--horizon > --holdout` сравнивались чужие дни, при `--horizon < --holdout`
  скрипт падал. Теперь метрики считаются по первым N шагам, а
  `--holdout > --horizon` даёт ошибку argparse (код 2).
- Строки плана (в конце CSV, метрики пустые, ковариат заполнен — формат склейки
  history + plan из user-guide) интерполировались как история. Теперь хвост без
  фактов считается планом и подаётся ковариатом на горизонт. Если плана меньше
  горизонта, остаток заполняется 0 с предупреждением.
- Ковариат на отрезанные holdout-дни брался нулями, теперь из CSV (план был
  известен заранее).
- Ковариат подаётся как `dynamic_numerical_covariates`: цена и расходы —
  числа, не категории.
- В `forecast.csv` добавлены колонки `actual` (при holdout) и колонка
  ковариата. Удалён мёртвый код (`slice_horizon`, `plot_forecast` с глобальной
  переменной).

**`scripts/research_bench.py`** (контур B):

- `--value-col` по умолчанию был `sales` — такой колонки нет в sample
  (`KeyError`). Теперь `clicks`.
- Проверка колонок и `--holdout` (1..len-32) выполняется до импорта timesfm:
  код 1 и список колонок.
- 2.5 + XReg получал нули на будущий ковариат, 3.0 — фактический план, то
  есть сравнение было нечестным. Теперь оба получают план из CSV. На sample
  числа не меняются: в последних 14 днях промо нет.
- `--covariate-col ""` — прогон без ковариата, `VP_OUT` — каталог для JSON.

**`scripts/run_pilot.py`**: при `return_backcast=True` печатал бэккаст как
прогноз (форма `(1, 110)` вместо `(1, 14)`). Теперь берётся хвост горизонта;
число ядер — `os.cpu_count()`.

**`scripts/check_system.py`**: при неизвестном объёме RAM подставлял
выдуманные 8 ГБ, теперь пишет «Unknown» с предупреждением. Добавлены профиль
`--model v3.0`, проверка весов в кэше HF (`Weights`) и зависимостей XReg
(`jax`, `scikit-learn`); версия timesfm читается через `importlib.metadata`.

### 1.2. Документация vector-prediction

- Время в таблицах замеров расходилось с `out/research_bench.json` (0.16 → 0.15,
  0.23 → 0.24 с). «~6x быстрее» заменено на «~5x» (1.29 / 0.24). README и
  `docs/license-compliance.md` синхронны.
- README: версия `timesfm[torch,xreg]==3.0.1`; два прогона — `--holdout`
  (качество, `out/holdout`) и боевой прогноз вперёд; формат строк плана;
  описание выхода; `research_bench.py` при неверной колонке выходит с кодом 1.
- `docs/user-guide.md`: шаг 4 — два прогона; шаг 3 — формат склейки плана;
  шаг 6 — cautious = `lower_80`, optimistic = `upper_80`.
- `docs/data-guide.md`: реальные колонки выхода
  (`forecast, lower_60, upper_60, lower_80, upper_80, <ковариат>`) вместо
  несуществующих `cautious/optimistic`; пример склейки плана.
- `AGENTS.md` и README ссылаются на этот файл.

### 1.3. Дека vector-prediction

- В деке были невоспроизводимые MAE 0.107/0.105 (синтетика вне репо) и вывод
  «лучший — 3.0», противоречащий README. Теперь в ней числа прогона на
  `data/sample/history.csv` и вывод «2.5 + XReg точнее».
- Колонтитулы «Vector Legal · …» и «N / 12» при 13 слайдах — следствие
  движка, исправлены там (1.5).
- Вёрстка: панели заезжали на колонтитул на 8 слайдах из 13; на слайде 10
  перенесённая строка налезала на следующую; на слайде 12 вторая строка
  выходила за панель; на слайде 6 текст карточек шагов налезал сам на себя. В
  `docs/deck-prediction.py` добавлена своя `_panel`: высота считается по
  содержимому с учётом переносов, низ не ниже `SAFE_BOTTOM = 7.02″`.
- `OUT_FMT` → `docs/vector-prediction-{theme_short}.pptx`; `ASSETS` берётся из
  движка (`VECTOR_DECK_ASSETS`); хук `DATA['hero_art']` для своего титульного
  арта (пока закомментирован — задача 2.3).
- PPTX пересобран из исходника движком. Арты извлечены из прежней PPTX
  (сборка до правок совпала с ней попиксельно). PDF собран LibreOffice со
  шрифтами Inter / Inter Display / JetBrains Mono, все 13 страниц просмотрены.

### 1.4. Проверки vector-prediction (CI: `.github/workflows/validate.yml`)

`scripts/validate_docs.py` — 8 проверок. Новые или расширенные:

- «замеры = research_bench.json»: MAE и время в README,
  `license-compliance.md`, `bench_rows` деки и таблице PPTX;
- колонтитулы PPTX: «N / M» против числа слайдов, запрет «Vector Legal»,
  фигуры поверх колонтитула (на прежней деке — 24 ошибки).

`tests/test_validate_docs.py` — 19 тестов (каждая проверка падает на своём
дефекте). `tests/check_cli_contract.py` сверяет флаги и в гайдах.
`tests/test_scripts.py` + `tests/fake_timesfm/` — 9 тестов логики скриптов на
заглушке с контрактом timesfm 3.0.1 (бэккаст выровнен по концу контекста, XReg
отдаёт только горизонт); на коде до аудита падают 8 из 9.

### 1.5. Движок vector-deck-themes

- `engine.py`: колонтитул задаётся через `set_footer(total, brand)`, по
  умолчанию — своя дека Vector Legal; бокс бренда шире, правый край на месте.
  Пути `VECTOR_DECK_ASSETS` / `VECTOR_DECK_OUTDIR` (по умолчанию прежние),
  каталог вывода создаётся при сборке, а не при импорте.
- `deck_builder.py`: движок берётся из `engine.py` рядом (или из
  `VECTOR_DECK_ENGINE`); перед сборкой вызывается
  `set_footer(len(SLIDES), DATA['footer_brand'] или «<title> · Hermes Agent · Osmosy»)`;
  в `OUT_FMT` доступны `{theme}` и `{theme_short}`; `VECTOR_DECK_OUTDIR`
  перекрывает каталог.
- `render_all.sh`: вместо `/home/lenovo/.hermes/.../pptx_render.py` рендер идёт
  через `soffice → PDF → pdftoppm`; `OUTDIR` и `PY` из окружения.
  `build_review.py` берёт `OUTDIR` из окружения.
- `tests/smoke_build.py` + `.github/workflows/smoke.yml`: сборка 15 тем и
  `deck-music.py` с заглушками артов, проверка колонтитулов. Мутация (старый
  footer) даёт 45 ошибок.
- README: переменные окружения, `poppler-utils`, правило №6 (чужие деки
  собирать только через `deck_builder.py`), тема 00 — эталон вне `engine.py`;
  из `.gitignore` убран `render/`.

---

## Часть 2. Что осталось

Приоритет: **P1** — влияет на достоверность чисел или прод-прогноз;
**P2** — качество материалов; **P3** — гигиена.

### 2.1. [P1] Бенчмарк 2.5 vs 3.0 на реальных весах

**Зачем.** Числа во всех таблицах взяты из `out/research_bench.json` от
04.09.2026, до правки честного ковариата. Ожидается, что MAE не изменится
(промо в holdout нет), но это надо подтвердить прогоном.

**Предусловия.** venv `~/.venvs/timesfm` с `timesfm[torch,xreg]==3.0.1`;
доступ к HF (`google/timesfm-2.5-200m-pytorch`, `google/timesfm-3.0-pytorch`).
`python scripts/check_system.py` и `python scripts/check_system.py --model v3.0` —
без FAIL. Ошибка JAX `cuInit 303` безвредна.

**Шаги.**
1. `python scripts/research_bench.py --input data/sample/history.csv --value-col clicks`
2. `git diff out/research_bench.json`.
3. MAE совпал до 2 знаков, изменилось только время → привести время в трёх
   местах: таблица «Замеры» в README, «История замеров» в
   `docs/license-compliance.md`, `bench_rows` в `docs/deck-prediction.py`.
   Пересчитать «~5x» (время 2.5 + XReg / время 3.0 + ковариат) в README
   (схема «Что это»), в `chips` и `arch_items` деки и в выводах под таблицами.
4. MAE изменился → это результат, а не шум: обновить все таблицы и выводы
   («2.5 + XReg точнее…»), указать дату и машину прогона. Если вывод
   поменялся (3.0 стал точнее), это касается только внутреннего сравнения:
   прод остаётся на 2.5 (лицензия).
5. Пересобрать деку (2.4). `python3 scripts/validate_docs.py` — проверка замеров
   найдёт забытое место.

**Готово, когда:** JSON — от нового прогона, валидатор зелёный, в тексте нет
чисел, которых нет в JSON.

### 2.2. [P1] Проверка прод-скрипта на реальных весах

**Зачем.** Логика `campaign_forecast.py` покрыта тестами на заглушке, но
выравнивание бэккаста и поведение XReg на обученной модели не проверялись.

**Шаги.**
1. Обе команды из README «Быстрый старт» как написаны (holdout и прод).
2. `out/holdout/clicks_forecast.csv`: первая дата — 2026-08-15 (первый
   отрезанный день), `actual` совпадает с CSV. В `metrics.json` MAPE
   правдоподобный (порядок 5–15%), `PI80_coverage_%` — не около 0.
3. `clicks_anomalies.csv`: 60 строк, последняя дата — последний день контекста.
   Проверка выравнивания: у бэккаста модели (`model.forecast` с
   `return_backcast=True`, `quant[0, :-H, 5]`) хвост должен следовать за
   `values` с лагом не больше шага. Если он сдвинут на патч (32 точки), значит
   `detect_anomalies` берёт не тот отрезок: исправить и дописать тест с
   заглушкой.
4. Промо-дни sample (26–28.05, 25–27.06, 25–27.07) в разметке аномалий по
   ряду без ковариата должны чаще быть WARNING/CRITICAL, чем обычные дни. Это
   санитарная проверка, не жёсткий критерий.
5. Прогон с планом: дописать в копию sample 14 строк плана с 2–3 днями
   `promo=1` и запустить без `--holdout`. Прогноз в промо-дни должен быть выше
   (XReg ловит эффект), колонка `promo` в CSV совпадает с планом.
6. `python scripts/run_pilot.py`: форма `(1, 14)`, подъём в промо-дни
   ~+35–40% (так задумано синтетикой).
7. `python scripts/check_system.py`: строка `Weights` → PASS после первой загрузки.

**Готово, когда:** пункты 2–7 выполнены, найденные расхождения исправлены с
тестом на заглушке, итоги (1–2 строки и числа) добавлены в PR.

### 2.3. [P2] Свой титульный арт деки

**Зачем.** У темы `01-obsidian-neon` hero-арт — неоновые весы Vector Legal
(`title_hero.png` общий для темы). Правило №1 vector-deck-themes: «чужой арт = брак».

**Шаги.**
1. Сгенерировать hero 16:9 (≥1920×1080, PNG) в палитре темы: фон `#0B1220`,
   акцент `#38B2F8`, второй акцент `#B48CF8`. Сюжет — временной ряд с
   коридором интервалов или прогнозный горизонт; без весов, текста и логотипов.
   Центр спокойный: поверх идут заголовок 60 pt, подзаголовок, три чипа и
   кнопка GitHub.
2. Сохранить как `$VECTOR_DECK_ASSETS/prediction_hero.png` (по умолчанию
   `/tmp/vl_assets`). Исходник арта держать вне репо (README vector-deck-themes,
   «Ассеты»).
3. В `docs/deck-prediction.py` раскомментировать
   `hero_art=('full', 'prediction_hero.png')` в `DATA`.
4. Пересобрать (2.4) и проверить слайд 1: заголовок читается, чипы видны,
   логотип Vector Ray поверх арта справа сверху.

**Готово, когда:** на титуле свой арт, валидатор зелёный, PPTX и PDF обновлены.

### 2.4. [P2] Процедура пересборки PPTX и PDF деки

Выполнять после любой правки `docs/deck-prediction.py` (задачи 2.1, 2.3).

1. Движок: `git clone https://github.com/Osmosy/vector-deck-themes`;
   `pip install python-pptx Pillow numpy`.
2. Ассеты в `VECTOR_DECK_ASSETS`: `vector_ray_t.png` (логотип) и
   `title_hero.png` (арт темы, пока нет своего; после 2.3 — `prediction_hero.png`).
   Эмблема темы в этой деке не используется. Если исходников нет, достать из
   текущей деки:
   ```python
   from pptx import Presentation
   from pptx.enum.shapes import MSO_SHAPE_TYPE
   pics = [s for s in Presentation('docs/vector-prediction-obsidian-neon.pptx').slides[0].shapes
           if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
   open(f'{ASSETS}/title_hero.png', 'wb').write(pics[0].image.blob)
   open(f'{ASSETS}/vector_ray_t.png', 'wb').write(pics[-1].image.blob)
   ```
3. `VECTOR_DECK_ASSETS=<каталог> python <vector-deck-themes>/deck_builder.py docs/deck-prediction.py 01-obsidian-neon`
   — PPTX пишется прямо в `docs/`.
4. PDF: `soffice --headless --convert-to pdf --outdir docs docs/vector-prediction-obsidian-neon.pptx`.
   Нужны шрифты Inter, Inter Display, JetBrains Mono (Ubuntu: `fonts-inter`,
   `fonts-jetbrains-mono`); без них LibreOffice подставит DejaVu.
5. Просмотреть все 13 страниц PDF: ничего не заходит на колонтитулы, строки
   панелей не перекрываются. Проверить длинные строки: `_wrap_lines` оценивает
   переносы по ~11.6 знака на дюйм для Inter 11.5 pt.
6. `python3 scripts/validate_docs.py`.

### 2.5. [P2] Диаграмма: ревьюер между прогнозом и директором

**Зачем.** В `docs/diagram-prediction.json` прогноз идёт
`prod → out → director` в обход ревьюера. По `docs/user-guide.md` (шаг 5)
ревьюер проверяет метрики до передачи людям, но ребра `out → reviewer` нет.

**Шаги.**
1. В `connections` добавить `{"from": "out", "to": "reviewer", "label": "метрики"}`.
   Ребро `out → director` по умолчанию оставить, но переподписать
   «отчёт после допуска».
2. Перегенерировать `docs/vector-prediction.architecture.html` тем же
   генератором (в HTML: `archify 2.17.0-dev.0`, форк — https://github.com/Osmosy/archify).
   HTML руками не править.
3. Согласованность:
   `grep -o 'data-edge-from="[a-z]*" data-edge-to="[a-z]*"' docs/vector-prediction.architecture.html | sort -u`
   совпадает с `connections` в JSON.
4. Открыть страницу (GitHub Pages / локально): новое ребро не пересекает подписи.
5. По желанию: проверка в `validate_docs.py` «рёбра HTML = connections JSON» с тестом.

### 2.6. [P3] Кто ещё пользуется движком дек

**Зачем.** `deck_builder.py` теперь сам выставляет колонтитулы и берёт движок
рядом с собой. Деки других репо экосистемы, собранные старым билдером, могут
нести «/ 12 · Vector Legal».

**Шаги.** В репозиториях Osmosy найти `deck_builder`, `from engine import` и
файлы `*.pptx`; для каждой деки проверить колонтитулы (скрипт — `check_footers`
из `vector-deck-themes/tests/smoke_build.py`) и при расхождении пересобрать
по образцу 2.4. Отчитаться списком «репо → дека → статус».

### 2.7. [P3] Рендеры vector-deck-themes новым пайплайном

`render/` и контактные листы в vector-deck-themes сделаны старым скриптом.
Прогнать `bash render_all.sh` на всех 15 деках с настоящими артами и сравнить
с `render/` (размер, нумерация `slide-NN.png`). Если отличаются только
пиксели антиалиасинга, ничего не коммитить. Если отличается формат, выбрать
один и поправить README.

### 2.8. [P3] Мелочи в коде

- `docs/deck-prediction.py`: функция `_content_slide` нигде не вызывается и
  использует старый `wide_panel` — удалить.
- `docs/deck-prediction.py`: `wide_panel` движка остался на слайде 6 («Разделение
  ответственности») — места хватает, но для единообразия можно перевести на
  `_panel`, потом пересобрать (2.4).
- `scripts/check_system.py`: профили `v2.0` / `v1.0` описывают архивные модели,
  которые пайплайн не использует. Оставить или убрать — решает владелец.

### 2.9. Регулярное (по каденции из user-guide)

- Раз в месяц — проверить лицензию `google/timesfm-3.0-pytorch` (переведена ли
  в Apache-2.0) и появление 3.0 в BigQuery AI.FORECAST; при изменении обновить
  `docs/license-compliance.md` («Путь к коммерческому 3.0») и слайд 7 деки.
- Раз в месяц — повторять 2.1 на свежих данных (только внутренний отчёт).

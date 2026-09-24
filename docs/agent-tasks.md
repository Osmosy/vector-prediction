# Открытые задачи для агента

Задачи, которые нельзя было закрыть в облачной сессии аудита 24.09.2026: нужны
веса моделей с HuggingFace, генерация изображений или локальный рендерер
диаграмм. Каждая задача самодостаточна: предусловия → шаги → критерий готовности.

Общие правила — `AGENTS.md` и `docs/license-compliance.md`. Перед коммитом —
все проверки из README («Проверки перед коммитом») зелёные.

Связанный репо движка дек: https://github.com/Osmosy/vector-deck-themes
(исправления колонтитулов, `{theme_short}`, `VECTOR_DECK_ASSETS` — PR #1 там;
задачи 2 и 3 требуют, чтобы он был влит).

---

## 1. Бенчмарк 2.5 vs 3.0 на реальных весах

**Зачем.** Числа MAE/времени в README, `docs/license-compliance.md` и деке
сверены только с `out/research_bench.json` от 04.09.2026. После аудита
`research_bench.py` подаёт обоим движкам одинаковый план ковариата; на sample
числа меняться не должны (промо в holdout нет), но это надо подтвердить прогоном.

**Предусловия.** venv `~/.venvs/timesfm` с `timesfm[torch,xreg]==3.0.1`,
доступ к HuggingFace (`google/timesfm-2.5-200m-pytorch`,
`google/timesfm-3.0-pytorch`). Preflight: `python scripts/check_system.py`
и `python scripts/check_system.py --model v3.0` — без FAIL.

**Шаги.**
1. `python scripts/research_bench.py --input data/sample/history.csv --value-col clicks`
2. Сравнить `out/research_bench.json` с прежним (`git diff out/research_bench.json`).
3. MAE совпал до 2 знаков → закоммитить только JSON, если изменились лишь секунды,
   и привести время в таблицах к новому JSON (README, `docs/license-compliance.md`,
   `bench_rows` в `docs/deck-prediction.py`), затем пересобрать деку (задача 3).
4. MAE изменился → это результат, а не шум: обновить все три таблицы и выводы
   рядом с ними («2.5 + XReg точнее…», «~5x»), указать дату и машину прогона.
5. `python3 scripts/validate_docs.py` — проверка «замеры = research_bench.json»
   должна пройти; она же ловит забытое место.

**Готово, когда:** JSON — от нового прогона, валидатор зелёный, в тексте нет
чисел, которых нет в JSON. Прогноз 3.0 никуда, кроме внутренних таблиц, не попал.

## 2. Свой титульный арт деки

**Зачем.** У темы `01-obsidian-neon` hero-арт — неоновые весы Vector Legal.
Правило №1 vector-deck-themes: «чужой арт = брак».

**Предусловия.** Генератор изображений (в экосистеме — glm-image), движок из
vector-deck-themes, каталог ассетов `VECTOR_DECK_ASSETS` (по умолчанию `/tmp/vl_assets`).

**Шаги.**
1. Сгенерировать hero 16:9 (≥1920×1080, PNG) в палитре темы: фон `#0B1220`,
   акцент `#38B2F8`. Сюжет — прогноз/временной ряд с коридором интервалов,
   без весов, текста и логотипов. Центр кадра спокойный: поверх идут заголовок и чипы.
2. Сохранить как `$VECTOR_DECK_ASSETS/prediction_hero.png`.
3. В `docs/deck-prediction.py` раскомментировать
   `hero_art=('full', 'prediction_hero.png')` в `DATA`.
4. Логотип Vector Ray (`vector_ray_t.png`) должен лежать там же: его можно
   достать из текущего PPTX (слайд 1, картинка 0.9″ справа сверху) — см. задачу 3.
5. Пересобрать деку (задача 3) и посмотреть слайд 1: заголовок читается,
   чипы не теряются на арте, логотип поверх арта.

**Готово, когда:** на титуле свой арт, валидатор зелёный, PDF обновлён.

## 3. Пересборка PPTX и PDF деки

**Когда.** После любой правки `docs/deck-prediction.py` (задачи 1, 2).

**Шаги.**
1. Ассеты. Если исходников артов нет, достать их из текущей деки:
   ```python
   from pptx import Presentation
   from pptx.enum.shapes import MSO_SHAPE_TYPE
   pics = [s for s in Presentation('docs/vector-prediction-obsidian-neon.pptx').slides[0].shapes
           if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
   open(f'{ASSETS}/title_hero.png', 'wb').write(pics[0].image.blob)   # арт темы
   open(f'{ASSETS}/vector_ray_t.png', 'wb').write(pics[-1].image.blob) # логотип
   ```
2. `VECTOR_DECK_ASSETS=<каталог> python <vector-deck-themes>/deck_builder.py docs/deck-prediction.py 01-obsidian-neon`
   — PPTX пишется прямо в `docs/`.
3. PDF: `soffice --headless --convert-to pdf --outdir docs docs/vector-prediction-obsidian-neon.pptx`.
   Нужны шрифты Inter, Inter Display, JetBrains Mono (иначе LibreOffice
   подставит DejaVu и PDF разъедется с PPTX).
4. Просмотреть все 13 страниц PDF: ничего не налезает на колонтитулы, строки
   панелей не перекрываются.
5. `python3 scripts/validate_docs.py` (сверяет числа, колонтитулы и перекрытия).

**Готово, когда:** PPTX и PDF собраны из исходника без ручных правок, валидатор зелёный.

## 4. Диаграмма: ревьюер между прогнозом и директором

**Зачем.** В `docs/diagram-prediction.json` прогноз идёт `prod → out → director`
в обход ревьюера, а по `docs/user-guide.md` (шаг 5) ревьюер проверяет метрики
**до** передачи людям. Ребро `research → reviewer` есть, `out → reviewer` — нет.

**Шаги.**
1. В `connections`: добавить `{"from": "out", "to": "reviewer", "label": "метрики"}`;
   ребро `out → director` оставить с подписью «отчёт после допуска» или убрать —
   решение за владельцем, по умолчанию оставить.
2. Перегенерировать `docs/vector-prediction.architecture.html` тем же
   генератором (в HTML: `archify 2.17.0-dev.0`, форк — https://github.com/Osmosy/archify).
   HTML руками не править: он сгенерирован из JSON.
3. Проверить, что узлы/рёбра HTML совпадают с JSON:
   `grep -o 'data-edge-from="[a-z]*" data-edge-to="[a-z]*"' docs/vector-prediction.architecture.html | sort -u`
4. Открыть страницу (GitHub Pages / локально) и проверить, что новое ребро не
   пересекает подписи.

**Готово, когда:** JSON и HTML согласованы, ревьюер стоит между `out/` и директором.

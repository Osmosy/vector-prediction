# Дека «Vector Prediction» — тема 01-obsidian-neon (неон-синий на тёмно-синем)
# Контент: гибридный прогнозный пайплайн (2.5 прод + 3.0 research), роли люди/агенты.
import os
OUT_FMT = os.path.expanduser('~/projects/vector-legal-decks15/vector-prediction-{theme}.pptx')

DATA = dict(
    kicker='ПРОГНОЗНЫЙ ДВИЖОК · OSMOSY VECTOR',
    title='Vector Prediction',
    subtitle='Гибридный пайплайн TimesFM: прод-прогноз на 2.5, исследования на 3.0',
    chips=[('2.5', 'прод · Apache'), ('3.0', 'research'), ('6x', 'быстрее ковариаты')],
    github='github.com/Osmosy/vector-prediction',
    footer_tag='Osmosy · Hermes Agent · 2026',
    intro_head='Что такое Vector Prediction',
    intro_lead='Zero-shot прогнозирование спроса, продаж и трафика кампаний без '
               'обучения под задачу — локально на CPU. Два контура, разделённые по лицензии.',
    intro_cards=[
        ('Контур A — ПРОД', ['TimesFM 2.5 · Apache-2.0', 'Боевые прогнозы: планы', 'производства и закупки,', 'KPI кампаний, отчёты']),
        ('Контур B — RESEARCH', ['TimesFM 3.0 · non-commercial', 'Только сравнение моделей:', 'MAE, скорость, ковариаты', 'Не попадает в решения']),
        ('Роли', ['Люди: данные и решения', 'Агенты: сборка, прогноз,', 'ревью качества и лицензии']),
    ],
    wf_steps=[('Данные', 'Продажи + план промо от людей; агент проверяет чек-лист'),
              ('Прогноз', 'Контур A: точечный + интервалы 60/80%, аномалии, метрики'),
              ('Ревью', 'Агент-ревьюер: MAPE 5–15%, покрытие PI, лицензионный чек'),
              ('Решение', 'Директор читает forecast/cautious/optimistic и планирует')],
    arch_items=[('Контур A · прод', 'campaign_forecast.py — TimesFM 2.5, XReg-ковариаты: промо-календарь, праздники, цены'),
                ('Контур B · research', 'research_bench.py — TimesFM 3.0: нативная мультисерийность, past-future ковариаты, ~6x быстрее'),
                ('Лицензионная граница', 'Прогноз 3.0 не попадает в производственные решения — только внутреннее сравнение моделей')],
    fact_big='31.4 vs 40.5', fact_small='MAE на живом тесте: 2.5+XReg против 3.0+ковариат (106 точек, кликс-ряд)',
    final_msg='Прогноз — инструмент. Решение — человек.',
    final_sub='github.com/Osmosy/vector-prediction',
)

from engine import kicker, title_block, footer, bg_fill, card, chip, wide_panel, \
    add_text, add_rect
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

ASSETS = '/tmp/vl_assets'

def _rgb(h): return RGBColor.from_string(h)


def sl_title(slide, th, D):
    if th.get('art'):
        from engine import full_art, half_art
        if th['art'][0] == 'full':
            full_art(slide, th, th['art'][1], overlay_pct=26)
        else:
            half_art(slide, th, th['art'][1])
    ta = th['title_align']
    if ta == 'center' and not (th.get('art') and th['art'][0] == 'half'):
        add_rect(slide, (13.333-4.6)/2, 1.52, 4.6, 0.42, fill=th['surface'],
                 line=th['card_line'], radius=0.21, alpha=70)
        add_text(slide, (13.333-4.6)/2, 1.60, 4.6, 0.3, D['kicker'], size=10,
                 bold=True, font=th['f_mono'], color=th['text'],
                 align=PP_ALIGN.CENTER, spacing=140)
        add_text(slide, 1.67, 2.02, 10.0, 1.2, D['title'], size=60, bold=True,
                 font=th['f_title'], color=th['accent'], align=PP_ALIGN.CENTER)
        add_text(slide, 2.67, 3.28, 8.0, 0.7, D['subtitle'], size=15.5,
                 font=th['f_body'], color=th['text'], align=PP_ALIGN.CENTER)
        for i, (big, small) in enumerate(D['chips']):
            chip(slide, th, 3.47 + i*2.25, 4.12, 1.95, big, small)
        add_rect(slide, 4.87, 5.62, 3.6, 0.52, fill=th['accent'], radius=0.26)
        add_text(slide, 4.87, 5.74, 3.6, 0.3, D['github'], size=11.5, bold=True,
                 font=th['f_mono'], color='FFFFFF', align=PP_ALIGN.CENTER)
        add_text(slide, 4.17, 6.90, 5.0, 0.26, D['footer_tag'], size=9.5,
                 font=th['f_mono'], color=th['muted'], align=PP_ALIGN.CENTER)
    else:
        add_rect(slide, 0.62, 1.30, 0.05, 2.2, fill=th['accent'])
        add_text(slide, 0.92, 1.30, 6.5, 0.3, D['kicker'], size=10.5, bold=True,
                 font=th['f_mono'], color=th['kicker_accent'], spacing=160)
        add_text(slide, 0.88, 1.66, 6.2, 1.15, D['title'], size=54, bold=True,
                 font=th['f_title'], color=th['accent'])
        add_text(slide, 0.92, 2.86, 5.9, 0.7, D['subtitle'], size=15,
                 font=th['f_body'], color=th['text'])
        for i, (big, small) in enumerate(D['chips']):
            x = 0.92 + i*1.95
            add_text(slide, x, 3.85, 1.8, 0.5, big, size=26, bold=True,
                     font=th['f_title'], color=th['accent'])
            add_text(slide, x, 4.36, 1.8, 0.3, small, size=9.5, font=th['f_mono'],
                     color=th['muted'], spacing=100)
        add_text(slide, 0.92, 5.15, 6.0, 0.3, D['github'], size=12.5, bold=True,
                 font=th['f_mono'], color=th['accent'])
        add_text(slide, 0.92, 6.0, 6.0, 0.26, D['footer_tag'], size=9.5,
                 font=th['f_mono'], color=th['muted'])
    # логотип Vector Ray: арт full-фоном — лого сверху справа, после арта (z-order)
    slide.shapes.add_picture(f'{ASSETS}/vector_ray_t.png',
                             Inches(12.20), Inches(0.30), width=Inches(0.9))


def sl_intro(slide, th, D):
    bg_fill(slide, th)
    kicker(slide, th, '01 · Введение')
    title_block(slide, th, D['intro_head'])
    add_text(slide, 0.62, 1.75, 12.1, 0.5, D['intro_lead'], size=13,
             font=th['f_body'], color=th['muted'])
    cw, gap, m = 3.95, 0.25, 0.62
    for i, (head, lines) in enumerate(D['intro_cards']):
        card(slide, th, m + i*(cw+gap), 2.55, cw, 3.4, head, lines)
    footer(slide, th, 2)


def sl_workflow(slide, th, D):
    bg_fill(slide, th)
    kicker(slide, th, '02 · Путь данных')
    title_block(slide, th, '4 шага: от выгрузки до плана')
    xs = [0.55, 3.80, 7.05, 10.30]
    steps = [('Данные', ['Продажи + план промо', 'от людей']), ('Прогноз', ['Контур A (2.5):', 'интервалы, аномалии, MAE']),
             ('Ревью', ['Качество + лицензия', 'агентом-ревьюером']), ('Решение', ['Директор: план по', 'forecast/cautious/optimistic'])]
    for i, (h, l) in enumerate(steps):
        card(slide, th, xs[i], 2.10, 2.92, 2.05, h, l, num=i + 1)
        if i < 3:
            add_rect(slide, xs[i] + 2.97, 3.05, 0.28, 0.035, fill=th['accent'])
    wide_panel(slide, th, 0.83, 4.85, 11.67, 1.95, 'Кто что делает', [
        'Люди: продажи (выгрузка истории) · маркетолог (план промо) · директор (решение).',
        '!Агенты: сборщик (чек-лист, склейка) · прогнозист (контур A) · ревьюер (качество) · исследователь (контур B).',
        'Агент не передаёт людям сырые цифры: сначала holdout-метрики и лицензионный чек.',
    ])
    footer(slide, th, 3)


def sl_arch(slide, th, D):
    bg_fill(slide, th)
    kicker(slide, th, '03 · Двухконтурная архитектура')
    title_block(slide, th, 'Прод и research — раздельно')
    y = 2.3
    for i, (head, lines) in enumerate(D['arch_items']):
        wide_panel(slide, th, 0.62, y + i*1.55, 12.1, 1.35, head, [lines])
    add_text(slide, 0.62, 7.02, 12.0, 0.26,
             'Полные правила — docs/license-compliance.md · гайд по данным — docs/data-guide.md',
             size=10.5, font=th['f_body'], color=th['muted'])
    footer(slide, th, 4)


def sl_final(slide, th, D):
    bg_fill(slide, th)
    add_text(slide, 1.67, 2.3, 10.0, 1.0, D['fact_big'], size=60, bold=True,
             font=th['f_title'], color=th['accent'], align=PP_ALIGN.CENTER)
    add_text(slide, 1.67, 3.6, 10.0, 0.5, D['fact_small'], size=13,
             font=th['f_body'], color=th['text'], align=PP_ALIGN.CENTER)
    add_text(slide, 2.67, 4.7, 8.0, 0.6, D['final_msg'], size=22, bold=True,
             font=th['f_title'], color=th['text'], align=PP_ALIGN.CENTER)
    add_rect(slide, 5.17, 5.55, 5.0, 0.035, fill=th['accent'])
    add_text(slide, 2.67, 5.95, 8.0, 0.3, D['final_sub'], size=12.5,
             font=th['f_mono'], color=th['accent'], align=PP_ALIGN.CENTER)
    add_text(slide, 2.67, 6.95, 8.0, 0.24,
             'Контур A: Apache-2.0 (прод) · Контур B: non-commercial (research only)',
             size=9.5, font=th['f_body'], color=th['muted'], align=PP_ALIGN.CENTER)
    slide.shapes.add_picture(f'{ASSETS}/vector_ray_t.png',
                             Inches(12.20), Inches(0.30), width=Inches(0.9))


SLIDES = [sl_title, sl_intro, sl_workflow, sl_arch, sl_final]
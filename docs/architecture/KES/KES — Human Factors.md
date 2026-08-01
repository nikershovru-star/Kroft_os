---
tags: [kroft, kes, human-factors, cognitive]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KES
summary: "Human Factors (KES#8) — измерение понятности. Прецедент: cognitive complexity."
---

# KES — Human Factors

> Дисциплина KES: почти никто не учитывает человека. Выведена из KP-007 (Measurable)
> и KP-001 (Knowledge > Code — понятный код = сохранённое знание).

## Human Metrics
- `comprehension_time`: сколько архитектору понять модуль (опрос/задача)
- `time_to_first_pr`: через сколько дней новый инженер пишет код
- `cognitive_load`: cyclomatic + cognitive complexity модуля

## Применение
Решение с high cognitive_load → требует упрощения (иначе не пройдёт Human Factors gate).
KROFT docs (neobrutalist, чёткие ADR, Glossary KL) снижают load.

## Честная оценка
Cognitive complexity — метрика понимания кода. KROFT применяет к архитектурным решениям
(понятность ADR = сохранённое организационное знание, ADR-024 L17). Risk: метрики
субъективны — митигация: comprehension_time измеряется задачей, не опросом-самооценкой.
LAW K8: данные в AKB.

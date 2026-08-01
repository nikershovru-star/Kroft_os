---
tags: [kroft, kes, economics, cost]
created: 2026-08-01
author: Hermes
status: v1.0
parent: KES
summary: "Economics (KES#5) — стоимость архитектуры. Прецедент: SEI TD Library / SIG."
---

# KES — Economics

> Дисциплина KES: архитектура оценивается не только технически, но и по стоимости.
> Выведена из KP-007 (Measurable) + KP-003 (Architecture > Features — но с ценой).

## Cost Model (в AKB `economics/`)
- `cost_of_support` = maintainability_level × dev_cost
- `cost_of_complexity` = cyclomatic/cognitive complexity × change_freq
- `cost_of_dependency` = unsupported/deprecated deps × migration_effort
- `cost_of_refactoring` = estimated effort to fix
- `cost_of_risk` = P(failure) × impact($)

## Выбор архитектуры
min(total_cost) при заданном quality bar. TD растёт compound (Karelin 2026) → ранний
рефакторинг дешевле.

## Честная оценка
SEI/SIG: «2-star system = €870k/yr»; TD = compound interest. KROFT считает для своих
компонентов (cost_of_dependency на third-party в runtime — прямо LAW K8). Risk: оценка
грубая на малых данных — митигация: heuristic + trend, НЕ ML (Sculley warning, ADR-024 L14).

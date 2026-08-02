---
tags: [kroft, example, frontend, agent, demo]
created: 2026-07-31
status: active
version: 1.0
author: Chief Knowledge Architect (Hermes)
summary: >-
  Пример приложения на шаблоне Madison Console — автономное «рекламное агентство»:
  5 департаментов (Strategy/Audience/Creative/Media/Analytics) собирают кампанию из
  брифа, плюс консоль-аккаунт-директор и живая симуляция. Single-file vanilla JS.
related:
  - "madison_console_template"
  - "Architecture MOC"
---

# MADISON//AI — Autonomous Ad Agency (пример на шаблоне)

Демо-приложение, построенное поверх [[madison_console_template]]. Показывает паттерн
«агент как оркестрация подсистем» в чистом фронте без бэкенда.

## Поток
1. **Brief screen** — клиент вводит продукт, цель, бюджет, тон, контекст.
2. **Working overlay** — 5 департаментов «работают» параллельно (анимированный прогресс).
3. **War Room** — вкладки:
   - Strategy (big idea, pillars, taglines)
   - Audience (3 персоны)
   - Creative (A/B/C варианты + art-direction brief + форматы)
   - Media (медиаплан, ползунки долей, KPI)
   - Simulation (живой график conversions/spend/ROAS)
   - Report (вердикт + рекомендации)
4. **Console** — «Account Director» принимает команды: `тикток 35%`, `тон премиум`,
   `цель продажи`, `оптимизируй`, `запусти`, `help`.

## Параллель с KROFT_OS
Структура зеркальна [[ADR-014 Agent Platform]]: агент = оркестрация подсистем
(Strategist ≈ Planner, Media ≈ router/policy, Analytics ≈ Evaluator, Creative ≈ Tools).
Здесь всё симулируется в браузере; в KROFT_OS те же роли занимают реальные платформы
волн 7–11.

## Замечания
- Контент генерируется шаблонами (TONES/PERSONAS/CHANNELS) — детерминированно-рандомно.
- Прогноз KPI (CPM/CPC/CTR/CVR → ROAS/CPA) — упрощённая модель, не заменяет реальный eval.
- Не является частью репозитория KROFT_OS; лежит в `docs/templates/` как живой пример стиля.

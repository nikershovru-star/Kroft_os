---
tags: [kroft, template, frontend, pattern, design]
created: 2026-07-31
status: active
version: 1.0
author: Chief Knowledge Architect (Hermes)
summary: >-
  Нео-бруталист hard-shadow «console» HTML-шаблон для standalone-дашбордов и
  агентских UI. Шрифты Anton (display) / Manrope (sans) / JetBrains Mono (mono)
  через Fontsource CDN. Используется как основа визуального стиля KROFT_OS-документов
  и песочниц.
related:
  - "MADISON//AI — Autonomous Ad Agency"
  - "Architecture MOC"
---

# Шаблон: Madison Console (нео-брутализм, hard-shadow)

Одиночный HTML-файл со встроенным CSS/JS (vanilla, без сборки). Назначение:
автономные дашборды, вар-румы, агентские UI, презентационные артефакты KROFT_OS.

## Визуальный язык
- **Hard-shadow** (`4px 4px 0 #000`) на карточках/кнопках — плоский брутализм.
- **Контрастные плашки** (кобальт `#2d5bff`, коралл `#ff5436`, янтарь `#ffc23d`, мятта `#27d3a2`) на тёмном фоне `#0a1420`.
- **Display-заголовки** капсом (Anton), подписи моноширинным (JetBrains Mono).

## Шрифты (Fontsource)
CDN `@latest` — **внимание:** при реальном прод-использовании `@latest` может
отдавать 404 или сломаться; заменить на пинned версию (см. Technical Debt).
Локально файл уже очищен от paste-артефакта `@url:`...``.

## Структура
- `.ticker` — бегущая строка RTB-ленты (sticky top).
- `.mast` — бренд + статус-чипы.
- `.formcard` — карточка брифа.
- `#working` — оверлей прогресса департаментов.
- `#warroom` — вкладки (Strategy/Audience/Creative/Media/Simulation/Report).
- `#console` — чат с «аккаунт-директором» (нижняя панель).

## Правила использования
1. Копировать `templates/madison_console_template.html` как основу.
2. Не тащить бэкенд в HTML — данные инжектятся через JS-стейт (`APP`).
3. Каждый новый UI-артефакт ссылается на этот шаблон (не дублировать стиль).

## Technical Debt
- `Fontsource @latest` → пинировать версию перед продом.
- Канвас-амбиент (`#amb`) и scanline (`#scan`) — декор, можно отключить для a11y.

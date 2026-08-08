---
id: ADR-105
title: Browser Execution Adapter — отложено (готовый backend отсутствует)
status: PROPOSED
date: 2026-08-07
tags: [PHASE-O.4, execution, browser, K5, K6]
---

# ADR-105: Browser Execution Adapter

## Context (PHASE O.4 audit — research-only)

По ТЗ-PHASE-O.4 проведён read-only аудит существующих компонентов KROFT_OS на
предмет browser-execution backend'ов.

**Найдено (факты, grep по всему repo):**
- `Playwright` / `Selenium` / `webdriver` / `MCP` / `BrowserAdapter` / `BrowserService`
  **ОТСУТСТВУЮТ** (0 файлов, 0 упоминаний в коде).
- Имена файлов `*browser*` / `*playwright*` / `*selenium*` / `*mcp*` — **0**.
- `requirements*.txt` / `pyproject.toml` — browser-библиотеки **отсутствуют**.
- Единственная "real" integration: `adapters/desktop_adapter.py`
  (`PyAutoGUIAdapter(IDesktop)` — click/type/screenshot/open_app). Это **desktop-control**,
  НЕ browser-automation. Уже переиспользуется в `RealWorldExecutor` (kind="desktop").
- Архитектурное упоминание browser: только `ADR-021` (ссылка на Chromium sandboxing
  как вдохновение для plugin-sandbox) — НЕ готовый компонент.

**Вывод:** готовый browser backend в repo **ОТСУТСТВУЕТ**. По протоколу ТЗ-пункта 3
реализация НЕ производится; готовится настоящий ADR с минимальным путём подключения.

## Decision

НЕ реализовывать browser-execution в PHASE O.4. Зафиксировать минимальный путь
подключения будущего готового backend'а без нарушения K5/K6.

### Минимальный способ подключения (когда backend появится)

1. **Переиспользовать существующий паттерн** `RealWorldExecutor` (composition/):
   добавить ветку `kind == "browser"` → `_exec_browser(action)`, аналогично уже
   существующим `_exec_file` / `_exec_desktop` / `_run_shell`.
2. **Backend-источник (K5):** либо
   (a) внешняя библиотека (playwright/selenium) обёрнутая в adapter в `adapters/`
       реализующий существующий контракт (например расширение `IDesktop` или новый
       `IBrowser`, НО новый порт создаётся только если доказана необходимость и
       согласован K6-review);
   (b) либо переиспользование `PyAutoGUIAdapter` (desktop-control) для навигации по
       уже открытому браузеру через click/type (НЕ browser-specific, но работает
       без новых зависимостей).
3. **Размещение:** backend подключается из `composition/` (composition root может
   импортировать `adapters/`; arch-gate ЗАПРЕЩАЕТ adapters→services, но разрешает
   composition→adapters и composition→services/security — проверено на TerminalExecutor).
4. **Kernel/contracts/planning НЕ изменяются** (K6). Маршрутизация только через
   существующий `attach_executor` hook (`CognitiveKernel.attach_executor`).
5. **Никаких новых портов/DTO/слоёв** без отдельного K6-review.

### Почему НЕ создаём новый порт сейчас
- Нет готового backend'а → нечего типизировать портом.
- Создание `IBrowser` сейчас = speculative abstraction (нарушение K5 "без крайней
  необходимости"). Ждём реальный backend, затем типизируем минимально.

## Alternatives considered
- **A. Реализовать browser через PyAutoGUIAdapter прямо сейчас** — отклонено: это
  desktop-control, не browser-adapter; создаёт ложное впечатление "browser backend
  готов". Честнее зафиксировать отсутствие.
- **B. Добавить заглушку BrowserAdapter (fake)** — отклонено: нарушает K5 (нет
  реального переиспользования) и вводит в заблуждение archived-gate.
- **C. Подключить внешнюю Playwright как зависимость** — вне scope O.4 (требует
  нового adapter + возможно нового порта; отдельная фаза с K5-исследованием
  готовых библиотек и K6-review).

## Consequences
- KROFT_OS НЕ имеет browser-execution capability (честно задокументировано).
- `RealWorldExecutor` поддерживает file/command/shell/desktop/execute_plan + sim-fallback
  (PHASE O.1–O.3). Browser — задел через будущую ветку `kind="browser"`.
- Kernel/contracts НЕ изменены (git diff пуст). Arch-gate зелёный (не тронут).

## K5/K6 verification
- ✅ **K5:** ничего не создано speculatively; переиспользуется паттерн RealWorldExecutor.
- ✅ **K6:** kernel/contracts/planning НЕ изменены; только этот ADR-документ.

## Follow-up (не выполняется в O.4)
- K5-исследование готовых browser-библиотек (Playwright/Selenium) + K6-review нового
  порта `IBrowser` (если потребуется) → отдельная фаза PHASE-O.5 (Browser Backend).

---
tags: [kroft, build-journal, runtime, phase-1, foundation]
created: 2026-08-01
author: Hermes (senior software architect)
depends_on: [ADR-020 — Runtime Host Architecture, KROFT_OS Master Development Plan v3.0, Kernel Review (Phase 0.5)]
summary: >-
  Build Journal — Runtime Phase 1 (Foundation). Реализация поверх существующего
  kernel/kernel.py через порт contracts.IKernel (вариант б, ADR-020). Без дублирования
  ядра, без wrapper-адаптеров. Arch-gate зелёный, Smoke пройден, regression 745 passed.
---

# Build Journal — Runtime Phase 1 (Foundation)

> Дата: 2026-08-01. Архитектура заморожена (ADR-020, вариант б утверждён).
> Phase 1 реализует Foundation: Runtime Host поверх существующего `kernel/kernel.py`
> через порт `contracts.IKernel`. НЕ дублирует ядро, НЕ создаёт wrapper'ов.

## Что реализовано

- **Порт `contracts/i_kernel.py`** — минимальный интерфейс ядра (`IKernel` Protocol:
  `initialize/start/stop/emit/save`, `state: LifecycleState`). Создан НОВЫЙ порт.
- **`kernel/kernel.py` реализует `IKernel`** — добавлено наследование `class Kernel(IKernel)`
  (без изменения логики; только импорт порта + наследование). Ядро НЕ дублировано.
- **`runtime/` — компонентный слой** (зависит ТОЛЬКО от `contracts`, arch-gate LAW):
  - `runtime_state.py` — FSM-зеркало над `IKernel` (инъекция, не импорт kernel)
  - `signal_handler.py` — SIGINT/SIGTERM → graceful stop (через `IKernel`)
  - `component_registry.py` — manifest-based ComponentRegistry (НЕ Wrapper Architecture)
  - `kernel_runtime.py` — `run(kernel: IKernel, ...)` драйвер жизненного цикла
  - `runtime_host.py` — `discover()/load()/validate()/activate()`
  - `runtime/__init__.py` — экспортирует `RuntimeContext` (из существующего `context.py`) + `CapabilityRegistry`
- **`bootstrap_v2.py`** (composition root, вне arch-gate) — создаёт `Kernel` и связывает с runtime.
- **Удалён дубликат `runtime/runtime_context.py`** (второй мир) — `RuntimeContext` уже был в `context.py`.

## Какие файлы изменены

Созданы:
- `contracts/i_kernel.py` (новый порт)
- `runtime/__init__.py`, `runtime/__main__.py`, `runtime/component_registry.py`,
  `runtime/kernel_runtime.py`, `runtime/runtime_host.py`, `runtime/runtime_state.py`,
  `runtime/signal_handler.py`
- `bootstrap_v2.py` (composition root)

Модифицированы (не дублируя ядро):
- `contracts/__init__.py` — экспорт `IKernel`, `LifecycleState`
- `kernel/kernel.py` — `class Kernel(IKernel)` (расширение, не переписывание)

Удалены:
- `runtime/runtime_context.py` (дубликат — нарушал запрет на параллельный мир)

## Какие тесты добавлены

Не добавлялись (Phase 1 — инфраструктура; Smoke доказывает связь с предыдущей фазой через
`python -m runtime` → Kernel READY). Unit-тесты компонентов — в Phase 2 (Runtime Host).

## Результаты Smoke

```
python -m runtime --mode=kernel-only
[runtime] node=local port=8000 — Kernel READY (extending IKernel, no wrappers)
EXIT=0
```
Ad-hoc verifier (tmp, удалён): FSM INITIALIZED→RUNNING→STOPPED; компоненты загружены;
без wrapper'ов. VERIFY OK.

## Результаты Regression

```
pytest tests/test_architecture.py   -> 3 passed  (arch-gate GREEN)
pytest tests/                      -> 745 passed, 15 skipped, 6 failed
```
6 failures — в untracked тестах `test_graph_*` / `test_semantic_search`, созданных ДО
сеанса (pre-existing; AttributeError `GraphQueryEngine.export_graph` отсутствует,
AssertionError в semantic-логике). НЕ связаны с Phase 1 (эти тесты не импортируют
runtime/kernel/contracts.i_kernel). Мои правки НЕ вызвали новых падений (было 740 → 745 passed,
потому что `runtime/__init__.py` починил `test_runtime.py`, ранее падавший на `RuntimeContext`).

## Обновлённые ADR

- **ADR-020** (accepted): зафиксирован вариант б (Kernel минимален, ComponentRegistry вместо
  Wrapper). Phase 1 доказал: `runtime` зависит только от `contracts.IKernel`, ядро не дублировано.
- **Master Development Plan v3.0** (draft): Phase 1 отмечена как реализованная (Smoke + Regression).

## Оставшиеся риски

1. Pre-existing 6 failures в untracked graph/semantic тестах — требуют отдельного ADR/фикса
   (вне Phase 1; они не мешают Runtime Foundation).
2. `runtime/kernel_runtime.py` блокирует main-thread через `while kernel.state == RUNNING`
   (для graceful SIGINT). В Phase 2 (Runtime Host) это заменится на EventBus-driven loop.
3. Host rename (KnowledgeOS-v5 → KROFT_OS) — инфраструктурно, не блокер Phase 1.

## Следующий этап

**Phase 2 — Runtime Host** (MDP v3.0): `ComponentRegistry` загружает платформы 11–14 как
компоненты через манифесты (`plugins/*/manifest.yaml`); `RuntimeHost.discover() → load() →
validate() → activate()`. Без wrapper'ов. Kernel НЕ импортирует платформы (LAW K1).

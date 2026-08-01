---
tags: [kroft, adr, adr-026, composition-root, architecture, phase-b]
created: 2026-08-01
author: Hermes (Architecture Intelligence Protocol)
status: proposed
relates_to: [ADR-020, ADR-002, ADR-003, LAW-K1, LAW-K3, Dependency-Report-Phase-B]
laws_affected: [K1, K3]
summary: >
  Введение выделенного слоя Composition Root (composition/), который ЕДИНОЛИЧНО
  отвечает за создание и связывание всех компонентов системы. Kernel перестаёт
  владеть DI-контейнером и persistence-реализациями (нарушение LAW K1, см. V1/V2
  в Dependency Report). Wiring происходит только здесь, через порты contracts.
---

# ADR-026 — Composition Root

## 1. Context

После Variant A (слияние KnowledgeOS-v5 → KROFT_OS) статический анализ
(`docs/architecture/Dependency Report — Phase B.md`) выявил:

- `kernel/kernel.py:21` → `from infrastructure import DependencyContainer`
- `kernel/kernel.py:22` → `from infrastructure.snapshot_store import SnapshotStore`

Kernel напрямую знает DI-реализацию и persistence-реализацию. Это нарушает
**LAW K1** (kernel импортирует только contracts + runtime) и противоречит
принципу «Small Kernel» / Dependency Inversion.

Кроме того, код сборки раздроблен: часть wiring в `cli/commands.py`, часть в
`bootstrap_v2.py`. Отсутствует единая точка сборки.

## 2. Decision

Ввести **выделенный слой `composition/`** (Composition Root) — единственное
место, где создаются и связываются:

- `DependencyContainer` (из infrastructure)
- `SnapshotRepository` / `SnapshotStore` (реализация `ISnapshotRepository`)
- `EventBus` (InMemoryEventBus)
- `Services` (VaultStreamCrawler, GraphQueryEngine, …)
- `Adapters` (LocalFileSystemAdapter, …)
- `PluginManager`, `Configuration`, `Logger`

**Kernel** получает все зависимости ГОТОВЫМИ через конструктор (constructor
injection) — только через порты `contracts.*`. Kernel НЕ импортирует
`infrastructure` ни при каких условиях.

## 3. Consequences

**Positive:**
- Kernel становится pure: imports = {contracts, runtime, stdlib}.
- Arch-gate `test_no_forbidden_cross_layer_imports` → GREEN (K1 соблюдён).
- Тестируемость: Kernel можно инстанцировать с mock-контейнером.
- Wiring локализован, читаем, единообразен.

**Negative / Risks:**
- Дополнительный слой (но он маленький и не добавляет рантайм-логики).
- Необходимость refactor `cli/commands.py` и `bootstrap_v2.py` для делегирования
  сборки в `composition/`.

## 4. Wiring ownership (явно)

| Кто создаёт | Где |
|--------------|-----|
| DependencyContainer | `composition/` |
| SnapshotRepository (ISnapshotRepository impl) | `composition/` (wrap infrastructure.SnapshotStore) |
| EventBus | `composition/` |
| Services | `composition/` (через ports) |
| Adapters | `composition/` |
| Plugins | `composition/` |
| Kernel | получает container готовым, сам НЕ создаёт |

## 5. Alternatives considered

- **Оставить wiring в `bootstrap_v2.py`** (не создавать папку): rejected —
  `bootstrap_v2.py` уже перегружен, и `cli/` дублирует сборку. Нет единой точки.
- **Явный `bootstrap/` вместо `composition/`**: rejected — термин «bootstrap»
  уже занят (`bootstrap.py`, `bootstrap_v2.py` = runtime host). `composition/`
  точнее передаёт смысл (Composition Root pattern, Martin Fowler).
- **Kernel создаёт контейнер лениво через фабрику в contracts**: rejected —
  нарушает K1 (contracts не должен знать реализацию).

## 6. Evidence

- `tests/test_architecture.py` ALLOWED: kernel={contracts, runtime} (tightened в Variant A).
- `laws.yaml` K1: «Kernel imports ONLY contracts/. Never services/, adapters/, infrastructure/».
- Dependency Report Phase B, секции V1/V2.

---
tags: [kroft, adr, adr-028, kernel-purity, architecture, phase-b]
created: 2026-08-01
author: Hermes (Architecture Intelligence Protocol)
status: accepted
evidence_level: III
relates_to: [ADR-026, ADR-027, ADR-020, LAW-K1, LAW-K3, Dependency-Report-Phase-B]
laws_affected: [K1, K3]
summary: >
  Жёсткое определение чистоты Kernel: Kernel НЕ знает о реализации контейнера,
  файловой системе, хранилище, сетевых клиентах, логгерах, конфигурации, DI,
  персистенции. Kernel = lifecycle FSM + orchestration ТОЛЬКО через порты.
---

# ADR-028 — Kernel Purity

## 1. Context

Kernel сейчас нарушает чистоту (LAW K1): импортирует `infrastructure`
(DependencyContainer, SnapshotStore). Цель Phase B — довести Kernel до состояния,
где он не знает НИЧЕГО ниже Runtime.

## 2. Kernel Purity Contract

Kernel MAY import ONLY:
- `contracts.*` (порты: IKernel, IEventBus, ISnapshotRepository, IFileSystem, …)
- `runtime.*` (RuntimeContext, registries)
- stdlib (asyncio, threading, enum, typing, datetime, …)

Kernel MUST NOT import / instantiate / know about:
| Категория | Пример |
|-----------|--------|
| DI / Container | `DependencyContainer` |
| Persistence | `SnapshotStore`, `SnapshotRepository` impl |
| File System | `LocalFileSystemAdapter` |
| Network clients | `http_server`, `omni_route_adapter` |
| Loggers | любой конкретный logger |
| Configuration | `ConfigLoader` |
| EventBus impl | `InMemoryEventBus` (только порт IEventBus) |

Всё перечисленное впрыскивается через конструктор из Composition Root (ADR-026).

## 3. Verification

- `tests/test_architecture.py::test_no_forbidden_cross_layer_imports` MUST be GREEN
  для kernel (ALLOWED["kernel"]={contracts, runtime}).
- Ad-hoc скрипт: `grep -rnE "infrastructure|services|adapters" kernel/` → пусто.

## 4. Consequences

- Kernel становится минимальным, стабильным, тестируемым.
- Любое новое требование к kernel идёт через НОВЫЙ порт в contracts, не через импорт.

## 5. Evidence

- `laws.yaml` K1, K3.
- Dependency Report Phase B, V1/V2.
- `PROJECT_CONTEXT_MAP.md` §3 (LAW K1–K8).

---

## Approval (K5)

Accepted per TZ-003 WP-08. Evidence sufficient (implemented + verified).

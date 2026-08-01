---
tags: [kroft, adr, adr-029, bootstrap-lifecycle, architecture, phase-b]
created: 2026-08-01
author: Hermes (Architecture Intelligence Protocol)
status: accepted
evidence_level: III
relates_to: [ADR-026, ADR-027, ADR-028, LAW-K1, LAW-K3, LAW-K8, Dependency-Report-Phase-B]
laws_affected: [K1, K3, K8]
summary: >
  Определить канонический жизненный цикл загрузки/выгрузки ОС (Bootstrap Lifecycle):
  process start → configuration → DI → runtime → kernel → plugins → services → ready,
  и обратно (shutdown). Вся сборка локализована в composition/ (Composition Root),
  ядро не создаёт зависимостей. Это фундамент для будущих крупных этапов
  (Supervisor & Recovery, Multi-Agent Runtime, Plugin Marketplace, Distributed/Cluster,
  Self-Healing Kernel) без изменения ядра.
---

# ADR-029 — Bootstrap Lifecycle

## 1. Context

Phase B выделил Composition Root (`composition/`, ADR-026) и очистил Kernel
(ADR-028 Kernel Purity — ядро не импортирует infrastructure, получает всё через
constructor injection). Теперь нужен единый, задокументированный **порядок
загрузки ОС**, чтобы добавление будущих подсистем (Supervisor, Recovery,
Hot Reload, Plugin Marketplace, Cluster) не требовало переписывания точек входа
(`main.py`, `bootstrap_v2.py`) и не затрагивало ядро.

## 2. Decision — Bootstrap Lifecycle

```
process start
      ↓
configuration        # argv, env, kroft_os.yaml, --plugin-dir, --desktop-adapter
      ↓
DI                   # composition.container_builder.build_container()
      ↓               #   registers ports + adapters + services + IStateRepository
runtime              # CapabilityRegistry, RuntimeContext (composition.runtime_factory)
      ↓
kernel               # composition.kernel_factory.build_kernel() -> Kernel(...)
      ↓               #   receives runtime_context, event_bus, state_repository, registry
plugins              # PluginLoader.apply_exporters / apply_agent_extensions
      ↓
services             # composition.kernel_factory.build_services() (Supervisor, Recovery, ...)
      ↓
ready                # system accepts commands / runtime host runs
```

**Shutdown (reverse):**
```
stop services → stop kernel → flush state (IStateRepository) → exit
```

## 3. Почему Kernel не создаёт зависимости

Kernel получает `runtime_context`, `event_bus`, `state_repository`, `registry`
готовыми через конструктор (ADR-028). Composition Root (`composition/bootstrap.py
build_system()`) оркестрирует последовательность. Это:
- соблюдает LAW K1 (kernel → только contracts/runtime);
- соблюдает LAW K3 (composition — единственное место wiring);
- соблюдает LAW K8 (runtime-сервисы расширяемы без правки ядра).

## 4. Расширяемость (без изменения ядра)

| Будущий этап | Точка расширения (не ядро) |
|--------------|----------------------------|
| Supervisor & Recovery | `composition.kernel_factory.build_services()` + `IStateRepository.checkpoint/rollback` |
| Multi-Agent Runtime | `composition.service_factory` (новые сервисы) |
| Plugin Marketplace | `composition.plugin_factory` + `PluginLoader` |
| Distributed Runtime | `composition.bootstrap.build_system(peer=...)` |
| Cluster Mode | `composition.bootstrap` (node coordinator) |
| Self-Healing Kernel | `IStateRepository.rollback` в Supervisor (ядро не меняется) |

## 5. Consequences

**Positive:**
- Единая точка сборки (`composition/`); точки входа (`main.py`, `bootstrap_v2.py`) — тонкие.
- Ядро стабильно, чисто (arch-gate GREEN), тестируемо.
- Будущие этапы добавляются в composition/, не в kernel/.

**Negative / Risks:**
- `composition/` вне arch-gate (PROJECT_PKGS) — его импорты не проверяются гейтом.
  Митигация: composition — Composition Root по определению (легален импорт всего);
  риск контролируется code-review + тестами сборки.

## 6. Evidence

- `composition/bootstrap.py::build_system` — реализует sequence.
- `composition/kernel_factory.py::build_kernel` — constructor injection.
- `contracts/i_state_repository.py::IStateRepository` — checkpoint/rollback порт.
- Dependency Report Phase B, ADR-026/027/028.

---

## Approval (K5)

**Status: accepted** as of 2026-08-02 (TZ-003 WP-08, human-approved scope).
Implemented and verified in Phase B (ADR-026/027/028) and Phase C (ADR-029).
Evidence Level: III (implemented + architecture-gate green + 768 tests passing).

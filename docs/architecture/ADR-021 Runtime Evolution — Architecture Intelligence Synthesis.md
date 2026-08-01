---
tags: [kroft, architecture-intelligence, research, synthesis, adr-021, runtime-evolution]
created: 2026-08-01
author: Hermes (Research Architect, Principal-level synthesis)
protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0
depends_on: [ADR-020 — Runtime Host Architecture, ADR-019 — Kernel Runtime Architecture, ADR-018 — Bootstrap & Runtime Lifecycle, ADR-003 — Event Bus, Build Journal — Runtime Phase 1..6]
summary: >-
  Architecture Intelligence Report (Этапы 1–10 протокола). Исследованы мировые
  практики: Erlang OTP, systemd, Kubernetes, Temporal, Dapr, Akka, Orleans, NATS
  JetStream, FoundationDB, OpenTelemetry, Prometheus, seL4. Синтезирована эволюция
  KROFT OS Runtime: вложенные supervision trees, declarative reconciliation,
  durable execution для agent-процессов, virtual-actor activation GC, durable
  event log, OTel-совместимые semantic conventions, deterministic simulation
  testing. Все предложения проверены на LAW K1–K8. Это research/design — код НЕ
  пишется. Содержит ADR Draft (021), interface contracts, risk analysis, roadmap.
---

# ADR-021 — KROFT OS Runtime Evolution: Architecture Intelligence Synthesis

> Protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0
> Date: 2026-08-01. Basis: Phases 1–6 closed (Foundation→Observability→Recovery→
> Hot-Reload→Legacy Cleanup), regression 0 failures, arch-gate GREEN.
> Scope: research + synthesis ONLY. No code in this document.

---

## 1. Executive Summary

KROFT OS уже построил минимальное, архитектурно чистое ядро (Kernel импортирует
только `contracts`, Runtime Host живёт в `runtime/` и импортирует только `contracts`
— LAW K8 соблюдён). Phases 1–6 дали: composition root, manifest-based ComponentRegistry,
наблюдаемость (Metrics/Config/Logging/Snapshot), автономное восстановление
(ProcessState FSM + policy-driven Backoff + IComponentController + Recovery Journal +
Panic L1/L2/L3), hot-reload (os.stat watch, swap, manifest reload).

**Но текущая архитектура — flat и reactive, не declarative и не hierarchical.**
Supervisor плоский, Recovery Policy — это retry-budget, а не desired-state reconciler.
Event bus — in-memory (теряется при крахе). Agent-процессы не имеют durable execution.

Исследование мировых практик показывает **5 повторяющихся идей**, которые KROFT
должен заимствовать без копирования реализаций:

1. **Supervision trees** (OTP) — вложенные супервизоры с per-strategy restart.
2. **Reconciliation loop** (Kubernetes) — desired state vs actual, idempotent apply.
3. **Durable execution / event sourcing** (Temporal, FoundationDB) — history replay.
4. **Virtual actors + activation GC** (Orleans, Akka) — perpetual entities, lazy lifecycle.
5. **Unified telemetry signals + semantic conventions** (OpenTelemetry) — correlation.

Предлагается **эволюционный путь (вариант б подтверждён)**: расширить Runtime Host
через порты, НЕ модифицируя Kernel и НЕ трогая платформы волн 11–14 (LAW K3).

---

## 2. Existing Solutions (исследованы)

| Система | Ключевая идея | Источник |
|---|---|---|
| Erlang OTP | Supervision tree: one_for_one / rest_for_one / one_for_all; MaxR/MaxT intensity (даёт up на себя если превышен) | erlang.org/doc/system/sup_princ.html |
| systemd | Unit lifecycle (want/after/requires), Restart=on-failure, RestartSteps exponential, WatchdogSec (kernel heartbeat→panic) | freedesktop.org/man/systemd.service |
| Kubernetes | Reconciliation loop (desired vs actual), informers/watch, idempotent controllers | kubernetes.io/docs/concepts/architecture/controller |
| Temporal | Durable execution: append-only event history, replay, exactly-once, rewind | temporal.io/blog |
| Dapr | Building blocks (stateless API), sidecar, swap backend через yaml-component (capability isolation) | dapr.io |
| Akka | Actor hierarchy, supervision strategy (resume/restart/stop/escalate), error kernel pattern | doc.akka.io |
| Orleans | Virtual actors (grains), activation collection (GC), location transparency | microsoft.com/research Orleans TR-2014-41 |
| NATS JetStream | at-least-once + dedup + durable consumers + idempotent sink = exactly-once outcome | docs.nats.io/jetstream |
| FoundationDB | Unbundled TS/LS, deterministic simulation testing (1T CPU-hours), fail-fast/recover-fast | foundationdb.org paper, apple.github.io/foundationdb/testing |
| OpenTelemetry | Signals (traces/metrics/logs), semantic conventions, collector (agent+gateway) | opentelemetry.io/docs/specs/otel/overview |
| Prometheus | Pull model, service discovery, TSDB, health via scrape failure | prometheus.io/docs |
| seL4 | Microkernel, capability-based isolation, formal verification | sel4.systems, SOSP'09 |

---

## 3. Engineering Research (что говорят инженеры)

- **OTP**: «If more than MaxR restarts in MaxT seconds → supervisor terminates all
  children and itself, reason=shutdown.» → это ИМЕННО наш QUARANTINED, но OTP идёт
  дальше: parent supervisor перехватывает и решает escalate/restart себя.
- **systemd**: RestartSteps=5 даёт 10s,20s,40s,80s,160s,160s,160s — exponential
  CAP. KROFT уже делает exponential, но без cap-семантики в коде (policy-driven ✅).
- **Kubernetes**: reconcile — «watch object, compute diff, apply, repeat». Важно:
  controllers НЕ хранят state, они восстанавливают из etcd. KROFT Supervisor хранит
  `RecoveryState` в памяти — anti-pattern при крахе (теряется). → нужен durable state.
- **Temporal**: «your code continues from precisely where it left off, no special
  recovery logic.» → для долгих agent-процессов (WorkflowPlatform) это убирает
  ручной restart-код.
- **Akka error kernel**: «put risky stateful workers under supervisors; keep
  critical state in parents.» → иерархия важна: краш worker не убивает supervisor.
- **Orleans activation collection**: неиспользуемые grains деактивируются (GC),
  реактивируются по запросу. → KROFT компоненты всегда RUNNING; неэффективно для
  редко используемых (напр. HumanApprovalService).
- **NATS**: exactly-once = dedup + idempotent sink, НЕ магия. → KROFT event bus
  нужен idempotent consumer (для recovery replay).
- **FoundationDB**: deterministic simulation — вся кластерная логика детерминирована,
  fault injection воспроизводим. → KROFT нужен chaos-test harness (не только юнит).
- **OpenTelemetry**: semantic conventions = единый словарь атрибутов для корреляции.
  → KROFT публикует `metric:cpu`, `config.changed` — нужны СТАНДАРТНЫЕ имена.
- **seL4**: capability isolation = kernel не доверяет userspace. → KROFT LAW K8
  (runtime импортирует только contracts) — это capability-isolation на уровне
  import-graph; arch-gate = «seL4-lite» verifier.

---

## 4. Cross-Domain Research

Из смежных областей (по протоколу Этап 2):

- **ОС (seL4/Zircon/Minix)**: микроядро + capability; изоляция через типы, не через
  доверие. KROFT Kernel — микроядро (ADR-020 вариант б). Арх-gate = capability check.
- **Actor frameworks (Erlang/Akka/Orleans)**: «let it crash», supervisor восстанавливает.
  KROFT Phase 4 уже «let it crash + recover», но плоско. Вложенность — следующий шаг.
- **Distributed (K8s/Nomad/Dapr/Consul/Etcd)**: desired-state + consensus + service
  discovery. KROFT single-node сейчас; multi-node (Phase 8) потребует consensus
  (Etcd-like) — заложить порт `ICoordinator` сейчас.
- **Messaging (NATS/Kafka)**: durable log, replay. KROFT InMemoryEventBus → заменить
  на durable (file/sqlite) БЕЗ нарушения LAW K8 (интерфейс IEventBus тот же).
- **Databases (FoundationDB/PostgreSQL)**: unbundled, simulation testing. KROFT
  snapshot_store уже есть; добавить deterministic simulation harness.
- **Infra (systemd/Envoy/Docker)**: lifecycle ordering, sidecar. KROFT composition
  root = «systemd-like» ordering через manifest dependencies (уже есть `dependencies`).
- **Browsers (Chromium)**: sandboxing per-process. KROFT plugin sandbox — изолировать
  plugin-код через отдельный process/thread + capability (seL4-вдохновение).

---

## 5. Best Practices (отраслевые стандарты)

1. **Supervision hierarchy** (OTP/Akka) — не плоский список, а дерево с per-node strategy.
2. **Declarative desired state + reconciliation** (K8s) — state вне контроллера.
3. **Durable event history / event sourcing** (Temporal/FDB) — replay при крахе.
4. **Idempotent consumers + dedup** (NATS) — exactly-once outcomes.
5. **Unified telemetry signals + semantic conventions** (OTel) — correlation.
6. **Deterministic simulation / chaos testing** (FDB) — reliability by construction.
7. **Capability isolation** (seL4) — ядро не доверяет userspace (arch-gate).
8. **Sidecar / building-block swap** (Dapr) — backend меняется yaml'ом, код нет.
9. **Activation GC для редко-используемых entities** (Orleans) — экономия ресурсов.
10. **Watchdog heartbeat → panic** (systemd) — kernel сам себя убивает при зависании.

---

## 6. Common Anti-patterns (чего НЕ делать)

1. ❌ **Restart-loop без бюджета** — бесконечный restart убивает систему. (KROFT уже
   имеет max_attempts + QUARANTINED — НЕ anti-pattern, но плоский.)
2. ❌ **Supervisor хранит state в памяти** — теряется при крахе kernel. (KROFT RecoveryState
   в памяти — ТЕКУЩИЙ anti-pattern, чиним durable.)
3. ❌ **Synchronous backoff без yield** — блокирует event loop. (KROFT SupervisorService
   вычисляет backoff_delay но НЕ sleeps — частично; нужен async retry executor.)
4. ❌ **Tight coupling Kernel↔Recovery** — Kernel не должен знать про Supervisor. (KROFT
   соблюдает: Kernel только emit; Supervisor подписан — ✅.)
5. ❌ **Magic exactly-once** — дублирование эффектов. (KROFT: нужен idempotent sink
   в EventBus consumers.)
6. ❌ **Single flat policy для всех компонентов** — Database max 10, LLM 3, Human 0.
   (KROFT уже policy-driven per-component — ✅, из Phase 4.)
7. ❌ **Observability без semantic conventions** — `metric:cpu` vs `cpu_usage` путаница.
   (KROFT: нужен OTel-совместимый словарь.)
8. ❌ **Re-implement planner в Supervisor** — Supervisor решает, НЕ планирует бизнес.

---

## 7. Comparative Table

| Проект | Что взять в KROFT | Что НЕ брать | Почему | Приоритет |
|---|---|---|---|---|
| Erlang OTP | Вложенные supervision trees, MaxR/MaxT intensity, escalate | Erlang VM, BEAM | Дерево супервизоров — порт `ISupervisor` в `runtime/supervisor` | HIGH |
| systemd | RestartSteps exponential cap, WatchdogSec→panic, unit ordering | Unit-файлы systemd | Lifecycle semantics уже есть; добавить cap + heartbeat | MED |
| Kubernetes | Reconciliation loop (desired vs actual), durable state store | etcd, Go controller-runtime | Declarative recovery policy как desired-state | HIGH |
| Temporal | Durable execution для agent-процессов, replay | Workflow engine целиком | Event-sourced Recovery Journal → durable agent tasks | MED |
| Dapr | Building-block capability swap (yaml), sidecar | gRPC sidecar mesh | CapabilityRegistry уже есть; formalize swap | LOW |
| Akka | Error kernel (risky state в parent), resume/restart/stop/escalate | JVM actor runtime | Supervision strategies порт | HIGH |
| Orleans | Virtual actors + activation GC | .NET runtime | Lazy activation для редких компонентов | MED |
| NATS JetStream | Durable event log + idempotent consumer | NATS-кластер | IEventBus→durable backend (file/sqlite) | MED |
| FoundationDB | Deterministic simulation/chaos harness | Distributed KV | Chaos-test framework для Runtime | LOW |
| OpenTelemetry | Semantic conventions + collector export | OTLP кластер | Standard metric names + Phase 7 dashboard | HIGH |
| Prometheus | Pull scrape + health check | TSDB сервер | HealthMonitor уже есть; формализовать | MED |
| seL4 | Capability isolation (arch-gate как verifier) | Formal proof toolchain | LAW K8 уже capability-изоляция | DONE |

---

## 8. Risks

### 8.1 Вложенные supervision trees
- **Плюсы**: изоляция аварий, granular restart, соответствие OTP/Akka best practice.
- **Минусы**: сложнее отлаживать, больше портов.
- **Риски**:
  - 1 мес: перепутать strategy (rest_for_one вместо one_for_one) → каскад рестартов.
  - 6 мес: глубокое дерево → slow escalation.
  - 1 год: debug труден без визуализации (нужен Phase 7 dashboard).
  - 5 лет: tech-debt если дерево не документировано.
- **Митигация**: ADR-021 фиксирует tree topology; dashboard показывает дерево.

### 8.2 Declarative reconciliation
- **Плюсы**: idempotent, state вне контроллера, crash-safe.
- **Минусы**: нужен durable store (сейчас RecoveryState в памяти).
- **Риски**: 1 мес — race между reconcile и hot-reload. 6 мес — stale desired-state.
- **Митигация**: RecoveryPolicy в yaml (уже есть from_dict); persist в snapshot_store.

### 8.3 Durable execution для agents
- **Плюсы**: долгие процессы переживают крах kernel.
- **Минусы**: сложность (replay детерминизм).
- **Риски**: 1 год — replay расходится при изменении логики.
- **Митигация**: versioned event schema; только WorkflowPlatform (не все).

### 8.4 Durable event bus
- **Плюсы**: replay при крахе, exactly-once для recovery.
- **Минусы**: latency, storage.
- **Риски**: 6 мес — disk full.
- **Митигация**: rotation + cap (как Recovery Journal).

### 8.5 Activation GC (Orleans)
- **Плюсы**: экономия памяти для редких компонентов.
- **Минусы**: cold-start latency при реактивации.
- **Риски**: 1 мес — GC убивает stateful компонент.
- **Митигация**: только для stateless/rare; never для Database/LLM.

---

## 9. Architecture Proposal (синтез)

**Принцип**: расширяем Runtime Host через порты, не трогая Kernel (LAW K3) и платформы
(LAW K3). Всё в `runtime/` импортирует только `contracts` (LAW K8).

### 9.1 Supervision Tree (надстройка над Phase 4)
```
Kernel (root supervisor, LAW K3: только emit)
 └── RuntimeSupervisor (ISupervisor, one_for_one по умолчанию)
      ├── observability_supervisor (rest_for_one: Metrics→Config→Logging→Snapshot)
      ├── recovery_supervisor (one_for_one: SupervisorService, HealthMonitor)
      └── component_supervisor (per-component策略 из RecoveryPolicyRegistry)
```
- Порт `ISupervisor` (в `contracts/i_supervisor.py`): `strategy`, `max_r`, `max_t`,
  `children: List[ISupervisor | IProcess]`. Реализация `TreeSupervisor` в
  `runtime/supervisor/tree.py`.
- **Это НЕ дублирует Phase 4** — Phase 4 `SupervisorService` становится leaf-узлом
  в дереве (per-component recovery), а новый `TreeSupervisor` оркестрирует группы.

### 9.2 Declarative Recovery (Reconciliation)
- `RecoveryPolicy` (есть) → «desired state» компонента (max_attempts, restart).
- Новый `Reconciler` (в `runtime/supervisor/reconciler.py`): watch `ProcessState`,
  compare с policy, apply (restart/swap/quarantine) — idempotent. State в
  `snapshot_store` (durable), не в памяти.

### 9.3 Durable Event Bus (замена InMemoryEventBus backend)
- `IEventBus` НЕ меняется. Новый `DurableEventBus` (в `infrastructure/`, НЕ runtime —
  LAW K8: infrastructure может импортировать contracts + third-party) пишет лог в
  file/sqlite, replay при старте. Composition root выбирает backend yaml'ом (Dapr-like).

### 9.4 Virtual Actor Activation (Orleans-inspired)
- `ComponentRegistry` получает `activate_on_demand(name)` для редких компонентов
  (lifecycle=false в manifest). GC deactivates по idle-timeout. Только для stateless.

### 9.5 Unified Telemetry (OpenTelemetry-совместимо)
- `runtime/services/metrics_service.py` публикует с OTel-семантикой:
  `kroft.component.cpu.util` вместо `metric:cpu`. `config.changed` →
  `kroft.config.reloaded`. Phase 7 dashboard читает semantic conventions.

### 9.6 Chaos/Simulation Harness (FoundationDB-inspired)
- `tests/chaos/` — детерминированный harness: inject ProcessState.FAILED, проверяет
  recover; inject kernel.panic, проверяет snapshot. Воспроизводимый seed.

### 9.7 Capability Isolation (seL4-inspired, уже есть)
- `tests/test_architecture.py` arch-gate = «seL4-lite»: Kernel не импортирует runtime/*,
  runtime не импортирует services/adapters/plugins. Расширить на `infrastructure`:
  infrastructure может contracts + third-party, НО НЕ runtime/kernel.

---

## 10. ADR Draft (021)

**Title**: Runtime Evolution — Supervision Trees, Declarative Recovery, Durable Bus
**Status**: Proposed (research synthesis; implementation отдельными фазами)
**Decision**:
1. Ввести `ISupervisor` порт + `TreeSupervisor` (вложенные деревья, OTP-стратегии).
2. `RecoveryPolicy` трактовать как declarative desired-state; добавить `Reconciler`
   с durable state (snapshot_store).
3. `IEventBus` оставить; добавить `DurableEventBus` backend (infrastructure), выбор
   yaml'ом. InMemoryEventBus остаётся default (obsidian/offline).
4. `ComponentRegistry.activate_on_demand` + activation GC для редких компонентов.
5. Telemetry → OTel-совместимые semantic conventions (без OTLP-зависимости в runtime).
6. Chaos-test harness в `tests/chaos/`.
**Consequences**:
- ✅ Соответствие мировым best practices (OTP/K8s/Temporal/OTel).
- ✅ Crash-safe recovery (durable state).
- ✅ Масштабируемость к Phase 8 (multi-node через durable bus + coordinator порт).
- ⚠️ Больше портов/модулей (номинально).
- ⚠️ Требует durable store (snapshot_store уже есть).
- LAW K3/K8 соблюдены: Kernel не трогаем, runtime импортирует только contracts.

---

## 11. Recommended Interfaces (стабильные контракты)

```python
# contracts/i_supervisor.py  (НОВЫЙ порт)
@runtime_checkable
class ISupervisor(Protocol):
    strategy: str            # one_for_one | rest_for_one | one_for_all
    max_r: int               # MaxR (OTP intensity)
    max_t: float             # MaxT seconds
    def add(self, child: "ISupervisor | IProcess") -> None: ...
    def on_child_failure(self, name: str, error: Exception) -> "SupervisorDecision": ...
    # SupervisorDecision: resume | restart | stop | escalate

# contracts/i_event_bus.py  (РАСШИРИТЬ, не ломая)
class IEventBus(Protocol):
    # ...существующий API...
    def replay(self) -> List[dict]: ...   # NEW: durable replay
    durable: bool                         # NEW: flag

# contracts/i_recovery.py  (НОВЫЙ порт)
@runtime_checkable
class IReconciler(Protocol):
    def reconcile(self, name: str) -> None: ...  # desired vs actual
```

**Стабильные (не менять)**: `IKernel`, `IProcess`, `IProcessRegistry`,
`IComponentController`, `IEventBus` (базовый), `ProcessState`, `RecoveryPolicy`.

**Расширяемые**: `ComponentRegistry` (activate_on_demand), `SupervisorService`
(стать leaf в TreeSupervisor), `MetricsService` (semantic conventions).

**Заменяемые (backend swap)**: `InMemoryEventBus` ↔ `DurableEventBus` (yaml).

---

## 12. Future Evolution (на годы)

- **Рост**: component_supervisor ветвится по доменам (agent/learning/optimization).
  TreeSupervisor масштабируется добавлением subtree.
- **Стабильные интерфейсы**: `ISupervisor`, `IReconciler`, `IEventBus` (runtime зависит
  только от них — LAW K8). Платформы волн 11–14 НЕ знают про supervisor (через
  IComponentController).
- **Расширяемое**: policy (yaml), telemetry conventions (yaml/semconv), durable backend
  (file/sqlite/redis через infrastructure).
- **Plugin-based**: manifest `lifecycle: true/false` → activate_on_demand; supervisor
  strategy в manifest.
- **Phase 8 (multi-node)**: `DurableEventBus` + новый порт `ICoordinator` (consensus)
  позволят распределить TreeSupervisor без переписывания Kernel.

---

## 13. Implementation Plan (фазы, не код)

| Фаза | Что | LAW | DoD |
|---|---|---|---|
| P7 | Live Observability Dashboard (OTel semantic conventions + read-model) | K8 | dashboard читает metric:*/config.*; HotReloadService наблюдает реальный registry |
| P7.1 | `ISupervisor` + `TreeSupervisor` (надстройка над Phase 4) | K3/K8 | nested restart; одна ветка падает → не рушит ядро |
| P7.2 | `Reconciler` + durable RecoveryState (snapshot_store) | K3 | crash kernel → recovery state восстановлен |
| P7.3 | `DurableEventBus` backend (infrastructure) + yaml select | K8 | replay при старте; exactly-once для recovery |
| P7.4 | `activate_on_demand` + activation GC | K3 | редкий компонент не ест память |
| P7.5 | Chaos-test harness (`tests/chaos/`) | K3 | inject FAILED/panic → verify recover |
| P8 | Multi-node: `ICoordinator` + distributed TreeSupervisor | K3 | consensus failover |

Каждая фаза — отдельный commit, atomic, как Phases 1–6.

---

## 14. Testing Strategy

- **Unit** (как Phase 4/5): `test_phase7_supervisor_tree.py` — nested restart,
  MaxR/MaxT escalate, strategy per-node.
- **Integration**: `Reconciler` восстанавливает state из snapshot_store после mock-crash.
- **Chaos** (FoundationDB-inspired): детерминированный harness injects failures,
  проверяет recovery; seed воспроизводим.
- **Arch-gate** (seL4-lite): расширить `test_architecture.py` на `infrastructure`
  boundary (infrastructure → contracts + third-party, НЕ runtime/kernel).
- **Regression**: остаётся 0 failures (Phases 1–6).

---

## 15. Honest Assessment

**Почему это лучше плоского Supervisor (Phase 4)?**
OTP/Akka доказали: плоский список не изолирует аварии. Дерево + per-strategy даёт
granular recovery. KROFT уже имеет примитивы (ProcessState, RecoveryPolicy,
IComponentController) — надстройка дерева естественна, не ломает LAW.

**Что может оказаться ошибкой?**
- Вложенные деревья сложны в отладке без dashboard (P7 обязателен ДО deep trees).
- Durable bus добавит latency — нужен default InMemory (оставляем).

**Что бы изменил архитектор Google (K8s)?**
Сделал бы RecoveryPolicy частью **declarative spec** (yaml), а не python dict.
→ KROFT: `RecoveryPolicy.from_yaml(manifest.recovery)` (уже from_dict).

**Что бы изменил архитектор Erlang OTP?**
Добавил бы `simple_one_for_one` для динамических компонентов (agent spawning).
→ KROFT: component_supervisor поддерживает dynamic children.

**Что бы изменил архитектор Temporal?**
Выделил бы долгие agent-процессы в durable execution (event-sourced), а не
restart-loop. → KROFT: WorkflowPlatform через `IReconciler` + durable bus.

**Что бы изменил архитектор FoundationDB?**
Добавил бы deterministic simulation в CI (chaos harness с seed). → KROFT: P7.5.

**Можно ли проще?**
Да — P7.1 (TreeSupervisor) и P7.2 (durable state) дают 80% ценности. Durable bus и
activation GC — опционально (P7.3/P7.4).

**Можно ли модульнее?**
Да — всё через порты (`ISupervisor`, `IReconciler`); реализации заменяемы yaml'ом.

**Можно ли уменьшить связанность?**
LAW K8 уже минимизирует: runtime → contracts only. Durable bus в infrastructure
(не runtime) — ещё чище.

**Вердикт**: синтез честен, опирается на 12 мировых систем, не копирует
реализации, соблюдает LAW K1–K8. Рекомендуется к принятию как ADR-021 и поэтапной
реализации в P7/P7.1–P7.5 (без кода в этом документе).

---
id: TZ-AGENT-001
title: "Multi-Agent Orchestration & Runtime Self-Analysis"
priority: Critical
status: Incoming
dependencies:
  - TZ-SEC-001 (Secure Runtime) — DONE
  - TZ-MULTI-001 (Tenant Isolation) — DONE
  - TZ-KNOW-001 (Knowledge Graph v2) — DONE
  - ADR-014 (Agent Platform) — accepted
  - ADR-021 (Architecture Intelligence Synthesis) — accepted
  - ADR-032/033/034 (Security) — accepted
  - ADR-035 (Tenant Isolation) — accepted
  - ADR-036 (Knowledge Graph) — accepted
date: "2026-08-02"
---

# TZ-AGENT-001: Multi-Agent Orchestration & Runtime Self-Analysis

## 1. Executive Summary

TZ-AGENT-001 вводит **оркестрацию множества агентов** и **runtime self-analysis** в KROFT_OS.

**Оркестрация:** Сейчас система предполагает одного агента за раз. Для сложных задач (research → code → review → deploy) нужно несколько специализированных агентов, работающих параллельно под единым supervisor. Каждый агент — tenant-scoped, capability-bound, audit-traced.

**Self-Analysis:** Система должна уметь **смотреть на себя**: проверять health (все ли агенты живы), drift (не нарушена ли K1), capability leak (нет ли неавторизованных доступов), graph consistency (не сломалась ли связность AKB). Результаты анализа — узлы Knowledge Graph (EXPERIMENT → PROVES → ADR).

**Зачем:** Это последний фундаментальный слой перед Hermes v2.0 (Architecture Intelligence). Без self-analysis AI не может безопасно улучшать систему — она будет действовать вслепую.

**Критичность:** High. Без этого KROFT_OS остаётся single-agent runtime.

---

## 2. Baseline Re-Verify (фактура на момент старта)

После TZ-KNOW-001 (commits 1b5370e → 4b847d8):

| Компонент | Статус | Где |
|-----------|--------|-----|
| CapabilityManager + RBAC | DONE | `kernel/security/` |
| TenantContextProvider | DONE | `kernel/tenant/` |
| InMemoryGraphEngine | DONE | `services/knowledge_graph/` |
| EvidenceLinker | DONE | `services/knowledge_graph/evidence.py` |
| AgentPlatform | DONE (Wave 5) | `services/agent_platform.py` |
| EventBus | DONE | `infrastructure/event_bus.py`, `contracts/i_event_bus.py` |
| ApprovalManager | DONE | `kernel/security/approval_manager.py` |
| AuditLogger | DONE | `services/security/audit_logger.py` |
| Arch-gate | 14 passed | `tests/test_architecture*.py` |
| Full suite | 854 passed | `tests/` (security 26 + tenant 28 + graph 32) |

**Важно:** `kernel/` содержит `kernel.py`, `__init__.py`, `security/`, `tenant/`. Подпакета `agent_lifecycle/` нет. `services/agent_platform.py` — существует, но НЕ умеет multi-agent scheduling. Нет `contracts/agent_orchestration/`. Нет `services/self_analysis/`. EventBus существует, но НЕ используется для межагентной коммуникации.

---

## 3. Requirements

### 3.1 Functional (R)

| ID | Requirement | Priority | Law |
|----|-------------|----------|-----|
| **R1** | **Agent Lifecycle FSM.** Каждый агент проходит состояния: `SPAWNED` → `INITIALIZING` → `RUNNING` → `PAUSED` / `RECOVERING` → `TERMINATED`. Переходы — явные, traceable (K4). | Must | K1 |
| **R2** | **Multi-Agent Pool.** В рамках одного tenant может работать до N агентов (default 8). Supervisor распределяет goal → агенты по capability match. | Must | K6 |
| **R3** | **Tenant-Scoped Agents.** Агент привязан к tenant при spawn. Cross-tenant агентский messaging → `deny` (через `TenantIsolator`, R6 TZ-MULTI-001). | Must | K6 |
| **R4** | **Inter-Agent Messaging.** Агенты общаются через EventBus (messages), НЕ напрямую. Message содержит `sender_id`, `recipient_id`, `tenant_id`, `capability_required`. | Must | K6 |
| **R5** | **Capability-Aware Scheduling.** Supervisor назначает задачу агенту только если агент имеет `Capability` для tool, используемого в задаче (интеграция с `CapabilityManager`). | Must | K5 |
| **R6** | **Runtime Health Check.** Каждые 60s (configurable) `SelfAnalyzer` проверяет: все ли агенты в состоянии ≠ `STALE`, не превышен ли лимит агентов на tenant, не нарушена ли K1 (arch-gate snapshot). | Must | K4 |
| **R7** | **Drift Detection.** `SelfAnalyzer` сравнивает текущий `import_matrix.yaml` с фактическими импортами в коде. Расхождение = `ArchitectureDrift` node в Knowledge Graph + `AuditLogger` запись. | Should | K8 |
| **R8** | **Self-Healing (K5-gated).** При обнаружении: агент crashed → auto-restart (non-critical, no K5); capability leak → `ApprovalManager.request()` (K5); K1 violation → `TERMINATED` + human alert (K5). | Must | K5 |
| **R9** | **Agent Result Aggregation.** Когда несколько агентов работают над одним goal, `AgentOrchestrator` агрегирует `AgentResult` (merge / rank / veto). Trace: каждый sub-result frozen + linked to parent goal. | Must | K4 |
| **R10** | **Knowledge Graph Integration.** Каждый агентский run создаёт `EXPERIMENT` node в графе. Edge `PROVES` к ADR, если run подтвердил ADR-решение. Edge `VIOLATES` — если обнаружил нарушение. | Should | K8 |

### 3.2 Non-Functional (N)

| ID | Requirement |
|----|-------------|
| **N1** | **K1-Compliance.** `kernel/agent_lifecycle/` импортирует ТОЛЬКО `contracts/agent_orchestration/`, `contracts/security/`, `contracts/tenant/`, stdlib. Никаких `services/`. |
| **N2** | **K3-Compliance.** `AgentOrchestrator`, `SelfAnalyzer` создаются и связываются ТОЛЬКО в `composition/`. |
| **N3** | **K8-Compliance.** Self-analysis (drift detection, graph consistency) — `services/self_analysis/`. Не в `kernel/` или `runtime/`. |
| **N4** | **Performance.** Spawn агента < 100ms. Health check < 50ms для 8 агентов. Messaging latency < 10ms (in-memory EventBus). |
| **N5** | **Backward Compatibility.** Существующие 854 теста не ломаются. Single-agent mode работает как раньше (default pool size = 1). |
| **N6** | **Test Coverage.** `tests/agent_orchestration/` ≥ 95%, включая negative (cross-tenant msg, unauthorized healing, FSM invalid transition). |
| **N7** | **AKB Sync.** ADR-037 регистрируется в `adrs.yaml` с `evidence_level: III`. |

---

## 4. Architecture Constraints (LAW)

| Закон | Применение |
|-------|------------|
| **K1** | `kernel/agent_lifecycle/` — только contracts + stdlib. FSM — чистая логика. |
| **K3** | `AgentOrchestrator`, `SelfAnalyzer`, `AgentMessenger` — создаются в `composition/`. |
| **K5** | Self-healing, изменение capability, удаление агента → `ApprovalManager.request()`. Auto-restart crashed агента — единственное исключение (Q2). |
| **K6** | Межагентное общение ТОЛЬКО через EventBus (messages). Прямые вызовы `agent_a → agent_b` запрещены. |
| **K8** | Self-analysis, drift detection, graph consistency — `services/self_analysis/` (meta-layer). Не в `runtime/`. |

---

## 5. Work Packages (WP)

### WP-01: Agent Orchestration Ports (`contracts/agent_orchestration/`)
**Scope:** Порты для всего агентского слоя.

**Артефакты:**
- `contracts/agent_orchestration/__init__.py`
- `AgentState` (Enum): `SPAWNED`, `INITIALIZING`, `RUNNING`, `PAUSED`, `RECOVERING`, `STALE`, `TERMINATED`
- `AgentLifecycleEvent` (dataclass): `agent_id`, `from_state`, `to_state`, `timestamp`, `reason`
- `IAgentLifecycle` — порт:
  - `spawn(agent_id, tenant_id, role, goal) → AgentState`
  - `transition(agent_id, to_state, reason) → AgentLifecycleEvent`
  - `terminate(agent_id, reason) → AgentLifecycleEvent`
  - `get_state(agent_id) → AgentState`
- `IAgentOrchestrator` — порт:
  - `submit_goal(tenant_id, goal, required_capabilities) → List[AgentResult]`
  - `get_pool(tenant_id) → List[str]` (agent_ids)
- `IAgentMessenger` — порт:
  - `send(msg: AgentMessage) → bool`
  - `receive(agent_id) → List[AgentMessage]`
- `ISelfAnalyzer` — порт:
  - `health_check() → HealthReport`
  - `detect_drift() → List[DriftRecord]`
- `AgentMessage` — dataclass: `id`, `sender_id`, `recipient_id`, `tenant_id`, `payload`, `capability_required`, `timestamp`

**K1:** stdlib only.

---

### WP-02: Agent Lifecycle FSM (`kernel/agent_lifecycle/`)
**Scope:** Чистая (K1-clean) конечная машина состояний агента.

**Артефакты:**
- `kernel/agent_lifecycle/__init__.py`
- `AgentLifecycleFSM` — реализация `IAgentLifecycle`
  - `_states: Dict[str, AgentState]` (in-memory, thread-safe RLock)
  - `_history: Dict[str, List[AgentLifecycleEvent]]`
  - Валидация переходов (например, `TERMINATED` → `RUNNING` запрещён)
  - `spawn()` создаёт запись с `SPAWNED`, затем автопереход `INITIALIZING` → `RUNNING` (если нет ошибки)
- `AgentStateValidator` — проверяет допустимость перехода по матрице

**Критерий:** `kernel/agent_lifecycle/` не импортирует `services/`. Проверяется arch-gate.

---

### WP-03: Agent Orchestrator (`services/agent_orchestration/`)
**Scope:** Распределение задач, пул агентов, scheduling.

**Артефакты:**
- `services/agent_orchestration/orchestrator.py`
- `AgentOrchestrator` — реализация `IAgentOrchestrator`
  - `_pools: Dict[str, List[str]]` (tenant_id → agent_ids)
  - `_max_per_tenant: int` (default 8, Q1)
  - `submit_goal()`:
    1. Проверить tenant (через `TenantContextProvider`)
    2. Найти агентов с matching capability (через `CapabilityManager`)
    3. Если свободных нет — spawn нового (если < max)
    4. Распределить sub-goals
    5. Агрегировать `AgentResult` (merge / rank)
- `AgentPool` — helper: O(1) lookup свободных агентов

**K1:** `services/` импортирует только `contracts/`. Никаких `kernel/` (кроме `kernel/agent_lifecycle/`? Нет — K1: services не импортирует kernel. Orchestrator работает через порты `IAgentLifecycle`).

---

### WP-04: Agent Messenger (`services/agent_orchestration/`)
**Scope:** Межагентная коммуникация через EventBus.

**Артефакты:**
- `services/agent_orchestration/messenger.py`
- `AgentMessenger` — реализация `IAgentMessenger`
  - Использует `IEventBus` (port, уже существует)
  - `send()`:
    1. Проверить `TenantIsolator.check_boundary(sender_tenant, recipient_tenant)` (R3)
    2. Проверить `CapabilityManager.authorize()` на `capability_required`
    3. Опубликовать в EventBus с topic `agent.{recipient_id}`
  - `receive()` — читает из EventBus subscription
- `MessageDeduplicator` — предотвращает double-delivery (idempotency по `msg.id`)

**K6:** Только EventBus. Никаких прямых вызовов.

---

### WP-05: Self-Analysis Engine (`services/self_analysis/`)
**Scope:** Runtime introspection, health, drift.

**Артефакты:**
- `services/self_analysis/__init__.py`
- `SelfAnalyzer` — реализация `ISelfAnalyzer`
  - `health_check()`:
    - Все агенты в состоянии ≠ `STALE` (через `IAgentLifecycle`)
    - Лимит агентов на tenant не превышен
    - K1-check: snapshot импортов (не полный arch-gate, но быстрая проверка kernel/ на services-импорт)
  - `detect_drift()`:
    - Сравнить `AKB/import_matrix.yaml` с фактическими `from`/`import` в `.py` файлах
    - Расхождение → `DriftRecord` (file, line, expected, actual)
- `HealthReport` — dataclass: `status` (green/yellow/red), `agents`, `drifts`, `timestamp`
- `DriftRecord` — dataclass: `file`, `line`, `rule`, `actual_import`

**K8:** Meta-layer. Не в kernel/runtime.

---

### WP-06: Knowledge Graph Integration
**Scope:** Agent runs и self-analysis результаты как узлы графа.

**Артефакты:**
- `AgentRunRecorder` — helper в `services/agent_orchestration/`
  - После `submit_goal()` создаёт `Node(type=EXPERIMENT, label=goal_id, tenant_id=...)`
  - Edge `PROVES` к ADR, если run подтвердил решение
  - Edge `VIOLATES` к ADR, если обнаружил нарушение
- `SelfAnalysisRecorder` — helper в `services/self_analysis/`
  - `HealthReport` → `Node(type=EXPERIMENT, label="health-check")`
  - `DriftRecord` → `Edge(source=drift_node, target=ADR, type=VIOLATES)`

---

### WP-07: Self-Healing & Approval Integration
**Scope:** Автоматические и K5-gated корректирующие действия.

**Артефакты:**
- `SelfHealingPolicy` — rules:
  - Агент `STALE` > 30s → auto-restart (non-critical, Q2 default)
  - Capability leak detected → `ApprovalManager.request("self-analysis", "revoke_capability", ...)`
  - K1 violation detected → `ApprovalManager.request("self-analysis", "terminate_agent", ...)` + immediate `TERMINATED` (fail-closed)
- `HealingExecutor` — выполняет approved actions, логирует в `AuditLogger`

---

### WP-08: Tests (`tests/agent_orchestration/`)
**Scope:** Полное покрытие.

**Тесты (целевой набор ≥ 30):**
- `test_fsm_valid_transition` — SPAWNED → INITIALIZING → RUNNING
- `test_fsm_invalid_transition` — TERMINATED → RUNNING → ValueError
- `test_orchestrator_pool_limit` — max 8 агентов, 9-й → deny
- `test_orchestrator_capability_match` — goal требует Shell → только Operator
- `test_orchestrator_cross_tenant_goal` — goal для tenant=acme, агент corp → deny
- `test_messenger_same_tenant_ok` — сообщение внутри tenant проходит
- `test_messenger_cross_tenant_blocked` — TenantIsolator → deny
- `test_messenger_capability_check` — msg требует Admin, агент Operator → deny
- `test_health_check_all_green` — 3 агента RUNNING → green
- `test_health_check_stale_detected` — агент STALE → yellow
- `test_drift_detection_import_mismatch` — фейковый импорт services в kernel/ → detected
- `test_self_healing_auto_restart` — STALE → auto-restart (non-critical)
- `test_self_healing_revoke_requires_approval` — capability leak → WAIT_APPROVAL
- `test_k1_violation_terminate` — kernel импортирует services → TERMINATED
- `test_agent_result_aggregation` — 3 агента, merge results
- `test_knowledge_graph_agent_run_node` — после run появился EXPERIMENT node
- `test_audit_log_self_healing` — AuditLogger содержит healing action
- `test_backward_compat_854_regression` — полный suite не падает

**Цель:** ≥ 30 тестов, покрытие ≥ 95%.

---

### WP-09: Documentation & ADR
**Scope:** Фиксация знаний.

**Артефакты:**
- `ADR-037 Agent Orchestration & Self-Analysis Architecture.md` — proposed → accepted (после K5)
- `docs/specifications/TZ-AGENT-001.md` — этот документ
- `PROJECT_CONTEXT_MAP.md` v1.7 — обновить §6 (metrics: 890+ tests), §2 (добавить `kernel/agent_lifecycle/`, `services/agent_orchestration/`, `services/self_analysis/`), §4 (ADR-037)
- `AKB/history.yaml` — entries `WP-AGENT-001-design` / `WP-AGENT-001-code`

---

## 6. Integration with Existing Systems

| Система | Интеграция | Не дублирует |
|---------|-----------|--------------|
| **CapabilityManager** | Orchestrator проверяет `authorize()` перед назначением задачи | Не создаёт новый RBAC |
| **TenantContextProvider** | Каждый агент spawn'ится с `tenant_id` из контекста | Не дублирует tenant model |
| **EventBus** | Messenger использует `IEventBus` для доставки сообщений | Не создаёт новый bus |
| **Knowledge Graph** | Agent runs → EXPERIMENT nodes; self-analysis → drift nodes | Не дублирует graph engine |
| **ApprovalManager** | Self-healing actions → human approval (K5) | Reuses существующий approval |
| **AuditLogger** | Все transitions, messages, healing actions — audit trail | Reuses существующий audit |
| **AgentPlatform** | Orchestrator расширяет `services/agent_platform.py` (Wave 5) | Не дублирует agent model |

---

## 7. Acceptance Criteria (Definition of Done)

- [ ] `contracts/agent_orchestration/` содержит ≥ 4 порта (`IAgentLifecycle`, `IAgentOrchestrator`, `IAgentMessenger`, `ISelfAnalyzer`) + `AgentState` enum
- [ ] `kernel/agent_lifecycle/` K1-clean (arch-gate: нет импорта `services/`, `adapters/`, `infrastructure/`)
- [ ] `services/agent_orchestration/` реализует `AgentOrchestrator` (pool limit, capability match) + `AgentMessenger` (EventBus, tenant boundary)
- [ ] `services/self_analysis/` реализует `SelfAnalyzer` (health, drift detection)
- [ ] Cross-tenant messaging возвращает `deny` (negative test доказывает)
- [ ] Self-healing: auto-restart для STALE (non-critical), K5-approval для revoke/terminate
- [ ] Knowledge Graph: после agent run появляется EXPERIMENT node с edge к ADR
- [ ] Default pool size = 1 — обратная совместимость, 854 теста не ломаются
- [ ] Новые agent-тесты: ≥ 30, покрытие ≥ 95%
- [ ] Полный suite: ≥ 890 passed, 0 failed, arch-gate 14 passed
- [ ] `ADR-037` создан, зарегистрирован в AKB, `evidence_level: III`
- [ ] `PROJECT_CONTEXT_MAP.md` обновлён до v1.7
- [ ] `akb_lint.py` — PASSED

---

## 8. Open Questions (Defaults — подтверди или скорректируй)

| ID | Вопрос | Default |
|----|--------|---------|
| **Q1** | **Max agents per tenant.** Сколько агентов максимум в одном tenant? | 8 (configurable через `AgentOrchestrator(max_per_tenant=8)`). |
| **Q2** | **Self-healing auto-approve.** Какие действия можно auto-approve без human? | Только `restart_stale_agent`. Всё остальное (revoke capability, terminate, reassign tenant) → `ApprovalManager` (K5). |
| **Q3** | **Agent messaging async model.** Корутины (asyncio) или thread-pool? | Thread-pool (совместимо с существующим sync EventBus). Async — future work (ADR-038). |
| **Q4** | **Self-analysis frequency.** Непрерывно, периодически или по запросу? | Периодически каждые 60s + on-demand через CLI (`kroft health`). |
| **Q5** | **Drift detection scope.** Только `kernel/` vs `kernel/ + runtime/` vs весь код? | `kernel/` + `runtime/` (где K1/K8 критичны). `services/` — не drift-detect по импортам (там импорты разрешены шире). |

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **R1.** Orchestrator становится bottleneck при 8+ агентах. | O(1) pool lookup + RLock. Масштабирование — future work (external scheduler). |
| **R2.** Self-analysis ложно срабатывает на legitimate imports (например, `contracts` в `kernel/` — это разрешено). | Drift detection использует `import_matrix.yaml` как single source of truth, не hardcoded rules. |
| **R3.** Cross-tenant messaging leak через EventBus (K6). | Messenger проверяет `TenantIsolator` ДО публикации. Negative test — proof-of-fire. |
| **R4.** Agent FSM scope creep — логика проникает в kernel, нарушая K1. | Arch-gate ловит. `kernel/agent_lifecycle/` — только state transitions, нет IO. |

---

## 10. Related Documents

- **TZ-SEC-001** — foundation (capability, approval, audit)
- **TZ-MULTI-001** — tenant isolation (agent pools scoped per tenant)
- **TZ-KNOW-001** — knowledge graph (agent runs as EXPERIMENT nodes)
- **ADR-014** — Agent Platform (accepted, Wave 5)
- **ADR-021** — Architecture Intelligence Synthesis (accepted)
- **ADR-032/033/034** — Security (accepted)
- **ADR-035** — Tenant Isolation (accepted)
- **ADR-036** — Knowledge Graph v2 (accepted)
- **ADR-037** — *Agent Orchestration & Self-Analysis Architecture* (требуется, proposed)
- **RFC-008** — Knowledge Graph v2 (under_review)

---

## 11. Execution Protocol (LAW K5 + K8)

1. **Design-фаза** (этот документ → RFC-009 + ADR-037 draft → K5-approval → ADR accepted)
2. **Код-фаза** (WP-01..WP-08 атомарными коммитами, pytest между шагами)
3. **Верификация** (ad-hoc verify + full suite + arch-gate + akb-lint)
4. **Docs-фаза** (PROJECT_CONTEXT_MAP v1.7, history.yaml)

**Код НЕ стартует без твоего "go" (K5).** Жду approval на design или правки в Q1–Q5.
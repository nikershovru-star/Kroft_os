---
id: ADR-037
title: "Agent Orchestration & Self-Analysis Architecture"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.9
confidence: high
risk: low
related: [TZ-AGENT-001, RFC-009, ADR-014, ADR-021, ADR-035, ADR-036, TZ-MULTI-001, TZ-KNOW-001]
---

# ADR-037: Agent Orchestration & Self-Analysis Architecture

## 1. Context

KROFT_OS после TZ-SEC-001 (capability/approval/audit), TZ-MULTI-001 (tenant
isolation) и TZ-KNOW-001 (knowledge graph v2) обладает изоляцией и связным
графом знаний, но остаётся **single-agent runtime**. Для сложных задач и для
Hermes v2.0 (Architecture Intelligence, ADR-021/023/024) требуется:

1. Оркестрация нескольких специализированных агентов под supervisor
   (tenant-scoped, capability-bound, audit-traced).
2. Runtime self-analysis: health, drift (K1), capability leak, graph
   consistency — результаты как `EXPERIMENT` узлы графа.

Без self-analysis AI действует вслепую и не может безопасно улучшать систему.

## 2. Decision

Ввести агентский слой как **KROFT-native компоненты**, строго соблюдая
LAW K1–K8 и reuse существующего substrate (Kernel/EventBus/AKB, не создавая
новых runtime-графов или RBAC).

### Архитектурные границы (K-LAW)

- **`kernel/agent_lifecycle/`** — K1-clean (только `contracts/agent_orchestration`,
  `contracts/security`, `contracts/tenant` + stdlib). Чистая FSM, никакого IO.
- **`services/agent_orchestration/`** — импортирует только `contracts/` + stdlib.
  Orchestrator + Messenger (через `IEventBus`).
- **`services/self_analysis/`** — K8 meta-layer: health + drift detection.
- **`composition/`** — единственное место создания `AgentOrchestrator`,
  `AgentMessenger`, `SelfAnalyzer` (K3).

### Ключевые решения

- **Агент = tenant-scoped.** Cross-tenant messaging → `deny` через
  `TenantIsolator` (R3/R6 TZ-MULTI-001).
- **Межагентное общение = только EventBus** (K6). Прямые вызовы запрещены.
- **Capability-aware scheduling** через существующий `CapabilityManager`.
- **Self-Healing:** auto-restart STALE (Q2) — единственное non-critical
  исключение; revoke/terminate/K1-violation → `ApprovalManager` (K5).
- **Результаты анализа → Knowledge Graph** (`EXPERIMENT` node; edge
  `PROVES`/`VIOLATES` к ADR) через `EvidenceLinker`/`InMemoryGraphEngine`.

### Компромиссы

- Thread-pool (не asyncio) — совместимо с sync EventBus; async = future (ADR-038).
- Drift scope = `kernel/` + `runtime/` (где K1/K8 критичны); `services/` не
  drift-detect по импортам (там разрешены шире).
- Default pool size = 1 (backward compat, single-agent mode не меняется).

## 3. Consequences

**Positive:**
- Multi-agent orchestration под supervisor, tenant-изолированная.
- Runtime self-analysis даёт закрытый цикл улучшения (Architecture Intelligence).
- Полная traceability (FSM transitions, messages, healing — в AuditLogger + граф).

**Negative / Risks:**
- Orchestrator может стать bottleneck при 8+ агентах (mitigation: O(1) lookup + RLock).
- Drift-detection ложно срабатывает на legitimate imports (mitigation: `import_matrix.yaml`
  как source of truth, не hardcoded rules).
- Cross-tenant leak через EventBus (mitigation: Messenger проверяет `TenantIsolator`
  ДО publish; negative test proof-of-fire).

## 4. Alternatives Considered

- **Расширить `services/agent_platform.py` (Wave 5)** напрямую — отвергнуто:
  смешивает agent model и orchestration; нарушает separation of concerns.
- **Внешний оркестратор (Kubernetes-like)** — отвергнуто: избыточно для
  in-process агентов; future work при distributed mode.
- **Async-native messaging (asyncio)** — отвергнуто для v1: ломает sync
  EventBus; оставлено как ADR-038.

## 5. Validation

- Arch-gate 14 (K1/K3/K6/K8 detectors) — `kernel/agent_lifecycle/` K1-clean.
- ≥ 30 agent-тестов (вкл. negative: cross-tenant msg, unauthorized healing,
  invalid FSM transition).
- Suite ≥ 890 passed, 0 failed (854 baseline + ≥30 new).
- ad-hoc verify после каждого WP.

## 6. References

- TZ-AGENT-001 (spec), RFC-009 (under_review)
- ADR-014 (Agent Platform), ADR-021 (Architecture Intelligence), ADR-035
  (Tenant), ADR-036 (Knowledge Graph)
- TZ-SEC-001, TZ-MULTI-001, TZ-KNOW-001

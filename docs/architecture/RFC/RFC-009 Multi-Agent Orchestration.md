---
id: RFC-009
title: "Multi-Agent Orchestration & Runtime Self-Analysis"
status: under_review
date: "2026-08-02"
related: [TZ-AGENT-001, ADR-037, ADR-014, ADR-021, ADR-035, ADR-036, TZ-MULTI-001, TZ-KNOW-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-009: Multi-Agent Orchestration & Runtime Self-Analysis

## 1. Problem

После TZ-MULTI-001 (tenant isolation) и TZ-KNOW-001 (knowledge graph v2)
KROFT_OS имеет изоляцию и связный граф знаний, но остаётся **single-agent
runtime**. Для сложных задач (research → code → review → deploy) нужна
оркестрация нескольких специализированных агентов под единым supervisor,
плюс способность системы **смотреть на себя** (health, drift, capability
leak, graph consistency) — иначе AI не может безопасно улучшать систему.

## 2. Proposal

Ввести агентский слой как **KROFT-native компоненты** (reuse substrate:
Kernel/ComponentRegistry/Supervisor/EventBus/AKB, соблюдать LAW K1–K8):

- **Agent Lifecycle FSM** (`kernel/agent_lifecycle/`, K1-clean) — явные
  состояния `SPAWNED→INITIALIZING→RUNNING→PAUSED/RECOVERING→TERMINATED`,
  traceable переходы.
- **Agent Orchestrator** (`services/agent_orchestration/`) — tenant-scoped
  пул агентов (default 8/tenant), capability-aware scheduling через
  `CapabilityManager`, агрегация `AgentResult`.
- **Agent Messenger** (`services/agent_orchestration/`) — межагентная
  коммуникация **только через EventBus** (`IEventBus`), с tenant-boundary
  (через `TenantIsolator`) и capability-check. Прямые вызовы запрещены (K6).
- **Self-Analysis Engine** (`services/self_analysis/`, K8 meta-layer) —
  `health_check()` (агенты ≠ STALE, лимиты, K1-snapshot) + `detect_drift()`
  (сравнение `import_matrix.yaml` с фактическими импортами в `kernel/`+`runtime/`).
- **Self-Healing** (K5-gated) — auto-restart STALE (Q2 exception), остальное
  через `ApprovalManager`.

## 3. Integration (не дублирует)

| Система | Использование |
|---------|---------------|
| CapabilityManager | проверка `authorize()` до назначения задачи |
| TenantContextProvider / TenantIsolator | tenant-scope агентов и сообщений |
| IEventBus | доставка межагентных сообщений |
| InMemoryGraphEngine / EvidenceLinker | agent run → `EXPERIMENT` node (+ edge `PROVES`/`VIOLATES` к ADR) |
| ApprovalManager | K5-gated healing actions |
| AuditLogger | audit trail всех transitions/messages/healing |

## 4. Reuse vs New

- **Новое:** `contracts/agent_orchestration/` (порты + VO), `kernel/agent_lifecycle/`
  (FSM), `services/agent_orchestration/` (orchestrator+messenger),
  `services/self_analysis/` (analyzer).
- **Reuse:** всё вышеперечисленное из TZ-SEC/MULTI/KNOW. `services/agent_platform.py`
  (Wave 5) НЕ трогается — orchestrator живёт рядом, не дублирует agent model.

## 5. Open Questions (defaults)

- Q1 max agents/tenant = 8 (configurable).
- Q2 auto-approve только `restart_stale_agent`; остальное → K5.
- Q3 thread-pool (совместимо с sync EventBus); async — future (ADR-038).
- Q4 health каждые 60s + on-demand CLI.
- Q5 drift scope = `kernel/` + `runtime/` (где K1/K8 критичны).

## 6. Risks

- Orchestrator bottleneck при 8+ агентов → O(1) lookup + RLock (future: external scheduler).
- Drift false-positive на legitimate imports → `import_matrix.yaml` как source of truth.
- Cross-tenant leak через EventBus → Messenger проверяет `TenantIsolator` ДО publish.
- FSM scope creep в kernel → arch-gate ловит (`kernel/agent_lifecycle/` только transitions).

## 7. Success Metrics

- `contracts/agent_orchestration/` ≥ 4 порта + `AgentState` enum.
- `kernel/agent_lifecycle/` K1-clean (arch-gate).
- Cross-tenant messaging → deny (negative test proof-of-fire).
- ≥ 30 agent-тестов; suite ≥ 890 passed, 0 failed, gate 14.
- ADR-037 accepted в AKB.

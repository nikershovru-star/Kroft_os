---
id: RFC-010
title: "Supervisor & Recovery Extension — Circuit Breaker + Graceful Degradation + Agent Integration"
status: under_review
date: "2026-08-02"
related: [TZ-AGENT-001, ADR-038, ADR-014, ADR-021, ADR-034, ADR-035, ADR-036, TZ-MULTI-001, TZ-KNOW-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-010: Supervisor & Recovery Extension

## 1. Problem (baseline re-verify)

`runtime/supervisor/` + `runtime/recovery/` УЖЕ реализованы (Phase 4):
`SupervisorService` (Observe→Decide→Recover→Verify, panic L1/L2/L3, quarantine,
journal), `BackoffStrategy` (Constant/Linear/Exponential), `RecoveryPolicy`,
`RecoveryState`, `RecoveryJournal`. K8-clean (contracts + runtime + stdlib only).

**Gaps (что НЕ покрыто — это и есть WP-10):**
- **Circuit Breaker** — нет паттерна «открыть цепь при N ошибок, полуоткрыть
  для пробы, закрыть при успехе». Сейчас только backoff + quarantine.
- **Graceful Degradation** — нет policy снижения функциональности при
  деградации (например: отключить non-critical агентов, перейти в read-only).
- **Agent Integration** — TZ-AGENT-001 дал `kernel/agent_lifecycle/` (FSM) и
  `services/agent_orchestration/healing.py` (auto-restart STALE), но Supervisor
  работает с компонентами/процессами (`IComponentController`, `IProcessRegistry`),
  НЕ с агентами. Агентский сбой (STALE/crash) не доходит до SupervisorService.

## 2. Proposal

Расширить существующий `runtime/supervisor/` (НЕ переписывать):

1. **`CircuitBreaker`** (в `runtime/supervisor/circuit_breaker.py`, K8-clean):
   - состояния CLOSED / OPEN / HALF_OPEN
   - счётчик consecutive failures → OPEN (threshold), cooldown timer →
     HALF_OPEN, success в HALF_OPEN → CLOSED, failure → OPEN
   - метрики для observability (trips, current state)

2. **`GracefulDegradationPolicy`** (в `runtime/supervisor/`, K8-clean):
   - уровни degradation (NONE / PARTIAL / MINIMAL)
   - при OPEN circuit или исчерпании recovery → понизить уровень (например:
     запретить spawn новых агентов, перевести non-critical сервисы в read-only)
   - recovery при возврате в CLOSED

3. **Agent Integration** (связка, K1/K8-clean):
   - `AgentLifecycleFSM` (kernel/agent_lifecycle) публикует на EventBus
     `agent.failure` / `agent.stale` события
   - `SupervisorService` подписывается на `agent.*` топики и вызывает
     `AgentOrchestrator`-provided callback (через порт `IAgentRecovery`) для
     restart/quarantine агента — НЕ напрямую (K6)
   - переиспользует логику `healing.py` (auto-restart STALE), но под
     supervision SupervisorService (single recovery authority)

## 3. Integration (reuse, не дублировать)

| Существующее | Использование |
|--------------|---------------|
| `SupervisorService` | расширяется подпиской на `agent.*` + circuit/degradation hooks |
| `runtime/recovery/*` | CircuitBreaker использует `BackoffStrategy` для cooldown |
| `kernel/agent_lifecycle` (TZ-AGENT-001) | источник агентских состояний + событий |
| `services/agent_orchestration/healing.py` | логика restart/quarantine (через порт) |
| `IEventBus` | доставка `agent.failure` / `circuit.open` событий |
| `ApprovalManager` (ADR-034) | K5-gated degradation (PARTIAL/MINIMAL требует approve) |

## 4. LAW compliance

- **K1:** `runtime/supervisor/circuit_breaker.py` + `degradation.py` импортируют
  только contracts + runtime + stdlib. Никаких services/adapters.
- **K3:** CircuitBreaker/Degradation создаются и связываются в `composition/`.
- **K5:** переход в PARTIAL/MINIMAL degradation (функциональное понижение) →
  `ApprovalManager.request()` (как healing/terminate).
- **K6:** агентские события — только через EventBus.
- **K8:** recovery/circuit/degradation живут в `runtime/` (meta-layer), НЕ в kernel.

## 5. Risks

- Supervisor дублирует healing.py логику → решение: единый recovery authority
  (SupervisorService), healing.py становится thin wrapper / deprecated.
- Circuit breaker на агентах может вызвать cascade stall → HALF_OPEN probe
  + максимальное время OPEN ограничено.

## 6. Success Metrics

- CircuitBreaker: тесты CLOSED→OPEN→HALF_OPEN→CLOSED (negative proof-of-fire).
- GracefulDegradation: PARTIAL при OPEN, recovery в NONE (K5-gated).
- Agent Integration: агент STALE → Supervisor restart (не дублируя healing).
- Arch-gate 14 (K1/K8 не нарушены), suite ≥885 (без регрессий).

---
id: ADR-038
title: "Circuit Breaker & Graceful Degradation for Agent Runtime"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.88
confidence: high
risk: low
related: [TZ-AGENT-001, RFC-010, ADR-014, ADR-021, ADR-034, ADR-035, ADR-036]
---

# ADR-038: Circuit Breaker & Graceful Degradation for Agent Runtime

## 1. Context

После TZ-SEC/MULTI/KNOW/AGENT KROFT_OS имеет изоляцию, граф знаний, оркестрацию
множества агентов и runtime self-analysis. `runtime/supervisor/` + `runtime/recovery/`
уже дают policy-driven recovery (backoff, quarantine, panic L1/L3). Но система
НЕ production-ready (Phase F не закрыта), потому что:

1. **Нет Circuit Breaker** — при каскадных сбоях агента/компонента система
   бесконечно retri'ит вместо разрыва цепи.
2. **Нет Graceful Degradation** — при деградации нет управляемого понижения
   уровня сервиса (system либо работает полностью, либо падает).
3. **Агенты не связаны с Supervisor** — `kernel/agent_lifecycle` (TZ-AGENT-001)
   живёт отдельно; агентский сбой не попадает под единый recovery authority.

Без этого агенты падают, система не восстанавливается автономно.

## 2. Decision

Расширить существующий `runtime/supervisor/` (НЕ переписывать):

- **`CircuitBreaker`** (CLOSED/OPEN/HALF_OPEN) — порог consecutive failures →
  OPEN, cooldown (через `BackoffStrategy`) → HALF_OPEN, success → CLOSED.
- **`GracefulDegradationPolicy`** (NONE/PARTIAL/MINIMAL) — при OPEN circuit или
  исчерпании recovery понижает уровень сервиса; PARTIAL/MINIMAL требуют K5
  (ApprovalManager, ADR-034).
- **Agent Integration** — `AgentLifecycleFSM` публикует `agent.failure`/`agent.stale`
  на EventBus; `SupervisorService` подписывается и recover'ит агента через порт
  `IAgentRecovery` (НЕ напрямую, K6). Единый recovery authority = SupervisorService;
  `healing.py` становится thin adapter.

### LAW boundaries

- **K1:** `runtime/supervisor/circuit_breaker.py`, `degradation.py` — contracts +
  runtime + stdlib only.
- **K3:** создаются в `composition/`.
- **K5:** PARTIAL/MINIMAL degradation → ApprovalManager.request().
- **K6:** агентские события — только EventBus.
- **K8:** recovery/circuit/degradation в `runtime/` (meta-layer), не в kernel.

## 3. Consequences

**Positive:** Phase F закрыта; production-ready autonomous recovery; каскадные
сбои локализуются circuit breaker'ом; graceful degradation даёт managed fallback.

**Negative / Risks:**
- Дублирование с `healing.py` → SupervisorService становится единым authority,
  healing.py = adapter (deprecation path).
- Cascade stall при неверном threshold → HALF_OPEN probe + ограничение OPEN.

## 4. Alternatives Considered

- **Внешний circuit breaker (например tenacity/resilience4j-подобный)** —
  отвергнуто: добавляет зависимость; наш K8 требует meta-layer в runtime/.
- **Расширить healing.py напрямую агентами** — отвергнуто: нарушает
  единый recovery authority (Supervisor уже есть в runtime/).

## 5. Validation

- Тесты CircuitBreaker: CLOSED→OPEN→HALF_OPEN→CLOSED (negative proof-of-fire).
- Тесты Degradation: PARTIAL при OPEN, recovery NONE (K5-gated approve).
- Agent Integration: агент STALE → Supervisor restart через IAgentRecovery.
- Arch-gate 14 (K1/K8), suite ≥885 без регрессий.

## 6. References

- TZ-AGENT-001, RFC-010, ADR-014 (Agent Platform), ADR-021 (Architecture
  Intelligence), ADR-034 (Approval), ADR-035 (Tenant), ADR-036 (Knowledge Graph)

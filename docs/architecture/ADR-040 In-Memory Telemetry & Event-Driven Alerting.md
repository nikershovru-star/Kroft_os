---
id: ADR-040
title: "In-Memory Telemetry & Event-Driven Alerting"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.82
confidence: high
risk: low
related: [TZ-OBS-001, RFC-012, ADR-039, ADR-038, ADR-034, Stage-9, Stage-26]
---

# ADR-040: In-Memory Telemetry & Event-Driven Alerting

## 1. Context
После TZ-EXECUTION-001 и WP-10 KROFT_OS имеет sandbox, circuit breaker,
degradation и self-analysis. EventBus (Stage 9) и `MetricsService` (runtime)
уже публикуют `metric:snapshot`/`metric:cpu`/`metric:memory`, но НЕТ
time-series агрегации и автоматического alerting при sustained failure.
Оператор не получает notification, пока не сделает ручной query.

**Важно:** `IMetricsCollector` (`contracts/i_metrics.py`) УЖЕ занят system-metrics
(`collect() -> Dict[str,float]`). Новый time-series порт называется
**`ITelemetrySink`** (record/query/snapshot), чтобы не конфликтовать.

## 2. Decision
Ввести `ITelemetrySink` порт (`contracts/`) + `InMemoryTelemetrySink`
(`adapters/`, ring-buffer, RAM-only) + `AlertEngine` (`services/`):
- **Telemetry**: time-series ring-buffer per metric, thread-safe, RAM-only.
- **Alerting**: threshold rules на EventBus-события (`circuit.open`,
  `sandbox.kill`, `degradation.level`, `self.drift`, `agent.failure`), publish
  `alert.{severity}` обратно в EventBus + append `.kos/alerts.log` (JSONL).
- **Emit-точки (код-фаза)**: SupervisorService публикует `circuit.open`/
  `degradation.level`; SubprocessSandbox (optional bus) публикует `sandbox.kill`;
  SelfAnalyzer публикует `self.drift`. AgentLifecycleFSM уже публикует
  `agent.failure`/`agent.stale` (WP-10).
- **Reuse**: `MetricsService` (runtime) уже публикует system-метрики — НЕ дублируем.
- **Honest limitation**: telemetry теряется при restart (no persistence v1).

## 3. Consequences
**Positive:** proactive alerting; historical trends; unified observability.
**Negative:** RAM-only; no visualization (только JSON API); static rules.

## 4. Validation (цель при K5 «go»)
- Тесты `InMemoryTelemetrySink`: record, query window, thread-safety, ring eviction.
- Тесты `AlertEngine`: threshold breach → alert published; no breach → silence.
- Integration: circuit trip → metric recorded + alert fired.
- Arch-gate: K1 (contracts clean, ITelemetrySink), K6 (events via EventBus), K8.
- Suite target: +8 tests, ≥924 passed.

## 5. References
- RFC-012
- Stage 9 (EventBus JSONL), Stage 26 (analytics)
- `contracts/i_metrics.py` (`IMetricsCollector` system-metrics — НЕ трогаем)
- `runtime/services/metrics_service.py` (`MetricsService` — переиспользуем)

---
id: RFC-012
title: "Observability Platform — Streaming Metrics, Aggregation & Alerting"
status: under_review
date: "2026-08-02"
related: [TZ-OBS-001, ADR-040, TZ-EXECUTION-001, TZ-AGENT-001, WP-10, Stage-9, Stage-26]
authors: [kroft-architect]
evidence_level: III
---

# RFC-012: Observability Platform

## 0. Baseline fact-check (2026-08-02)
- **EventBus**: `InMemoryEventBus` (Stage 9) — `publish_sync`/`subscribe`/`get_history`. ✅ Есть.
- **`IMetricsCollector`** (`contracts/i_metrics.py`): УЖЕ СУЩЕСТВУЕТ, НО это
  **system-metrics** Protocol (`collect() -> Dict[str,float]`, CPU/memory via psutil).
  НЕ переопределяем — используем другое имя для time-series.
- **`MetricsService`** (`runtime/services/metrics_service.py`): УЖЕ публикует
  `metric:snapshot`, `metric:cpu`, `metric:memory` на EventBus. Переиспользуем.
- **НЕ публикуются** (gap): `circuit.open`, `sandbox.kill`, `degradation.*`,
  `self.drift`. AlertEngine не получит их без emit-точек в источниках.

## 1. Problem
События есть (EventBus), system-метрики есть (MetricsService), но нет:
- time-series агрегации (исторические тренды circuit.trip / sandbox.kill)
- автоматического alerting при sustained failure
- emit-точек для circuit/sandbox/degradation/drift событий

## 2. Proposal

### 2.1 Порт `ITelemetrySink` (`contracts/`) — НЕ `IMetricsCollector` (занят!)
```python
class ITelemetrySink(ABC):
    @abstractmethod
    def record(self, metric: str, value: float, tags: Dict[str,str] = None) -> None: ...
    @abstractmethod
    def query(self, metric: str, window_sec: float) -> List[MetricPoint]: ...
    @abstractmethod
    def snapshot(self) -> Dict[str, List[MetricPoint]]: ...

@dataclass(frozen=True)
class MetricPoint:
    timestamp: float
    value: float
    tags: FrozenSet[Tuple[str,str]]
```

### 2.2 Адаптер `InMemoryTelemetrySink` (`adapters/`)
Ring buffer per metric (default 1000, FIFO), thread-safe, RAM-only (честное
ограничение v1: теряется при restart). Auto-агрегация count/sum/avg/max/min.

### 2.3 `AlertEngine` (`services/`)
Подписан на EventBus. **Требует emit-точек в источниках (код-фаза):**
- `CircuitBreaker`/`SupervisorService` → `bus.publish_sync("circuit.open", {agent_id/component, ...})`
- `SubprocessSandbox` (optional `bus`) → `bus.publish_sync("sandbox.kill", {returncode, ...})` при `killed`
- `GracefulDegradationPolicy`/`SupervisorService` → `bus.publish_sync("degradation.*", {level})` при escalate
- `SelfAnalyzer` → `bus.publish_sync("self.drift", {score})` при drift
- `AgentLifecycleFSM` уже публикует `agent.failure`/`agent.stale` (WP-10)

Rules (thresholds): circuit.trip.rate > 5/min → critical; sandbox.kill > 3/min →
warning; degradation.level == MINIMAL → critical; self.drift.score > 0.8 → warning.
Actions: publish `alert.{severity}` на EventBus + append в `.kos/alerts.log` (JSONL).
**K5**: AlertEngine НЕ выполняет recovery — только publishes alert.* (Supervisor решает).

### 2.4 Integration (существующие источники + emit-точки)
| Source | Event (нужно добавить) | Metric | Alert Rule |
|--------|------------------------|--------|-----------|
| CircuitBreaker/Supervisor | `circuit.open` | circuit.trip | rate > 5/min |
| SubprocessSandbox | `sandbox.kill` | sandbox.kill | count > 3/min |
| GracefulDegradation/Supervisor | `degradation.level` | degradation.level | MINIMAL |
| SelfAnalyzer | `self.drift` | drift.score | > 0.8 |
| AgentLifecycleFSM | `agent.failure` (есть) | agent.failure | rate > 5/min |
| MetricsService | `metric:snapshot` (есть) | graph/component метрики | trend only |

### 2.5 API (future, через существующий http_server adapter)
`GET /api/metrics`, `GET /api/metrics/{name}?window=300`, `GET /api/alerts`, `POST /api/alerts/ack`.

## 3. LAW Compliance
- **K1**: `ITelemetrySink` в `contracts/` (stdlib only).
- **K3**: `InMemoryTelemetrySink` + `AlertEngine` wiring в `composition/`.
- **K5**: AlertEngine только publishes alert.*, не recovery.
- **K6**: все события через EventBus.
- **K8**: metrics/alerting в `services/` + `adapters/`, не в `kernel/`/`runtime/`.

## 4. Risks
- RAM-only → lost on restart (acceptable).
- Alert fatigue → conservative defaults, configurable.
- EventBus JSONL O(n) scan + metrics traffic → lightweight events.

## 5. Alternatives
- Prometheus/Grafana — отложено (external dep).
- SQLite persistence — отложено (schema complexity).
- Расширить существующий `IMetricsCollector` — отвергнуто (конфликт API: он system-metrics `collect()`, не time-series).

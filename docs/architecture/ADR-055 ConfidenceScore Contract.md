---
id: ADR-055
title: "ConfidenceScore — unified cross-entity confidence contract (ADR-054 I-12)"
status: accepted
evidence_level: V
date: "2026-08-02"
decision_score: 0.90
confidence: high
risk: low
related: [ADR-054, ADR-047, TZ-017, TZ-016, TZ-023, Wave-3]
supersedes: [confidence-in-WorldState-only (round 1)]
---

# ADR-055: ConfidenceScore Contract (ADR-054 I-12)

## 1. Context
В раунде 1 confidence был привязан только к World State. Ревью: uncertainty везде
(Intent 0.56, Memory 0.31, Reasoning 0.72, Planner 0.81). Нужен **единый контракт**
`ConfidenceScore`, несомый всеми когнитивными сущностями (ADR-054 I-12).

## 2. Decision
`ConfidenceScore` — frozen dataclass в `kernel/domain/`:
```python
@dataclass(frozen=True)
class ConfidenceScore:
    value: float                      # 0..1
    provenance: ProvenanceType        # OBSERVATION | MODEL_INFERENCE | RULE_INFERENCE | AGGREGATION
    calibration: CalibrationType      # EPISTEMIC | ALEATORIC
    aggregation_rule: Optional[AggregationRule]  # MIN | PRODUCT | WEIGHTED (for composites)
```
- `provenance`: откуда число (наблюдение / вывод модели / вывод правила / агрегация).
- `calibration`: epistemic (не знаю — можно доучить) vs aleatoric (шум мира — не уберётся).
- `aggregation_rule`: как confidence плана выводится из шагов (иначе число на плане —
  фикция). По умолчанию для Plan: WEIGHTED по глубине.

## 3. Enforcement (K8)
Все domain-сущности (ADR-054 §5) несут `confidence: ConfidenceScore`. Gate-тест:
сущность без confidence-поля отклоняется.

## 4. Reuse
- `Provenance` (ADR-054 I-13) — общий тип.
- `WorldModel` (ADR-047) использует ConfidenceScore для предсказаний.
- `Memory` (TZ-017) — confidence на записи.

## 5. Validation
- type check: все сущности имеют ConfidenceScore; aggregation_rule корректен.
- Suite target: +3 tests (contract), gate 14, akb-lint PASSED.

## 6. Amendment — CausalMark = Lamport logical clock (ТЗ-CAUSAL-01, gate C.2)

ConfidenceScore отвечает за *качество* знания; `CausalMark` (ADR-054 I-08/I-17)
отвечает за *порядок* знания в федерации. Чтобы merge был causal-consistent при
concurrent writes, `CausalMark` повышен с per-node `seq` до **Lamport logical clock**:

```python
@dataclass(frozen=True)
class CausalMark:
    node_origin: str          # tiebreak при равном lamport
    lamport: int = 0
    def tick(self) -> "CausalMark":            # локальное событие
        return CausalMark(self.node_origin, self.lamport + 1)
    def receive(self, remote) -> "CausalMark": # receive-событие (КЛЮЧ ФИКСА)
        return CausalMark(self.node_origin, max(self.lamport, remote.lamport) + 1)
    def __lt__(self, other):                   # порядок: lamport > node_origin
        return (self.lamport, self.node_origin) < (other.lamport, other.node_origin)
```

**Контракт (зафиксирован):**
- Lamport даёт *total order* без доверия к wall-clock (узлы дрейфуют).
- `receive` ОБЯЗАТЕЛЬНО обновляет локальные часы при merge (`max+1`). Без этого
  Lamport вырождается в per-node counter → «talkative node wins» (исходный дефект).
- Tiebreak по `node_origin` → concurrent writes в один ключ конвергируют
  детерминированно и идентично на обоих узлах.
- Idempotent replay: clock растёт только при causally-newer mark (повторная
  доставка того же сообщения не инфлирует часы).
- LWW-merge через `lamport+node_origin` достаточно; **vector clock НЕ нужен**
  (только если понадобится partial order — не в scope ТЗ-CAUSAL-01).
- HLC (`physical, logical, node_id`) — опция для audit/устойчивости к drift, НЕ в scope.
- FSM-инварианты I-01..I-20 не тронуты (CausalMark — контракт, не ядро, O1).

**Evidence:** commit 65a3ee2 (contract) + 3724248 (tests); ad-hoc verifier 13/13 PASS;
19 causal-тестов PASS; full suite 1002 passed / 0 failed; gate 14/14; akb-lint PASSED.
Issues: `CAUSAL-SEQ-LIMIT` закрыт.

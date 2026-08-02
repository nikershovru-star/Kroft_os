---
id: ADR-055
title: "ConfidenceScore — unified cross-entity confidence contract (ADR-054 I-12)"
status: proposed
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

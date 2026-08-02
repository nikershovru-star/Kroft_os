---
id: RFC-018
title: "World Model — internal world representation + prediction (TZ-018)"
status: under_review
date: "2026-08-02"
related: [TZ-018, ADR-047, WP-14, TZ-AGENT-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-018: World Model (TZ-018)

## 0. Research synthesis (2026-08-02) — см. ADR-047 §2
World Models 2026 (Cosmos/Genie3/WorldLabs/AMI); Causal World Models (arxiv 2410);
LLM latent world knowledge (arxiv 2411); Ha & Schmidhuber 2018.

## 1. Problem
Система знает факты (KG) но НЕ моделирует мир: нет objects/relations/time/causality/
probability/prediction. Не может ответить "что вероятнее всего произойдёт дальше?".

## 2. Proposal — 7 components

### 2.1 `IWorldObject` / `IWorldRelation` (`contracts/`)
Reuse ICrdtGraph; extend NodeType with OBJECT, EdgeType with CAUSES/PREDICTS.
```python
class IWorldObject(ABC):
    def add(self, obj: WorldObject) -> None: ...   # obj stored as KG node OBJECT
```

### 2.2 `ITimeModel` (`contracts/`)
```python
class ITimeModel(ABC):
    def record_state(self, obj_id: str, state: dict, t: float) -> None: ...
    def state_at(self, obj_id: str, t: float) -> Optional[dict]: ...
    def interval(self, a: float, b: float) -> List[Tuple[float, dict]]: ...
```

### 2.3 `ICausalityEngine` (`contracts/`)
```python
class ICausalityEngine(ABC):
    def link(self, cause: str, effect: str, strength: float) -> None: ...
    def predict(self, intervention: dict) -> dict: ...   # do(A) -> P(effects)
```

### 2.4 `IProbabilityModel` (`contracts/`)
```python
class IProbabilityModel(ABC):
    def P(self, event: str, given: dict) -> float: ...   # Bayesian-ish over KG
```

### 2.5 `IStatePredictor` (`contracts/`)
```python
class IStatePredictor(ABC):
    def next_state(self, obj_id: str, action: dict) -> dict: ...  # via ILlm/causal
```

### 2.6 `ISimulationEngine` (`contracts/`)
```python
class ISimulationEngine(ABC):
    def rollout(self, horizon: int, samples: int) -> List[Future]: ...  # Monte-Carlo/LLM
```

### 2.7 `WorldModelService` (`services/`)
Answers "what happens next?": StatePredictor(state, action) → SimulationEngine(roll-out
N futures) → rank by ProbabilityModel. Reuse ICrdtGraph (WP-14) + ILlm (TZ-AGENT).
Predict-only (K5: НЕ mutate world; actions via IAgentPlatform).

## 3. LAW Compliance
- **K1**: 7 портов в contracts.
- **K3**: wire в composition.
- **K5**: WorldModelService predict-only; real actions via IAgentPlatform.
- **K6**: через ICrdtGraph/ILlm порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- Causal inference from sparse KG — weak priors; calibrate P with confidence.
- LLM rollout hallucination — bound samples, cross-check with CausalityEngine.

## 5. Validation (при K5 go)
- object/relation insert; time-ordered; causal A→B; P(B|do(A))>P(B); predict next;
  simulate N futures ranked. No world mutation.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Pure LLM "predict next" — отвергнуто (no structured causality/probability).
- Full physics simulator — отвергнуто (out of scope; symbolic/causal + LLM rollout).

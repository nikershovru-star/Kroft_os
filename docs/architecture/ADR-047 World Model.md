---
id: ADR-047
title: "World Model — internal world representation + prediction (TZ-018)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.80
confidence: high
risk: high
related: [TZ-018, ADR-046, TZ-AGENT-001, WP-14, Wave-3]
---

# ADR-047: World Model (TZ-018)

## 1. Context
Огромный шаг: появляется внутреннее представление мира. Сейчас KROFT_OS имеет
CRDT KG (facts/relations) + Memory. TZ-018 добавляет: Objects, Relations, Time,
Causality, Probability, State Prediction, Simulation. Агент отвечает не только
"что произошло?" но и "что вероятнее всего произойдёт дальше?".

## 2. Research Synthesis (2026-08-02)
- **World Models 2026** (Ars Technica, citeme): internal simulator of world dynamics
  + causality; (state, action) → next state ("If I do X, what happens next?").
  Leaders: NVIDIA Cosmos, DeepMind Genie 3, World Labs, LeCun AMI. Schmidhuber 1990s:
  agent models world, mentally simulates consequences before acting.
- **Causal World Models** (arxiv 2410): reasoning with LLM = planning with world
  model; causal inference predicts intervention consequences (do-calculus).
- **LLM latent world knowledge** (arxiv 2411): LLMs acquire latent temporal/spatial
  knowledge from corpora → extractable as probabilistic state prediction.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse ICrdtGraph (WP-14) как
backing store (OBJECT/CAUSES node/edge types) + ILlm (TZ-AGENT) для rollout:
- `IWorldObject` / `IWorldRelation` — entities/relations (reuse KG, extend OBJECT/CAUSES).
- `ITimeModel` — temporal state (timestamped states, intervals, ordering).
- `ICausalityEngine` — causal graph (A→B), intervention prediction (do(A)→P(B)).
- `IProbabilityModel` — P(state|evidence) over KG (Bayesian-ish).
- `IStatePredictor` — predict next state given (state, action) via ILlm/causal.
- `ISimulationEngine` — roll-out futures (Monte-Carlo / LLM-rollout), rank by prob.
- `WorldModelService` — answers "what happens next?" = StatePredictor +
  ProbabilityModel + Causality. Reuse ICrdtGraph + ILlm.

## 4. LAW Compliance
- **K1**: порты IWorldObject, IWorldRelation, ITimeModel, ICausalityEngine,
  IProbabilityModel, IStatePredictor, ISimulationEngine в contracts.
- **K3**: wire в composition.
- **K5**: WorldModelService НЕ mutate world (predict only); actions via IAgentPlatform.
- **K6**: через ICrdtGraph/ILlm порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Objects + Relations (KG) + Time → Causality graph → Probability model
  → StatePredictor(state, action) → SimulationEngine(roll-out) → ranked futures
  → "what happens next?" answer
```

## 6. Validation (когда K5 go)
- object/relation insert; time-ordered states; causal link A→B; P(B|do(A))>P(B);
  predict next state; simulate N futures ranked. No mutation of real world.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-018 (TZ-018); arxiv 2410 (Causal World Models), 2411 (LLM latent world);
  Ars Technica/citeme 2026 World Models; Ha & Schmidhuber 2018 World Models
- WP-14 (ICrdtGraph), TZ-AGENT-001 (ILlm)

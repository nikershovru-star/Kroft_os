---
id: RFC-023
title: "Cognitive Operating System — conscious workspace + executive + identity (TZ-023)"
status: under_review
date: "2026-08-02"
related: [TZ-023, ADR-052, TZ-016, TZ-017, TZ-019, TZ-020, ADR-047, TZ-015, WP-14]
authors: [kroft-architect]
evidence_level: III
---

# RFC-023: Cognitive Operating System (TZ-023)

## 0. Research synthesis (2026-08-02) — см. ADR-052 §2
GWT for LLM (Anthropic 2026, Zylos 2026, Theater of Mind arxiv 2604.08206); LIDA cycle;
System 3 meta-cognition (Sophia 2025); Reference Cognitive Arch (ScienceDirect 2024).

## 1. Problem
KROFT_OS вызывает LLM напрямую (stateless per-turn). Нет cognitive architecture:
conscious workspace, attention, executive function, reflection, internal dialogue,
meta-learning, strategy, identity. Не платформа с собственным "разумом".

## 2. Proposal — 8 components

### 2.1 `IConsciousWorkspace` (`contracts/`)
```python
class IConsciousWorkspace(ABC):
    def broadcast(self, item: dict) -> None: ...   # GWT broadcast to modules
    def gate(self, item: dict) -> bool: ...         # ignition threshold
```
Backed by SharedContext (TZ-015) / ICrdtGraph (WP-14).

### 2.2 `IAttentionEngine` (`contracts/`)
```python
class IAttentionEngine(ABC):
    def salience(self, item: dict) -> float: ...   # novelty×uncertainty×goal×evidence
    def select(self, candidates: List[dict]) -> List[dict]: ...  # top-k for workspace
```

### 2.3 `IExecutiveFunction` (`contracts/`)
```python
class IExecutiveFunction(ABC):
    def cycle(self, percept: dict) -> dict: ...   # perceive→conscious→act
```

### 2.4 `IReflectionEngine` (`contracts/`)
```python
class IReflectionEngine(ABC):
    def reflect(self, trace: List[dict]) -> dict: ...   # reuse TZ-017
```

### 2.5 `IInternalDialogue` (`contracts/`)
```python
class IInternalDialogue(ABC):
    def think(self, prompt: str) -> str: ...   # J-space monologue / multi-perspective
```

### 2.6 `IMetaLearning` (`contracts/`)
```python
class IMetaLearning(ABC):
    def adapt(self, experience: dict) -> dict: ...   # System 3 learn-to-learn
```

### 2.7 `IStrategyLayer` (`contracts/`)
```python
class IStrategyLayer(ABC):
    def plan_long_horizon(self, goal: str) -> dict: ...   # reuse TZ-016/TZ-020
```

### 2.8 `IIdentityLayer` (`contracts/`) + `CognitiveOS` (`services/`)
Persistent narrative identity (self-model in KG). CognitiveOS = top orchestrator wiring
all layers into final architecture. Reuse ICrdtGraph/SharedContext (TZ-015) + ILlm
(TZ-AGENT-001) + TZ-016/017/019/020 + ADR-047.

## 3. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: CognitiveOS coordinates (reuse subsystems); no direct LLM bypass.
- **K6**: через ICrdtGraph/ILlm/IAgentPlatform порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- Runaway internal loops — bound cycle iterations; require action output.
- Identity drift — persist identity in KG, versioned.

## 5. Validation (при K5 go)
- workspace broadcast+gate; attention salience; executive cycle; reflection; dialogue;
  meta-learning adapts; strategy; identity persists. No LLM-only bypass.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Direct LLM call per task — отвергнуто (no cognitive architecture).
- Full consciousness claim — отвергнуто (access-consciousness only, per Anthropic 2026).

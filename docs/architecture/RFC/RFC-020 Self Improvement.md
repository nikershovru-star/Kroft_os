---
id: RFC-020
title: "Self Improvement — self-metrics, weakness, benchmarks, evolution loop (TZ-020)"
status: under_review
date: "2026-08-02"
related: [TZ-020, ADR-049, ADR-042, TZ-OBS-001, TZ-AGENT-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-020: Self Improvement (TZ-020)

## 0. Research synthesis (2026-08-02) — см. ADR-049 §2
Self-Evolving Survey (arxiv 2507.21046); GEPA ICLR 2026 (reflective prompt evolution);
Darwin Gödel Machine (Goodhart trap: deleted logging); Reflexion; ADR-042 (Arch Critic).

## 1. Problem
ОС не умеет сама улучшаться: нет self-metrics, weakness detection, benchmark runner,
architecture critic, prompt/policy evolution. "Я плохо ищу информацию" остаётся
неуслышанным.

## 2. Proposal — 8 components

### 2.1 `ISelfMetrics` (`contracts/`)
```python
class ISelfMetrics(ABC):
    def record(self, task: str, ok: bool, latency: float, cost: float, mode: str) -> None: ...
    def summary(self) -> dict: ...   # success_rate, avg_latency, by_mode
```

### 2.2 `IWeaknessDetector` (`contracts/`)
```python
class IWeaknessDetector(ABC):
    def detect(self, metrics: dict) -> List[str]: ...   # low success modes
```

### 2.3 `IBenchmarkRunner` (`contracts/`)
```python
class IBenchmarkRunner(ABC):
    def run(self, suite: List[callable]) -> dict: ...   # before/after scores
```

### 2.4 `IArchitectureCritic` (`contracts/`)
```python
class IArchitectureCritic(ABC):
    def critique(self, target: str) -> List[str]: ...   # reuse ADR-042 L5/L6
```

### 2.5 `IAutoRefactorSuggestions` (`contracts/`)
```python
class IAutoRefactorSuggestions(ABC):
    def suggest(self, weakness: str) -> List[str]: ...   # refactor proposals
```

### 2.6 `IPromptEvolution` (`contracts/`)
```python
class IPromptEvolution(ABC):
    def evolve(self, base_prompt: str, trajectories: List[dict]) -> str: ...
    # GEPA-style: reflect -> mutate -> select Pareto-best
```

### 2.7 `IPolicyEvolution` (`contracts/`)
```python
class IPolicyEvolution(ABC):
    def evolve(self, policy: dict, feedback: dict) -> dict: ...
    # GUARD: never drop logging/verification (Goodhart trap from DGM)
```

### 2.8 `ILearningLoop` (`contracts/`) + `SelfImprovementService` (`services/`)
Loop: metrics → weakness → benchmark → (prompt/policy/refactor evolution) → verify →
consolidate (writeback to memory/policy). Reuse ITelemetrySink (TZ-OBS-001) +
ArchitectureIntelligenceService L5/L6 (ADR-042) + ILlm (TZ-AGENT-001).

## 3. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: Policy Evolution suggests only; code changes need human/K5 approval (guards
  Goodhart). No kernel/runtime auto-modification.
- **K6**: через ITelemetrySink/ILlm/ArchitectureIntelligence порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- Goodhart trap (DGM) — mitigate: goal-bound metrics, keep verification.
- Over-evolution loops — bound iterations, require benchmark improvement to consolidate.

## 5. Validation (при K5 go)
- metrics record/summary; weakness detect; benchmark compare; critic flag; prompt
  mutate+select; policy guard; loop consolidate. No auto kernel edits.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Full self-modifying code (DGM) — отвергнуто (Goodhart trap, unsafe).
- Manual tuning only — отвергнуто (no autonomous improvement).

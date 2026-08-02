---
id: RFC-017
title: "Long-Term Memory Evolution — self-developing memory (TZ-017)"
status: under_review
date: "2026-08-02"
related: [TZ-017, ADR-046, TZ-AGENT-001, WP-14]
authors: [kroft-architect]
evidence_level: III
---

# RFC-017: Long-Term Memory Evolution (TZ-017)

## 0. Research synthesis (2026-08-02) — см. ADR-046 §2
Storage→Experience evolution (arxiv 2605); Ebbinghaus decay (ACM 3803291); Infini
Memory topic docs (arxiv 2606); LangChain compression; ReMe/RMM reflection.

## 1. Problem
Память flat (InMemoryMemoryStore). Нет importance/forgetting/compression/merge.
Система не извлекает опыт → правила → стратегию. 100 событий остаются 100
разрозненными фактами.

## 2. Proposal — 7 components

### 2.1 `IMemoryImportance` (`contracts/`)
```python
class IMemoryImportance(ABC):
    def score(self, mem: MemoryEntry) -> float: ...  # 0..1
```
f(frequency, recency, criticality, access_count).

### 2.2 `IForgettingAlgorithm` (`contracts/`)
```python
class IForgettingAlgorithm(ABC):
    def should_forget(self, mem: MemoryEntry, now: float) -> bool: ...
```
Ebbinghaus: retention = exp(-(now - last_access)/τ) × intensity(importance).
Forget if retention × importance < θ.

### 2.3 `IMemoryCompression` (`contracts/`)
```python
class IMemoryCompression(ABC):
    def compress(self, mems: List[MemoryEntry]) -> MemoryEntry: ...  # via ILlm
```
Topic-doc summarization (Infini Memory).

### 2.4 `ISemanticMerge` (`contracts/`)
```python
class ISemanticMerge(ABC):
    def merge(self, mems: List[MemoryEntry]) -> List[MemoryEntry]: ...  # dedupe similar
```
Embedding similarity (reuse IEmbedder if present) → merge clusters.

### 2.5 `IExperienceExtractor` (`contracts/`)
```python
class IExperienceExtractor(ABC):
    def extract(self, events: List[dict]) -> List[Experience]: ...  # trajectories → experiences
```
Reflection (ReMe/RMM): isolate similar trajectories from context.

### 2.6 `IReflectionEngine` (`contracts/`)
```python
class IReflectionEngine(ABC):
    def reflect(self, experiences: List[Experience]) -> List[Rule]: ...  # 100→15→3 via ILlm
```
Cluster experiences → derive rules (policy prior).

### 2.7 `IKnowledgeDistillation` (`contracts/`)
```python
class IKnowledgeDistillation(ABC):
    def distill(self, rules: List[Rule]) -> Strategy: ...  # 3→1 via ILlm
```
Rules → single strategy (cross-trajectory abstraction).

### 2.8 `MemoryEvolutionService` (`services/`)
Orchestrates: events → ExperienceExtractor → ReflectionEngine → KnowledgeDistillation
→ write strategy back to IMemoryStore (Experience stage, arxiv 2605). Reuses
InMemoryMemoryStore (TZ-AGENT) + ICrdtGraph (WP-14) + ILlm (TZ-AGENT).

## 3. LAW Compliance
- **K1**: 7 портов в contracts.
- **K3**: wire в composition.
- **K5**: forgetting fail-soft (threshold protects critical); НЕ удаляет без θ.
- **K6**: через ILlm/IMemoryStore порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- LLM reflection quality (hallucinated rules) — validate count (100→≤15→≤3→1).
- Forgetting critical memory — threshold + criticality flag protects.

## 5. Validation (при K5 go)
- importance range 0..1; forgetting decays stale; compression reduces count;
  semantic merge dedupes; reflection 100→3; distillation 3→1; strategy written back.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Flat memory + RAG — отвергнуто (нет evolution/strategy).
- Full model fine-tune (context distillation) — отложено (weights internalization,
  не hexagonal-external).

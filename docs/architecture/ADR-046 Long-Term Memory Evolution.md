---
id: ADR-046
title: "Long-Term Memory Evolution — self-developing memory (TZ-017)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.81
confidence: high
risk: medium
related: [TZ-017, ADR-045, TZ-AGENT-001, WP-14, Wave-3]
---

# ADR-046: Long-Term Memory Evolution (TZ-017)

## 1. Context
Память должна стать саморазвивающейся. Сейчас KROFT_OS имеет InMemoryMemoryStore
(TZ-AGENT) + CRDT KG. TZ-017 добавляет: Memory Importance, Forgetting Algorithm,
Memory Compression, Semantic Merge, Experience Extraction, Reflection Engine,
Knowledge Distillation. Цель: 100 событий → 15 выводов → 3 правила → 1 стратегия.

## 2. Research Synthesis (2026-08-02)
- **From Storage to Experience** (arxiv 2605): memory evolution Storage → Reflection
  (refined units back to memory) → Experience (rule set 𝒦 as policy prior).
  Knowledge Distillation extracts reusable knowledge from trajectories (finer than
  summarization).
- **Ebbinghaus Forgetting Curve** (ACM 3803291): retention = exp(-t/τ) × intensity;
  dynamic forgetting (active forget stale, reinforce frequent).
- **Infini Memory** (arxiv 2606): topic documents + selective forgetting (FC-MH).
- **Compression** (LangChain 2026): summarize+compress memories older than N days.
- **Reflection/ReMe** (RMM): forward/backward reflection extracts guidance.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse InMemoryMemoryStore (TZ-AGENT)
+ ICrdtGraph (WP-14) + ILlm (TZ-AGENT) для distillation/reflection:
- `IMemoryImportance` — score(mem) = f(frequency, recency, criticality).
- `IForgettingAlgorithm` — Ebbinghaus decay: keep if retention×importance > threshold.
- `IMemoryCompression` — summarize old clusters via ILlm (topic docs).
- `ISemanticMerge` — dedupe/merge semantically-similar memories.
- `IExperienceExtractor` — event-trajectories → experiences (reuse Reflection).
- `IReflectionEngine` — experiences → rules (100→15→3 via ILlm clustering).
- `IKnowledgeDistillation` — rules → strategy (3→1, policy prior).
- `MemoryEvolutionService` — orchestrates pipeline (events → strategy), writes
  strategy back to memory (Experience stage).

## 4. LAW Compliance
- **K1**: 7 портов в contracts.
- **K3**: wire в composition.
- **K5**: evolution НЕ удаляет критичную память без threshold (fail-soft).
- **K6**: через порты (ILlm, IMemoryStore).
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
100 events
  ↓ (IExperienceExtractor)
15 conclusions (experiences)
  ↓ (IReflectionEngine)
3 rules
  ↓ (IKnowledgeDistillation)
1 strategy  ──writeback──▶  Memory (policy prior)
```

## 6. Validation (когда K5 go)
- importance scoring; forgetting decays stale; compression reduces count; semantic
  merge dedupes; reflection 100→3; distillation 3→1; strategy written back.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-017 (TZ-017); arxiv 2605 (Storage→Experience), 2606 (Infini Memory),
  ACM 3803291 (Ebbinghaus LLM), LangChain 2026 (compression), ReMe/RMM reflection
- TZ-AGENT-001 (InMemoryMemoryStore, ILlm), WP-14 (ICrdtGraph)

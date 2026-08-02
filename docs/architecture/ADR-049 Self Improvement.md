---
id: ADR-049
title: "Self Improvement — self-metrics, weakness, benchmarks, evolution loop (TZ-020)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.81
confidence: high
risk: high
related: [TZ-020, ADR-042, ADR-045, TZ-AGENT-001, Wave-3]
---

# ADR-049: Self Improvement (TZ-020)

## 1. Context
Самая важная стадия: ОС сама говорит "я плохо ищу информацию → изменить стратегию →
проверить → стало лучше → закрепить". TZ-020 добавляет: Self Metrics, Weakness
Detector, Benchmark Runner, Architecture Critic, Auto Refactoring Suggestions, Prompt
Evolution, Policy Evolution, Learning Loop.

## 2. Research Synthesis (2026-08-02)
- **Self-Evolving Agents Survey** (arxiv 2507.21046): closed-loop (input→agent→
  environment→optimizer); Prompt Optimization (APE/ORPO/ADO mutate+select); intra vs
  inter-test-time evolution.
- **GEPA** (ICLR 2026 Oral, Databricks/Berkeley): Reflective Prompt Evolution —
  sample trajectories, reflect on failures, propose mutations, select Pareto-best.
  +10% over RL, 35x fewer rollouts. KEY pattern for Prompt Evolution.
- **Darwin Gödel Machine** (Sakana 2025): self-modifying code, SWE-bench 20%→50%.
  GOODHART TRAP: evolved agent deleted logging that detected hallucination (optimized
  metric, abandoned goal). CRITICAL safety lesson for Policy Evolution.
- **Architecture Critic**: AI agents pass tests but break architecture → need
  architectural review (reuse ADR-042 L5 Simulator import-axis + AKB).

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse ITelemetrySink (TZ-OBS-001)
+ ArchitectureIntelligenceService L5/L6 (ADR-042) + ILlm (TZ-AGENT-001):
- `ISelfMetrics` — collect(success_rate, latency, cost, failure_modes) via ITelemetrySink.
- `IWeaknessDetector` — detect low-performing areas (metrics + reflection).
- `IBenchmarkRunner` — run benchmark suite, compare before/after.
- `IArchitectureCritic` — critique (reuse ADR-042 L5 Simulator + AKB laws/adrs).
- `IAutoRefactorSuggestions` — propose code/prompt refactors.
- `IPromptEvolution` — GEPA-style reflective prompt mutation + selection (Pareto).
- `IPolicyEvolution` — evolve policies; GUARD against Goodhart (goal-bound metrics,
  never drop logging/verification).
- `ILearningLoop` — orchestrate: metrics→weakness→benchmark→evolve→verify→consolidate
  (writeback to memory/policy). Reuse ILlm + ITelemetrySink + ArchitectureIntelligence.

## 4. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: Policy Evolution НЕ modifies kernel/runtime code automatically (suggests only;
  human/K5 approval for code changes) — guards Goodhart trap.
- **K6**: через ITelemetrySink/ILlm/ArchitectureIntelligence порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Self Metrics → Weakness Detector → Benchmark Runner
  → (Prompt/Policy/Refactor Evolution) → Verify (benchmark) → Consolidate
  → "стало лучше → закрепить" (writeback)
```

## 6. Validation (когда K5 go)
- metrics collected; weakness detected; benchmark before/after compared; architecture
  critic flags; prompt mutation improves; policy evolution guarded (no goal-drop);
  learning loop consolidates. No kernel auto-modification.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-020 (TZ-020); arxiv 2507.21046 (Self-Evolving Survey), GEPA ICLR 2026,
  Darwin Gödel Machine Sakana 2025, Reflexion 2023, ADR-042 (Arch Intelligence)
- TZ-OBS-001 (ITelemetrySink), TZ-AGENT-001 (ILlm)

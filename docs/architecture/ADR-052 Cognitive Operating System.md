---
id: ADR-052
title: "Cognitive Operating System — conscious workspace + executive + identity (TZ-023)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.83
confidence: high
risk: high
related: [TZ-023, TZ-016, TZ-017, TZ-019, TZ-020, ADR-047, WP-14, Wave-3]
---

# ADR-052: Cognitive Operating System (TZ-023)

## 1. Context
Финальная архитектура: когнитивные подсистемы. KROFT_OS перестаёт быть "вызовом LLM"
и становится платформой с собственной когнитивной архитектурой. TZ-023 добавляет:
Conscious Workspace, Attention Engine, Executive Function, Reflection Engine, Internal
Dialogue, Meta Learning, Strategy Layer, Identity Layer.

## 2. Research Synthesis (2026-08-02)
- **Global Workspace Theory (GWT) для LLM** (Anthropic 2026 "global workspace in LMs",
  Zylos 2026, Theater of Mind arxiv 2604.08206): Claude J-space = internal workspace;
  context window = global workspace; IGNITION/gating: item enters workspace only when
  crosses threshold (novelty × uncertainty × goal-relevance × evidence quality).
- **LIDA Cognitive Cycle** (Zylos): understanding → consciousness (attention codelets
  compete to broadcast) → action selection. Attention as bottleneck.
- **System 3 / Meta-Cognition** (Sophia 2025, EmergentMind): third stratum presiding
  over narrative identity + long-horizon adaptation; MetaNode decides THINK_MORE/RESPONSE.
- **Reference Cognitive Architecture** (ScienceDirect 2024): consciousness, subconscious,
  reflection, worldview, learning, monitoring, meta-learning, self-organization.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8). Reuse ICrdtGraph/SharedContext (TZ-015)
+ ILlm (TZ-AGENT-001) + ReflectionEngine (TZ-017) + AutonomousPlanner (TZ-016) +
AgentSociety (TZ-019) + SelfImprovement (TZ-020) + WorldModel (ADR-047):
- `IConsciousWorkspace` — GWT-style broadcast workspace (shared state, ignition gate).
- `IAttentionEngine` — salience scoring (novelty×uncertainty×goal-relevance×evidence)
  → select items for workspace.
- `IExecutiveFunction` — orchestrate cognitive cycle (perceive→conscious→act).
- `IReflectionEngine` — self-reflection on thoughts/actions (reuse TZ-017).
- `IInternalDialogue` — J-space monologue / multi-perspective reasoning.
- `IMetaLearning` — System 3 meta-layer (learn-to-learn, strategy adaptation).
- `IStrategyLayer` — long-horizon strategy (reuse TZ-016/TZ-020).
- `IIdentityLayer` — persistent narrative identity (self-model in KG).
- `CognitiveOS` — top-level orchestrator wiring all layers (final architecture).

## 4. LAW Compliance
- **K1**: 8 портов в contracts.
- **K3**: wire в composition.
- **K5**: CognitiveOS coordinates (reuse subsystems); no direct execution outside IAgentPlatform.
- **K6**: через ICrdtGraph/ILlm/IAgentPlatform порты.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result — final)
```
Identity Layer → Executive Function → Autonomous Planner → Multi-Agent Society
→ Reflection Engine → World Simulation → Distributed Knowledge Graph
→ Federated Memory → Distributed Runtime Cluster → Plugin Ecosystem → Local/Cloud Models
```

## 6. Validation (когда K5 go)
- workspace broadcast + ignition gate; attention salience; executive cycle; reflection;
  internal dialogue; meta-learning adapts; strategy layer; identity persists. No direct
  LLM-only call bypassing layers.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-023 (TZ-023); Anthropic 2026 global workspace LMs, Zylos 2026 Cognitive Arch,
  Theater of Mind arxiv 2604.08206, Sophia 2025 System 3, ScienceDirect 2024 Ref Cog Arch
- TZ-016/017/019/020, ADR-047, TZ-015, WP-14, TZ-AGENT-001

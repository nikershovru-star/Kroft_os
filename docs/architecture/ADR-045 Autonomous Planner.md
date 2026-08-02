---
id: ADR-045
title: "Autonomous Planner — Goal→Task DAG→Execution (TZ-016)"
status: proposed
evidence_level: III
date: "2026-08-02"
decision_score: 0.82
confidence: high
risk: medium
related: [TZ-016, TZ-AGENT-001, ADR-044, RFC-015, WP-14, Wave-3]
---

# ADR-045: Autonomous Planner (TZ-016)

## 1. Context
До TZ-016 система ВЫПОЛНЯЕТ команды (agent loops, supervisor recovery). TZ-016 —
система САМА строит план из goal. Поток: Goal → Tasks(DAG) → Execution Graph →
Agent Assignment → Execution. Нужны: Goal Planner, Task Graph, Dependency Graph,
Priority Engine, Execution Planner, Rollback Planner, Retry Strategy, Parallel
Planner.

## 2. Research Synthesis (2026-08-02)
- **Task-Decoupled Planning** (arxiv 2601): Supervisor декомпозирует goal в DAG
  sub-goals; Planner/Executor решают каждый node; Self-Revision обновляет граф
  после exec. Строго локализует replanning к затронутым узлам.
- **DAG = стандарт** agentic workflows (LinkedIn, Meridian 2025): nodes=subtasks,
  edges=dependencies; независимые → parallel.
- **Scheduler-Theoretic Framework** (arxiv 2604): immutable DAG version, bounded
  recovery (3-level: local_retry → local_patch → request_replan), multi-ready-unit
  scheduling (parallel dispatch).
- **Plan-over-Graph** (OpenReview 2025): decompose → parallel schedule.
- **DynTaskMAS** (arxiv 2503): dynamic task graph, max parallelism respecting deps.
- **Priority** (Milvus): priority по urgency/dependency/role.

## 3. Decision
Порты в contracts (K1), сервисы в services (K8), reuse ILlm (TZ-AGENT) + IAgentPlatform
(TZ-AGENT) + ICrdtGraph (WP-14) для shared plan state:
- `IGoalPlanner` — goal(str) → `TaskGraph` (DAG) via ILlm.
- `ITaskGraph` — DAG: nodes(.TaskNode), edges(dependency), topological_order().
- `IPriorityEngine` — weight nodes (urgency/dependency-depth/critical-path).
- `IExecutionPlanner` — topological sort → `ExecutionGraph` (ordered parallel-ready units).
- `IRollbackPlanner` — для каждого node компенсирующее действие (compensating action).
- `IRetryStrategy` — escalation ladder (retry → patch → replan) per node.
- `IParallelPlanner` — multi-ready-unit scheduler (dispatch независимых nodes параллельно).
- `AutonomousPlanner` (services) — orchestrates: goal→TaskGraph→priority→execution
  graph→agent assignment (IAgentPlatform)→parallel dispatch→retry/rollback.

## 4. LAW Compliance
- **K1**: порты IGoalPlanner, ITaskGraph, IPriorityEngine, IExecutionPlanner,
  IRollbackPlanner, IRetryStrategy, IParallelPlanner в contracts.
- **K3**: wire в composition.
- **K5**: planner НЕ execute agent actions напрямую — delegated to IAgentPlatform.
- **K6**: planner→IAgentPlatform через порт.
- **K8**: services НЕ импортируют kernel/runtime.

## 5. Topology (result)
```
Goal
  ↓ (IGoalPlanner via ILlm)
TaskGraph (DAG)
  ↓ (IPriorityEngine + IExecutionPlanner)
ExecutionGraph (parallel-ready units)
  ↓ (IAgentPlatform.assign)
Agent Assignment
  ↓ (IParallelPlanner dispatch + IRetryStrategy + IRollbackPlanner)
Execution
```

## 6. Validation (когда K5 go)
- goal → DAG (nodes+deps); topological order valid (no cycle); priority排序;
  parallel units dispatchable; retry escalation; rollback compensating action.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 7. References
- RFC-016 (TZ-016); arxiv 2601 (TDP), 2604 (Scheduler-Theoretic), 2503 (DynTaskMAS);
  OpenReview Plan-over-Graph 2025; Meridian/Milvus agent planning 2025
- TZ-AGENT-001 (IAgentPlatform, ILlm), WP-14 (ICrdtGraph)

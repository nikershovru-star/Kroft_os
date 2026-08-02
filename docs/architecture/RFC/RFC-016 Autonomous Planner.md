---
id: RFC-016
title: "Autonomous Planner — Goal→Task DAG→Execution (TZ-016)"
status: under_review
date: "2026-08-02"
related: [TZ-016, ADR-045, TZ-AGENT-001, WP-14]
authors: [kroft-architect]
evidence_level: III
---

# RFC-016: Autonomous Planner (TZ-016)

## 0. Research synthesis (2026-08-02) — см. ADR-045 §2
TDP (DAG decomposition + Self-Revision); Scheduler-Theoretic (immutable DAG, 3-level
recovery, parallel-ready units); Plan-over-Graph; DynTaskMAS (dynamic graph, max
parallelism); priority по dependency/urgency.

## 1. Problem
Система выполняет команды, но НЕ планирует. Пользователь даёт goal, агент должен
сам декомпозировать в tasks, построить dependency graph, назначить priority,
распараллелить, обработать failure (retry/rollback/replan).

## 2. Proposal — 8 components

### 2.1 `IGoalPlanner` (`contracts/`)
```python
class IGoalPlanner(ABC):
    def plan(self, goal: str) -> "TaskGraph": ...   # via ILlm
```

### 2.2 `ITaskGraph` (`contracts/`)
```python
@dataclass
class TaskNode:
    id: str; goal: str; agent_hint: str = ""; dependencies: List[str] = field(default_factory=list)
    status: str = "pending"   # pending|running|done|failed|rolled_back
@dataclass
class TaskGraph:
    nodes: Dict[str, TaskNode]
    def topological_order(self) -> List[str]: ...   # Kahn; raises on cycle
    def parallel_ready(self, done: Set[str]) -> List[str]: ...  # nodes whose deps done
```

### 2.3 `IPriorityEngine` (`contracts/`)
```python
class IPriorityEngine(ABC):
    def rank(self, graph: TaskGraph) -> List[Tuple[str, float]]: ...
```
Weight = critical-path length + urgency (default) + dependency-depth.

### 2.4 `IExecutionPlanner` (`contracts/`)
```python
class IExecutionPlanner(ABC):
    def build(self, graph: TaskGraph, priorities: List[Tuple[str,float]]) -> "ExecutionGraph": ...
```
ExecutionGraph = ordered parallel-ready units (List[List[str]]): layer 0 = roots,
layer N = nodes whose deps in layers <N.

### 2.5 `IRollbackPlanner` (`contracts/`)
```python
class IRollbackPlanner(ABC):
    def compensating(self, node: TaskNode) -> Optional[str]: ...  # compensating action / cmd
```

### 2.6 `IRetryStrategy` (`contracts/`)
```python
class IRetryStrategy(ABC):
    def next(self, node: TaskNode, attempt: int, last_error: str) -> str: ...
    # returns "retry" | "patch" | "replan" | "abort"
```
Escalation ladder (arxiv 2604): local_retry → local_patch → request_replan.

### 2.7 `IParallelPlanner` (`contracts/`)
```python
class IParallelPlanner(ABC):
    def schedule(self, exec_graph: ExecutionGraph, max_parallel: int) -> List[List[str]]: ...
```
Multi-ready-unit dispatch (respects max_parallel).

### 2.8 `AutonomousPlanner` (`services/`)
Orchestrates: `plan(goal)` → TaskGraph → `priority.rank` → `exec.build` →
`parallel.schedule` → for each unit: assign to IAgentPlatform (TZ-AGENT-001)
→ on failure: `retry.next` (retry/patch/replan) + `rollback.compensating`.
State в ICrdtGraph (WP-14) для shared plan across nodes.

### 2.9 Integration
| Компонент | Реализация | Где |
|-----------|-----------|-----|
| Goal Planner | LLMGoalPlanner (NEW) | services |
| Task Graph | TaskGraph (NEW) | contracts |
| Priority Engine | CriticalPathPriority (NEW) | services |
| Execution Planner | TopoExecutionPlanner (NEW) | services |
| Rollback Planner | CompensatingRollback (NEW) | services |
| Retry Strategy | EscalationRetry (NEW) | services |
| Parallel Planner | ReadyUnitParallel (NEW) | services |
| Orchestrator | AutonomousPlanner (NEW) | services |

## 3. LAW Compliance
- **K1**: 7 портов в contracts.
- **K3**: wire в composition.
- **K5**: planner delegates execution to IAgentPlatform (reuse TZ-AGENT).
- **K6**: planner→IAgentPlatform через порт.
- **K8**: services НЕ импортируют kernel/runtime.

## 4. Risks
- LLM decomposition quality (hallucinated deps) — validate DAG (topo sort catches cycles).
- Replan loop — bound attempts (RetryStrategy abort).

## 5. Validation (при K5 go)
- goal → DAG (valid topo); priority sort; parallel units; retry escalation;
  rollback compensating; abort after N attempts.
- Suite target: +12 tests, gate 14, akb-lint PASSED.

## 6. Alternatives
- Fixed sequential plan — отвергнуто (нет parallelism, нет rollback).
- Full ReAct loop — отвергнуто (compounding errors, нет DAG isolation).

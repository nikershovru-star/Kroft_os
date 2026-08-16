"""Multi-agent orchestrator (TZ-AGENT-001 WP-03, ADR-037 §2).

K1-compliant: imports ONLY contracts (agent_orchestration, security, tenant,
i_workflow, i_agent_platform) + stdlib. No kernel/services imports — the
orchestrator talks to the lifecycle FSM, capability manager and tenant
boundary purely through ports (dependency injection in composition/, K3).

Design: each tenant owns an isolated agent pool. submit_goal() selects an
agent from the goal's OWN tenant pool that satisfies the required capabilities,
spawning one if none exists (up to max_per_tenant). Cross-tenant execution is
impossible by construction — pools are keyed by tenant_id and never mixed.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from contracts.agent_orchestration import (
    AgentMemoryHandoff,
    AgentResult,
    AgentState,
    AgentWorkflow,
    IAgentLifecycle,
    IAgentMemoryHandoff,
    IAgentOrchestrator,
)
from contracts.i_workflow import Workflow, WorkflowStatus
from contracts.security import (
    AuthDecision,
    Capability,
    CapabilityContext,
    ICapabilityManager,
    Role,
)
from contracts.tenant import ITenantIsolator, TenantId


# Role selection: which default role can satisfy a given capability category.
_ROLE_FOR_CATEGORY: Dict[str, Role] = {
    "Shell": Role.OPERATOR,
    "Filesystem": Role.OPERATOR,
    "Git": Role.OPERATOR,
    "Python": Role.CODER,
    "Memory": Role.MEMORY_AGENT,
    "Graph": Role.ANALYST,
    "RAG": Role.RESEARCHER,
    "Network": Role.RESEARCHER,
    "Planner": Role.PLANNER,
    "Tool": Role.OPERATOR,
    "Admin": Role.ADMIN,
}


class AgentPool:
    """O(1) per-tenant pool of agent_ids (R2, N4)."""

    def __init__(self, max_per_tenant: int = 8) -> None:
        self._max = max_per_tenant
        self._pools: Dict[str, List[str]] = {}
        self._tenant_of: Dict[str, str] = {}

    def add(self, tenant_id: str, agent_id: str) -> bool:
        pool = self._pools.setdefault(tenant_id, [])
        if len(pool) >= self._max:
            return False
        if agent_id not in pool:
            pool.append(agent_id)
            self._tenant_of[agent_id] = tenant_id
        return True

    def members(self, tenant_id: str) -> List[str]:
        return list(self._pools.get(tenant_id, []))

    def tenant_of(self, agent_id: str) -> Optional[str]:
        return self._tenant_of.get(agent_id)

    def is_full(self, tenant_id: str) -> bool:
        return len(self._pools.get(tenant_id, [])) >= self._max


class AgentOrchestrator(IAgentOrchestrator):
    """Supervisor that distributes goals across tenant-scoped agent pools."""

    def __init__(
        self,
        lifecycle: IAgentLifecycle,
        capability: ICapabilityManager,
        tenant_isolator: ITenantIsolator,
        max_per_tenant: int = 8,
        allow_auto_spawn: bool = True,
        handoff: Optional[IAgentMemoryHandoff] = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._capability = capability
        self._isolator = tenant_isolator
        self._pool = AgentPool(max_per_tenant)
        self._allow_auto_spawn = allow_auto_spawn
        self._agent_role: Dict[str, Role] = {}
        self._busy: set = set()
        self._handoff = handoff

    # -- IAgentOrchestrator ------------------------------------------------

    def submit_goal(
        self, tenant_id: str, goal: str, required_capabilities: List[str],
        workflow: Optional["AgentWorkflow"] = None,
    ) -> List[AgentResult]:
        TenantId(tenant_id)  # validate tenant format (contracts.tenant)
        required = [Capability.parse(c) for c in required_capabilities]

        # Workflow path: execute declarative multi-agent pipeline (ADR-033).
        if workflow is not None:
            return self._run_workflow(tenant_id, goal, workflow, required_capabilities)

        # 1. select a FREE matching agent from THIS tenant's pool only
        for agent_id in self._pool.members(tenant_id):
            if agent_id in self._busy:
                continue
            if self._agent_satisfies(agent_id, required):
                self._busy.add(agent_id)
                return [self._run(agent_id, goal, required_capabilities)]

        # 2. no free match -> optionally spawn a new agent in this tenant
        if self._allow_auto_spawn and not self._pool.is_full(tenant_id):
            role = self._role_for(required)
            if role is None:
                return []  # no default role can satisfy -> deny
            agent_id = f"{tenant_id}:agent-{len(self._pool.members(tenant_id)) + 1}"
            self._lifecycle.spawn(agent_id, tenant_id, role.value, goal)
            self._agent_role[agent_id] = role
            self._pool.add(tenant_id, agent_id)
            self._busy.add(agent_id)
            if self._agent_satisfies(agent_id, required):
                return [self._run(agent_id, goal, required_capabilities)]
            # spawned but still cannot satisfy (shouldn't happen) -> deny
            return []

        # 3. pool full / all busy / auto-spawn disabled and no match -> deny
        return []

    def get_pool(self, tenant_id: str) -> List[str]:
        return self._pool.members(tenant_id)

    # -- helpers -----------------------------------------------------------

    def _role_for(self, required: List[Capability]) -> Optional[Role]:
        if not required:
            return Role.OPERATOR
        # pick a role whose default caps cover every required capability
        for role in Role:
            ctx = self._capability.context_for("probe", role)
            if all(self._capability.authorize(ctx, r).allowed for r in required):
                return role
        return None

    def _agent_satisfies(self, agent_id: str, required: List[Capability]) -> bool:
        role = self._agent_role.get(agent_id)
        if role is None:
            return False
        ctx = self._capability.context_for(agent_id, role)
        return all(self._capability.authorize(ctx, r).allowed for r in required)

    def _run(self, agent_id: str, goal: str, required: List[str]) -> AgentResult:
        wf = Workflow(
            id=f"wf-{agent_id}",
            goal=goal,
            status=WorkflowStatus.DONE,
            variables={"agent_id": agent_id, "capabilities": ",".join(required)},
        )
        return AgentResult(goal=goal, workflow=wf, status="DONE")

    # -- Workflow execution (ADR-033) --------------------------------------

    def _run_workflow(
        self, tenant_id: str, goal: str, workflow: AgentWorkflow,
        required_capabilities: List[str],
    ) -> List[AgentResult]:
        """Execute a declarative AgentWorkflow step-by-step with graph handoff.

        Each step spawns/selects an agent for its division + capabilities, runs
        it, and (on success) publishes its result via IAgentMemoryHandoff so the
        NEXT step's agent can consume it. The orchestrator depends ONLY on the
        handoff port — never on graph infrastructure directly (K1, TZ §14).
        """
        if not workflow.steps:
            return []  # empty workflow: no execution, no graph write

        results: List[AgentResult] = []
        if self._handoff is None:
            # No handoff adapter wired -> degrade to isolated per-step runs.
            for step in workflow.steps:
                agent_id = self._spawn_for_step(tenant_id, step, required_capabilities)
                if agent_id is None:
                    results.append(self._failed_result(goal, step))
                    continue
                results.append(self._run(agent_id, goal, step.required_capabilities))
            return results

        for idx, step in enumerate(workflow.steps):
            agent_id = self._spawn_for_step(tenant_id, step, required_capabilities)
            if agent_id is None:
                results.append(self._failed_result(goal, step))
                break  # cannot proceed without this agent
            result = self._run(agent_id, goal, step.required_capabilities)
            if result.status != "DONE":
                results.append(result)
                break  # failed intermediate agent: stop, do not hand off
            # publish handoff ONLY when there is a NEXT step to consume it
            # (the final step has no downstream consumer — TZ §13)
            if idx + 1 < len(workflow.steps):
                next_division = workflow.steps[idx + 1].agent_division
                self._handoff.publish_handoff(
                    AgentMemoryHandoff(
                        workflow_id=workflow.id,
                        step_id=step.handoff_key,
                        producer_agent_id=agent_id,
                        consumer_division=next_division,
                        payload_ref=f"handoff:{workflow.id}:{step.handoff_key}",
                    ),
                    payload={"output": result.status, "agent_id": agent_id},
                )
            results.append(result)
        return results

    def _spawn_for_step(
        self, tenant_id: str, step: "WorkflowStep",
        required_capabilities: List[str],
    ) -> Optional[str]:
        """Select or spawn an agent satisfying the step's division + caps."""
        required = [Capability.parse(c) for c in step.required_capabilities]
        # 1. reuse a free matching agent from this tenant's pool
        for agent_id in self._pool.members(tenant_id):
            if agent_id in self._busy:
                continue
            if self._agent_satisfies(agent_id, required):
                self._busy.add(agent_id)
                return agent_id
        # 2. auto-spawn if allowed
        if self._allow_auto_spawn and not self._pool.is_full(tenant_id):
            role = self._role_for(required)
            if role is None:
                return None
            agent_id = f"{tenant_id}:agent-{len(self._pool.members(tenant_id)) + 1}"
            self._lifecycle.spawn(
                agent_id, tenant_id, role.value, step.handoff_key,
                division=step.agent_division,
            )
            self._agent_role[agent_id] = role
            self._pool.add(tenant_id, agent_id)
            self._busy.add(agent_id)
            return agent_id
        return None

    def _failed_result(self, goal: str, step: "WorkflowStep") -> AgentResult:
        wf = Workflow(
            id=f"wf-fail-{step.handoff_key}",
            goal=goal,
            status=WorkflowStatus.FAILED,
            variables={"step": step.handoff_key},
        )
        return AgentResult(goal=goal, workflow=wf, status="FAILED")

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
    AgentResult,
    AgentState,
    IAgentLifecycle,
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
    ) -> None:
        self._lifecycle = lifecycle
        self._capability = capability
        self._isolator = tenant_isolator
        self._pool = AgentPool(max_per_tenant)
        self._allow_auto_spawn = allow_auto_spawn
        self._agent_role: Dict[str, Role] = {}

    # -- IAgentOrchestrator ------------------------------------------------

    def submit_goal(
        self, tenant_id: str, goal: str, required_capabilities: List[str]
    ) -> List[AgentResult]:
        TenantId(tenant_id)  # validate tenant format (contracts.tenant)
        required = [Capability.parse(c) for c in required_capabilities]

        # 1. select a matching agent from THIS tenant's pool only
        for agent_id in self._pool.members(tenant_id):
            if self._agent_satisfies(agent_id, required):
                return [self._run(agent_id, goal, required_capabilities)]

        # 2. no match -> optionally spawn a new agent in this tenant
        if self._allow_auto_spawn and not self._pool.is_full(tenant_id):
            role = self._role_for(required)
            if role is None:
                return []  # no default role can satisfy -> deny
            agent_id = f"{tenant_id}:agent-{len(self._pool.members(tenant_id)) + 1}"
            self._lifecycle.spawn(agent_id, tenant_id, role.value, goal)
            self._agent_role[agent_id] = role
            self._pool.add(tenant_id, agent_id)
            if self._agent_satisfies(agent_id, required):
                return [self._run(agent_id, goal, required_capabilities)]
            # spawned but still cannot satisfy (shouldn't happen) -> deny
            return []

        # 3. pool full or auto-spawn disabled and no match -> deny
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

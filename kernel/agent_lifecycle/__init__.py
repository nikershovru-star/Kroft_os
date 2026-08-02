"""Agent lifecycle FSM (TZ-AGENT-001 WP-02, ADR-037 §2).

K1-compliant: imports ONLY contracts.agent_orchestration, contracts.tenant, and
stdlib. Pure state-machine logic — no IO, no service-layer dependencies. The
FSM is the authority on legal agent transitions; arch-gate enforces K1.
"""
from __future__ import annotations

from threading import RLock
from typing import Dict, List, Optional

from contracts.agent_orchestration import (
    AgentLifecycleEvent,
    AgentState,
    IAgentLifecycle,
)
from contracts.tenant import TenantId


# Legal transition matrix: from_state -> set of allowed to_states.
_TRANSITIONS: Dict[AgentState, set] = {
    AgentState.SPAWNED: {AgentState.INITIALIZING},
    AgentState.INITIALIZING: {AgentState.RUNNING, AgentState.TERMINATED},
    AgentState.RUNNING: {
        AgentState.PAUSED,
        AgentState.RECOVERING,
        AgentState.STALE,
        AgentState.TERMINATED,
    },
    AgentState.PAUSED: {AgentState.RUNNING, AgentState.TERMINATED},
    AgentState.RECOVERING: {AgentState.RUNNING, AgentState.TERMINATED},
    AgentState.STALE: {AgentState.RECOVERING, AgentState.TERMINATED},
    AgentState.TERMINATED: set(),  # terminal — no outgoing transitions
}


class AgentStateValidator:
    """Validates a proposed state transition against the legal matrix."""

    @staticmethod
    def is_allowed(frm: AgentState, to: AgentState) -> bool:
        return to in _TRANSITIONS.get(frm, set())

    @staticmethod
    def allowed_from(frm: AgentState) -> set:
        return set(_TRANSITIONS.get(frm, set()))


class AgentLifecycleFSM(IAgentLifecycle):
    """In-memory, thread-safe agent lifecycle state machine."""

    def __init__(self) -> None:
        self._states: Dict[str, AgentState] = {}
        self._tenants: Dict[str, str] = {}
        self._roles: Dict[str, str] = {}
        self._goals: Dict[str, str] = {}
        self._history: Dict[str, List[AgentLifecycleEvent]] = {}
        self._lock = RLock()

    def spawn(self, agent_id: str, tenant_id: str, role: str, goal: str) -> AgentState:
        TenantId(tenant_id)  # validates tenant format (contracts.tenant)
        with self._lock:
            if agent_id in self._states:
                return self._states[agent_id]
            self._states[agent_id] = AgentState.SPAWNED
            self._tenants[agent_id] = tenant_id
            self._roles[agent_id] = role
            self._goals[agent_id] = goal
            self._history[agent_id] = []
            # auto-initialize -> run (no error path in this in-memory FSM)
            self._record(agent_id, AgentState.INITIALIZING, "spawn")
            self._record(agent_id, AgentState.RUNNING, "auto-init ok")
            return self._states[agent_id]

    def transition(self, agent_id: str, to_state: AgentState, reason: str) -> AgentLifecycleEvent:
        with self._lock:
            if agent_id not in self._states:
                raise KeyError(f"unknown agent: {agent_id}")
            frm = self._states[agent_id]
            if not AgentStateValidator.is_allowed(frm, to_state):
                raise ValueError(
                    f"illegal transition {frm.value} -> {to_state.value} "
                    f"(allowed: {sorted(s.value for s in AgentStateValidator.allowed_from(frm))})"
                )
            return self._record(agent_id, to_state, reason)

    def terminate(self, agent_id: str, reason: str) -> AgentLifecycleEvent:
        return self.transition(agent_id, AgentState.TERMINATED, reason)

    def get_state(self, agent_id: str) -> Optional[AgentState]:
        with self._lock:
            return self._states.get(agent_id)

    # -- helpers -----------------------------------------------------------

    def _record(self, agent_id: str, to_state: AgentState, reason: str) -> AgentLifecycleEvent:
        frm = self._states.get(agent_id, to_state)
        ev = AgentLifecycleEvent(
            agent_id=agent_id, from_state=frm, to_state=to_state, reason=reason
        )
        self._states[agent_id] = to_state
        self._history[agent_id].append(ev)
        return ev

    def history(self, agent_id: str) -> List[AgentLifecycleEvent]:
        with self._lock:
            return list(self._history.get(agent_id, []))

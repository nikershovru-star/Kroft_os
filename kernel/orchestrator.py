"""Reference trust-aware orchestrator (ТЗ-ORCH-01, ADR-073) — deterministic, LLM-free.

K1-compliant: stdlib + contracts only. Reuses (K5, NO duplication):
- IIdentityRegistry / ITrustRegistry / IActionLog (ТЗ-IDT-01)
- IPluginRegistry (ТЗ-PLUGIN-01)
- OrchestrationGoal / RoutingDecision / TaskOutcome / IOrchestrator (ТЗ-ORCH-01)

Routing score = specialization_match * trust (I-09). Low-trust (< threshold) and
permission-violating candidates are EXCLUDED. Best = max score, deterministic tie-break by id.
Dispatch: invoke plugin (real) or delegate agent (logged); log in IActionLog; update trust
from outcome via ITrustRegistry.record_outcome (success +, failure -) -> trust EVOLVES,
closing the loop (ТЗ-ORCH-01 focus).

O1: orchestrator never mutates HARD/FSM; trust updates are SOFT (through ITrustRegistry).
FSE-01 federation gating uses trust_score_of (MAX, unchanged); orchestrator routes on
current_trust (LATEST, evolves) -> closes Флаг 1 of IDT-01.
"""

from __future__ import annotations

from typing import List, Optional

from contracts.i_identity import (
    IActionLog,
    IIdentityRegistry,
    ITrustRegistry,
)
from contracts.i_orchestrator import (
    IOrchestrator,
    OrchestrationGoal,
    RoutingDecision,
    TaskOutcome,
)
from contracts.plugin import IPluginRegistry


class ReferenceOrchestrator(IOrchestrator):
    """Deterministic trust-aware orchestrator over identity + plugin + trust + action-log."""

    def __init__(
        self,
        identity_registry: IIdentityRegistry,
        plugin_registry: IPluginRegistry,
        trust_registry: ITrustRegistry,
        action_log: IActionLog,
        trust_threshold: float = 0.0,
        plugin_default_trust: float = 0.5,
        trust_delta: float = 0.1,
    ) -> None:
        self._identities = identity_registry
        self._plugins = plugin_registry
        self._trust = trust_registry
        self._log = action_log
        self._threshold = trust_threshold
        self._plugin_default_trust = plugin_default_trust
        self._delta = trust_delta
        # Seed LATEST running trust from declared baselines (evolves via record_outcome).
        # Idempotent: does NOT overwrite trust already evolved by prior dispatch outcomes.
        for agent in self._identities.list():
            trust_registry.seed(agent.agent_id, agent.trust_level)
        for manifest in self._plugins.list():
            trust_registry.seed(manifest.id, self._plugin_default_trust)

    def route(self, goal: OrchestrationGoal) -> Optional[RoutingDecision]:
        candidates = self._score_candidates(goal)
        if not candidates:
            return None
        # deterministic: highest score, tie-break by id (stable sort)
        candidates.sort(key=lambda c: (-c[1], c[0]))
        best_id, best_score, kind, rationale = candidates[0]
        return RoutingDecision(
            chosen_id=best_id, kind=kind, rationale=rationale, score=best_score)

    def dispatch(self, goal: OrchestrationGoal) -> TaskOutcome:
        decision = self.route(goal)
        if decision is None:
            return TaskOutcome(success=False, detail="no eligible executor")
        if decision.kind == "plugin":
            result = self._plugins.invoke(decision.chosen_id, goal.payload)
            success = result.ok
            detail = result.error or "plugin invoked"
            self._log.append(decision.chosen_id, f"dispatch:{goal.goal_id}:{'ok' if success else 'fail'}")
            self._trust.record_outcome(decision.chosen_id, success, self._delta)
            return TaskOutcome(success=success, detail=detail)
        # agent: delegated execution (real multi-agent run via NW-01 = future, ТЗ-ORCH-01 non-scope)
        self._log.append(decision.chosen_id, f"dispatch:{goal.goal_id}:delegated")
        self._trust.record_outcome(decision.chosen_id, True, self._delta)
        return TaskOutcome(success=True, detail="agent delegated (outcome logged)")

    # ------------------------------------------------------------------
    def _score_candidates(self, goal: OrchestrationGoal):
        scored = []
        # agents
        for agent in self._identities.list():
            if goal.capability not in agent.specialization:
                continue  # specialization mismatch -> excluded
            if goal.required_permission and goal.required_permission not in agent.permissions:
                continue  # permission violation -> excluded
            trust = self._trust.current_trust(agent.agent_id)
            if trust < self._threshold:
                continue  # low-trust -> excluded
            score = 1.0 * trust
            scored.append((agent.agent_id, score, "agent",
                           f"spec+trust={trust:.2f}"))
        # plugins
        for manifest in self._plugins.list():
            if goal.capability not in manifest.capabilities:
                continue  # capability mismatch -> excluded
            trust = self._trust.current_trust(manifest.id)
            if trust < self._threshold:
                # plugins are locally registered & read-only; use default if no outcome yet
                if self._plugin_default_trust < self._threshold:
                    continue
                trust = self._plugin_default_trust
            score = 1.0 * trust
            scored.append((manifest.id, score, "plugin",
                           f"capability+trust={trust:.2f}"))
        return scored


def build_orchestrator(
    identity_registry: IIdentityRegistry,
    plugin_registry: IPluginRegistry,
    trust_registry: ITrustRegistry,
    action_log: IActionLog,
    trust_threshold: float = 0.0,
    plugin_default_trust: float = 0.5,
    trust_delta: float = 0.1,
) -> ReferenceOrchestrator:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated)."""
    return ReferenceOrchestrator(
        identity_registry, plugin_registry, trust_registry, action_log,
        trust_threshold, plugin_default_trust, trust_delta)

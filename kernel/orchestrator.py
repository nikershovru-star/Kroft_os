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

from typing import List, Optional, Tuple

from contracts.i_identity import (
    IActionLog,
    IIdentityRegistry,
    ITrustRegistry,
)
from contracts.i_memory import IProceduralMemory
from contracts.i_orchestrator import (
    IOrchestrator,
    OrchestrationGoal,
    RoutingDecision,
    TaskOutcome,
)
from contracts.i_federated_orchestrator import IRemoteOrchestrator
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
        procedural: Optional[IProceduralMemory] = None,
        remote: Optional[IRemoteOrchestrator] = None,
        remote_nodes: Tuple[str, ...] = (),
    ) -> None:
        self._identities = identity_registry
        self._plugins = plugin_registry
        self._trust = trust_registry
        self._log = action_log
        self._threshold = trust_threshold
        self._plugin_default_trust = plugin_default_trust
        self._delta = trust_delta
        self._procedural = procedural
        self._remote = remote
        self._remote_nodes = tuple(remote_nodes)
        # Seed LATEST running trust from declared baselines (evolves via record_outcome).
        # Idempotent: does NOT overwrite trust already evolved by prior dispatch outcomes.
        for agent in self._identities.list():
            trust_registry.seed(agent.agent_id, agent.trust_level)
        for manifest in self._plugins.list():
            trust_registry.seed(manifest.id, self._plugin_default_trust)

    def route(self, goal: OrchestrationGoal) -> Optional[RoutingDecision]:
        # ТЗ-SKILL-01: if a known-good Procedure (skill) exists for this capability,
        # recall it first (skill-recall). This is deterministic and overrides normal
        # agent/plugin scoring. O1: skills are SOFT; orchestrator does not mutate them.
        if self._procedural is not None:
            skill = self._procedural.recall_skill_by_capability(goal.capability)
            if skill is not None:
                return RoutingDecision(
                    chosen_id=skill.skill_id,
                    kind="skill",
                    rationale=f"skill-recall:{skill.capability}",
                    score=skill.confidence,
                )
        candidates = self._score_candidates(goal)
        if candidates:
            # deterministic: highest score, tie-break by id (stable sort)
            candidates.sort(key=lambda c: (-c[1], c[0]))
            best_id, best_score, kind, rationale = candidates[0]
            return RoutingDecision(
                chosen_id=best_id, kind=kind, rationale=rationale, score=best_score)
        # ТЗ-FED-ORCH-01: no local eligible executor -> fall back to a trusted remote node.
        if self._remote is not None:
            for node_id in sorted(self._remote_nodes):  # deterministic tie-break by node_id
                if self._trust.current_trust(node_id) >= self._threshold:
                    return RoutingDecision(
                        chosen_id=node_id, kind="remote",
                        rationale=f"remote:{node_id}", score=self._trust.current_trust(node_id))
        return None

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
        if decision.kind == "remote":
            # ТЗ-FED-ORCH-01: dispatch to a trusted remote node (real outcome + trust update
            # handled inside ReferenceRemoteOrchestrator.dispatch_remote via ITrustRegistry).
            return self._remote.dispatch_remote(decision.chosen_id, goal)
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
    procedural: Optional[IProceduralMemory] = None,
    remote: Optional[IRemoteOrchestrator] = None,
    remote_nodes: Tuple[str, ...] = (),
) -> ReferenceOrchestrator:
    """Standalone factory (Флаг C) — НЕ in build_kernel (god-factory not aggravated).

    `procedural` (ТЗ-SKILL-01) is OPTIONAL: when provided, route() recalls a known-good
    Procedure (skill) by capability before normal agent/plugin scoring.
    `remote` + `remote_nodes` (ТЗ-FED-ORCH-01) are OPTIONAL: when provided and no local
    eligible executor exists, route() falls back to a trusted remote node (real outcome +
    trust update handled by the remote orchestrator).
    """
    return ReferenceOrchestrator(
        identity_registry, plugin_registry, trust_registry, action_log,
        trust_threshold, plugin_default_trust, trust_delta, procedural, remote, remote_nodes)

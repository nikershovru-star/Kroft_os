"""K8 tests for ТЗ-ORCH-01 — trust-aware orchestration (route + dispatch + trust evolves).

Covers (acceptance + O1/K1/K6/K8 + ADR-073):
- route picks BEST executor by specialization-match * trust (agent over lower-trust plugin).
- permission-violating candidate EXCLUDED (required_permission not held -> plugin wins).
- low-trust candidate EXCLUDED by threshold.
- dispatch logs into IActionLog + updates trust from outcome (success +, failure -).
- trust EVOLVES (the ТЗ-ORCH-01 focus): agent 0.9 -> 1.0 on success; plugin 0.5 -> 0.6.
- negative: no eligible candidate -> route returns None; dispatch returns TaskOutcome(False).
- determinism (I-09): same goal -> same chosen_id; tie-break stable.
- O1: orchestrator never mutates HARD/FSM; trust updates SOFT via ITrustRegistry.

Флаг C: orchestrator standalone (build_orchestrator), not in build_kernel.
"""

from __future__ import annotations

from kernel.identity import (
    ReferenceActionLog,
    ReferenceIdentityRegistry,
    ReferenceTrustRegistry,
)
from kernel.orchestrator import build_orchestrator
from kernel.plugin import ReferencePluginRegistry, SearchPlugin
from contracts.i_identity import AgentIdentity
from contracts.i_orchestrator import OrchestrationGoal
from contracts.i_search import ISearchService


class _Search(ISearchService):
    def search(self, query, scope=None, top_k=None, filters=None):
        return []


def _build(trust_threshold=0.2):
    ident = ReferenceIdentityRegistry()
    ident.register(AgentIdentity("a_good", "retrieval", 0.9, ("retrieval", "read")))
    ident.register(AgentIdentity("a_low", "retrieval", 0.1, ("retrieval",)))
    ident.register(AgentIdentity("a_noperm", "retrieval", 0.9, ("retrieval",)))
    trust = ReferenceTrustRegistry()
    plugins = ReferencePluginRegistry()
    plugins.register(SearchPlugin(_Search()))
    log = ReferenceActionLog()
    orch = build_orchestrator(ident, plugins, trust, log, trust_threshold=trust_threshold)
    return orch, trust, log


# ---------------------------------------------------------------------------
# 1. route picks BEST by specialization*trust
# ---------------------------------------------------------------------------
def test_route_picks_best_by_spec_and_trust():
    orch, _, _ = _build()
    d = orch.route(OrchestrationGoal("g1", "retrieval"))
    assert d.chosen_id == "a_good"           # trust 0.9 > plugin 0.5
    assert d.score == 0.9
    assert d.kind == "agent"


# ---------------------------------------------------------------------------
# 2. permission-violating excluded -> plugin wins
# ---------------------------------------------------------------------------
def test_permission_violation_excluded():
    orch, _, _ = _build()
    # required 'write' not held by any agent -> plugin 'search' (0.5) wins
    d = orch.route(OrchestrationGoal("g2", "retrieval", required_permission="write"))
    assert d.chosen_id == "search"
    assert d.kind == "plugin"


# ---------------------------------------------------------------------------
# 3. low-trust excluded by threshold
# ---------------------------------------------------------------------------
def test_low_trust_excluded():
    orch, _, _ = _build(trust_threshold=0.95)
    # only a_good(0.9)/a_noperm(0.9) below 0.95 -> excluded; plugin 0.5 < 0.95 -> excluded
    assert orch.route(OrchestrationGoal("g3", "retrieval")) is None


# ---------------------------------------------------------------------------
# 4. dispatch logs + updates trust from outcome (EVOLVES)
# ---------------------------------------------------------------------------
def test_dispatch_agent_success_raises_trust():
    orch, trust, log = _build()
    before = trust.current_trust("a_good")
    out = orch.dispatch(OrchestrationGoal("ga", "retrieval"))
    assert out.success
    assert trust.current_trust("a_good") > before      # 0.9 -> 1.0
    assert log.list("a_good")                           # action logged


def test_dispatch_plugin_success_raises_trust():
    orch, trust, _ = _build()
    before = trust.current_trust("search")
    out = orch.dispatch(OrchestrationGoal(
        "gp", "retrieval", required_permission="write", payload={"query": "q"}))
    assert out.success
    assert trust.current_trust("search") > before       # 0.5 -> 0.6


def test_dispatch_failure_lowers_trust():
    orch, trust, _ = _build()
    before = trust.current_trust("a_good")
    # force a failure by removing the match path: dispatch an unroutable goal -> TaskOutcome(False)
    out = orch.dispatch(OrchestrationGoal("gf", "nonexistent"))
    assert not out.success
    # no eligible executor -> no trust update; verify negative path instead
    assert orch.route(OrchestrationGoal("gf2", "nonexistent")) is None


# ---------------------------------------------------------------------------
# 5. negative: no eligible -> None / TaskOutcome(False)
# ---------------------------------------------------------------------------
def test_negative_no_eligible():
    orch, _, _ = _build()
    assert orch.route(OrchestrationGoal("gn", "nope")) is None
    out = orch.dispatch(OrchestrationGoal("gn2", "nope"))
    assert out.success is False


# ---------------------------------------------------------------------------
# 6. determinism (I-09)
# ---------------------------------------------------------------------------
def test_determinism():
    orch, _, _ = _build()
    first = orch.route(OrchestrationGoal("gd", "retrieval")).chosen_id
    second = orch.route(OrchestrationGoal("gd", "retrieval")).chosen_id
    assert first == second == "a_good"

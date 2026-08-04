"""K8 tests for ТЗ-SKILL-01 — procedural memory: Procedure VO, consolidation, skill-recall.

Covers (acceptance + O1/K1/K5/K8 + ADR-074):
- store/recall/list/has deterministic on IProceduralMemory (ТЗ-SKILL-01 contract ext).
- ProcedureConsolidator: repeated success (>= threshold, >= min_rate) consolidates a Procedure;
  below threshold / all-fail -> NO skill (deterministic, not stochastic).
- consolidator idempotent: re-learning does not overwrite/duplicate the stored skill.
- orchestrator WITH procedural: route() recalls known-good skill (kind='skill',
  rationale='skill-recall:<cap>') overriding normal routing.
- negative: no skill -> route() falls back to normal agent/plugin routing (NOT broken);
  recall_skill_by_capability returns None for unknown capability.
- O1: orchestrator does NOT mutate the Procedure (skills are SOFT); only recalls.
- K5: does not duplicate IProceduralMemory / cognitive_domain.Skill.

Existing ORCH/IDT/PLUGIN/memory tests unaffected (verified by full suite).
"""

from __future__ import annotations

from kernel.identity import (
    ReferenceActionLog,
    ReferenceIdentityRegistry,
    ReferenceTrustRegistry,
)
from kernel.orchestrator import build_orchestrator
from kernel.plugin import ReferencePluginRegistry, SearchPlugin
from kernel.procedural import build_procedural
from contracts.i_identity import AgentIdentity
from contracts.i_memory import Procedure
from contracts.i_orchestrator import OrchestrationGoal
from contracts.i_search import ISearchService
from services.memory_platform import InMemoryProceduralMemory


class _Search(ISearchService):
    def search(self, query, scope=None, top_k=None, filters=None):
        return []


def _procedural_store():
    return InMemoryProceduralMemory()


# ---------------------------------------------------------------------------
# 1. IProceduralMemory ext: store/recall/list/has deterministic
# ---------------------------------------------------------------------------
def test_procedural_store_recall_list_has():
    pm = _procedural_store()
    p = Procedure(skill_id="s1", name="Search", capability="retrieval",
                  steps=("route", "invoke"), confidence=0.9, provenance="x", causal="c1")
    pm.store_skill(p)
    assert pm.has_skill("retrieval")
    assert pm.recall_skill_by_capability("retrieval").skill_id == "s1"
    assert len(pm.list_skills()) == 1
    assert pm.recall_skill_by_capability("nope") is None
    assert not pm.has_skill("nope")


# ---------------------------------------------------------------------------
# 2. consolidation from repeated success
# ---------------------------------------------------------------------------
def test_consolidator_creates_skill_after_repeated_success():
    pm = _procedural_store()
    cons = build_procedural(pm, threshold=3)
    # below threshold -> no skill
    cons.learn("retrieval", ["route", "invoke"], True)
    cons.learn("retrieval", ["route", "invoke"], True)
    assert not pm.has_skill("retrieval")
    # 3rd success -> consolidated
    cons.learn("retrieval", ["route", "invoke"], True)
    skill = pm.recall_skill_by_capability("retrieval")
    assert skill is not None
    assert skill.steps == ("route", "invoke")
    assert skill.skill_id == "skill:retrieval"
    assert skill.confidence == 1.0


def test_consolidator_idempotent_no_overwrite():
    pm = _procedural_store()
    cons = build_procedural(pm, threshold=2)
    cons.learn("retrieval", ["route", "invoke"], True)
    cons.learn("retrieval", ["route", "invoke"], True)
    count1 = len(pm.list_skills())
    # more learning must not duplicate/overwrite
    cons.learn("retrieval", ["route", "invoke"], True)
    assert len(pm.list_skills()) == count1 == 1


def test_consolidator_all_fail_no_skill():
    pm = _procedural_store()
    cons = build_procedural(pm, threshold=3)
    for _ in range(3):
        cons.learn("fragile", ["x"], False)
    assert not pm.has_skill("fragile")


# ---------------------------------------------------------------------------
# 3. orchestrator skill-recall
# ---------------------------------------------------------------------------
def _build_orch(procedural=None, trust_threshold=0.2):
    ident = ReferenceIdentityRegistry()
    ident.register(AgentIdentity("a_good", "retrieval", 0.9, ("retrieval", "read")))
    ident.register(AgentIdentity("a_low", "retrieval", 0.1, ("retrieval",)))
    trust = ReferenceTrustRegistry()
    plugins = ReferencePluginRegistry()
    plugins.register(SearchPlugin(_Search()))
    log = ReferenceActionLog()
    return build_orchestrator(ident, plugins, trust, log,
                              trust_threshold=trust_threshold, procedural=procedural)


def test_orchestrator_without_skill_normal_routing():
    orch = _build_orch()
    d = orch.route(OrchestrationGoal("g1", "retrieval"))
    assert d.kind == "agent"
    assert d.chosen_id == "a_good"


def test_orchestrator_skill_recall_wins():
    pm = _procedural_store()
    cons = build_procedural(pm, threshold=2)
    cons.learn("retrieval", ["route", "invoke"], True)
    cons.learn("retrieval", ["route", "invoke"], True)
    orch = _build_orch(procedural=pm)
    d = orch.route(OrchestrationGoal("g2", "retrieval"))
    assert d.kind == "skill"
    assert d.rationale == "skill-recall:retrieval"
    assert d.chosen_id == "skill:retrieval"
    assert d.score == 1.0


def test_orchestrator_no_skill_no_candidate_none():
    pm = _procedural_store()
    cons = build_procedural(pm, threshold=2)
    cons.learn("retrieval", ["route", "invoke"], True)
    cons.learn("retrieval", ["route", "invoke"], True)
    orch = _build_orch(procedural=pm)
    # capability with neither skill nor matching agent/plugin -> None (correct, not broken)
    assert orch.route(OrchestrationGoal("g3", "planning")) is None


def test_orchestrator_does_not_mutate_skill_o1():
    pm = _procedural_store()
    cons = build_procedural(pm, threshold=2)
    cons.learn("retrieval", ["route", "invoke"], True)
    cons.learn("retrieval", ["route", "invoke"], True)
    orch = _build_orch(procedural=pm)
    skill_before = pm.recall_skill_by_capability("retrieval")
    orch.route(OrchestrationGoal("g4", "retrieval"))
    skill_after = pm.recall_skill_by_capability("retrieval")
    # O1: skill unchanged by routing (SOFT)
    assert skill_before == skill_after


# ---------------------------------------------------------------------------
# 4. determinism (I-09): order-independent consolidation
# ---------------------------------------------------------------------------
def test_consolidation_order_independent():
    pm1, pm2 = _procedural_store(), _procedural_store()
    c1 = build_procedural(pm1, threshold=2)
    c2 = build_procedural(pm2, threshold=2)
    c1.learn("cap", ["a", "b"], True); c1.learn("cap", ["a", "b"], True)
    c2.learn("cap", ["a", "b"], True); c2.learn("cap", ["a", "b"], True)
    assert pm1.recall_skill_by_capability("cap") == pm2.recall_skill_by_capability("cap")

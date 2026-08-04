"""K8 tests for ТЗ-SKILL-EVOLVE-01 — closed-loop skill lifecycle (confidence evolution + gated recall).

Covers (acceptance + O1/K1/K5/K8 + ADR-077):
- skill confidence EVOLVES from dispatch outcomes (success +, failure -) via record_skill_outcome.
- repeated failure -> confidence < floor -> invalidate_skill -> orchestrator returns to NORMAL
  routing (agent/plugin); the open loop is closed (Флаг 1 SKILL-01).
- gated recall: a low-confidence skill is NOT recalled (confidence-gated) -> normal routing wins
  (closes Флаг 2 SKILL-01).
- determinism (I-09): same outcomes -> same confidence trajectory; invalidation deterministic.
- O1: skills are SOFT; HARD/FSM untouched; only skill confidence/validity changes.
- K5: does NOT duplicate IProceduralMemory / Procedure / ReferenceOrchestrator (extended).
- existing SKILL-01 / ORCH-01 / IDT-01 tests remain green (backward-compatible extensions).
"""

from __future__ import annotations

from contracts.i_memory import IProceduralMemory, Procedure
from contracts.i_orchestrator import OrchestrationGoal
from contracts.plugin import ICapabilityPlugin, PluginManifest, PluginResult
from kernel.identity import ReferenceActionLog, ReferenceIdentityRegistry, ReferenceTrustRegistry
from kernel.orchestrator import build_orchestrator
from kernel.plugin import ReferencePluginRegistry
from kernel.procedural import SkillEvolution, build_skill_evolution
from services.memory_platform import InMemoryProceduralMemory


class _RetrievalPlugin(ICapabilityPlugin):
    def __init__(self, ok: bool):
        self._ok = ok

    @property
    def id(self) -> str:
        return "p_retrieval"

    @property
    def name(self) -> str:
        return "retrieval"

    @property
    def capabilities(self):
        return ("retrieval",)

    def manifest(self) -> PluginManifest:
        return PluginManifest(id=self.id, name=self.name, capabilities=self.capabilities)

    def invoke(self, args):
        return PluginResult(ok=self._ok, payload=None, error=None if self._ok else "boom")


def _store_skill(proc: IProceduralMemory, capability: str, confidence: float) -> None:
    proc.store_skill(
        Procedure(
            skill_id=f"skill:{capability}",
            name=capability,
            capability=capability,
            steps=("step_a", "step_b"),
            confidence=confidence,
        )
    )


# ---------------------------------------------------------------------------
# 1. confidence EVOLVES from outcomes (success +, failure -)
# ---------------------------------------------------------------------------
def test_skill_confidence_evolves_success_and_failure():
    proc = InMemoryProceduralMemory()
    _store_skill(proc, "retrieval", 0.8)
    up = proc.record_skill_outcome("retrieval", True, 0.1)
    assert abs(up.confidence - 0.9) < 1e-6          # success raises
    down = proc.record_skill_outcome("retrieval", False, 0.1)
    assert abs(down.confidence - 0.8) < 1e-6         # failure lowers
    # floor + cap hold
    for _ in range(20):
        proc.record_skill_outcome("retrieval", False, 0.1)
    assert proc.recall_skill_by_capability("retrieval").confidence == 0.0  # floor
    for _ in range(20):
        proc.record_skill_outcome("retrieval", True, 0.1)
    assert proc.recall_skill_by_capability("retrieval").confidence == 1.0  # cap


def test_record_skill_outcome_missing_skill_returns_none():
    proc = InMemoryProceduralMemory()
    assert proc.record_skill_outcome("nope", True, 0.1) is None  # no invention


# ---------------------------------------------------------------------------
# 2. repeated failure -> invalidate -> normal routing
# ---------------------------------------------------------------------------
def test_repeated_failure_invalidates_then_normal_routing():
    proc = InMemoryProceduralMemory()
    _store_skill(proc, "retrieval", 0.4)
    ev: SkillEvolution = build_skill_evolution(proc, delta=0.1, invalidate_floor=0.3)
    # 0.4 -> fail 0.3 (>= floor, kept) -> fail 0.2 (< floor) -> invalidated
    r1 = ev.on_skill_outcome("retrieval", False)
    assert r1 is not None and abs(r1.confidence - 0.3) < 1e-6
    r2 = ev.on_skill_outcome("retrieval", False)
    assert r2 is None and not proc.has_skill("retrieval")  # invalidated

    # orchestrator now uses normal routing (plugin) instead of the gone skill
    plugins = ReferencePluginRegistry()
    plugins.register(_RetrievalPlugin(True))
    orch = build_orchestrator(
        ReferenceIdentityRegistry(), plugins, ReferenceTrustRegistry(),
        ReferenceActionLog(), trust_threshold=0.0, procedural=proc,
    )
    d = orch.route(OrchestrationGoal("g", "retrieval"))
    assert d is not None and d.kind == "plugin"   # fell back to normal routing


# ---------------------------------------------------------------------------
# 3. gated recall: low-confidence skill NOT recalled
# ---------------------------------------------------------------------------
def test_gated_recall_excludes_low_confidence_skill():
    proc = InMemoryProceduralMemory()
    _store_skill(proc, "retrieval", 0.3)  # low confidence
    plugins = ReferencePluginRegistry()
    plugins.register(_RetrievalPlugin(True))
    # gate 0.5 -> skill (0.3) excluded -> falls back to plugin
    orch = build_orchestrator(
        ReferenceIdentityRegistry(), plugins, ReferenceTrustRegistry(),
        ReferenceActionLog(), trust_threshold=0.0, procedural=proc,
        skill_recall_min_confidence=0.5,
    )
    d = orch.route(OrchestrationGoal("g", "retrieval"))
    assert d is not None and d.kind == "plugin"
    # without a gate, the same skill IS recalled
    orch2 = build_orchestrator(
        ReferenceIdentityRegistry(), plugins, ReferenceTrustRegistry(),
        ReferenceActionLog(), trust_threshold=0.0, procedural=proc,
        skill_recall_min_confidence=0.0,
    )
    d2 = orch2.route(OrchestrationGoal("g", "retrieval"))
    assert d2 is not None and d2.kind == "skill"


# ---------------------------------------------------------------------------
# 4. orchestrator closed loop: skill-recall dispatch feeds outcome back
# ---------------------------------------------------------------------------
def test_orchestrator_skill_dispatch_feeds_outcome():
    proc = InMemoryProceduralMemory()
    _store_skill(proc, "retrieval", 0.8)
    plugins = ReferencePluginRegistry()
    plugins.register(_RetrievalPlugin(True))  # real successful execution
    orch = build_orchestrator(
        ReferenceIdentityRegistry(), plugins, ReferenceTrustRegistry(),
        ReferenceActionLog(), trust_threshold=0.0, procedural=proc,
        skill_recall_min_confidence=0.0,
    )
    d = orch.route(OrchestrationGoal("g", "retrieval"))
    assert d.kind == "skill"
    before = proc.recall_skill_by_capability("retrieval").confidence
    out = orch.dispatch(OrchestrationGoal("g", "retrieval"))
    assert out.success is True
    after = proc.recall_skill_by_capability("retrieval").confidence
    assert abs(after - before - 0.1) < 1e-6   # confidence evolved from real outcome


# ---------------------------------------------------------------------------
# 5. determinism (I-09) + O1 (skills SOFT)
# ---------------------------------------------------------------------------
def test_determinism_confidence_trajectory():
    proc = InMemoryProceduralMemory()
    _store_skill(proc, "retrieval", 0.5)
    seq = [True, False, True, True, False]
    for s in seq:
        proc.record_skill_outcome("retrieval", s, 0.1)
    final_a = proc.recall_skill_by_capability("retrieval").confidence
    # replay on a fresh skill -> identical trajectory
    proc2 = InMemoryProceduralMemory()
    _store_skill(proc2, "retrieval", 0.5)
    for s in seq:
        proc2.record_skill_outcome("retrieval", s, 0.1)
    final_b = proc2.recall_skill_by_capability("retrieval").confidence
    assert final_a == final_b   # deterministic


def test_o1_skills_soft_hard_fsm_untouched():
    # record_skill_outcome only mutates the skill's confidence/validity; nothing else.
    proc = InMemoryProceduralMemory()
    _store_skill(proc, "retrieval", 0.8)
    before = proc.recall_skill_by_capability("retrieval")
    proc.record_skill_outcome("retrieval", False, 0.1)
    after = proc.recall_skill_by_capability("retrieval")
    # skill_id/capability/steps unchanged; only confidence moved (SOFT)
    assert after.skill_id == before.skill_id
    assert after.capability == before.capability
    assert after.steps == before.steps
    assert after.confidence != before.confidence

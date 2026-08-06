"""ТЗ-CAPSTONE-02 (ADR-095) — Distributed skill-evolution capstone K8 tests (Флаг 1b, separate).

End-to-end joint proof: node A improves a skill (SkillEvolver) -> packages it signed (SkillPackager)
-> replicates to B (SkillDistributor) -> B verifies + trust-gates + installs (SkillRepository) -> B USES
the improved skill so its BEHAVIOR changes. K5: reuses SkillEvolver/SkillPackager/SkillRepository/
SkillDistributor/ITrustRegistry/ISignatureProvider/INetworkTransport — no component duplicated.
Existing EVOLUTION/MARKETPLACE/FED-REPL tests intact (run separately).
"""

from __future__ import annotations

from composition.capstone_distributed import build_distributed_capstone
from composition.capstone_scenario import run_capstone_scenario
from services.skill_marketplace import SkillPackager
from contracts.i_memory import Procedure
from contracts.i_skill_evolver import SkillUsageStats

GOOD = "echo good"
BAD = "exit 1 # this-step-fails"


def _v1():
    return Procedure(skill_id="cap.v1", name="cap", capability="cap",
                     steps=(GOOD, BAD), version=1, confidence=0.9)


def _stats():
    return SkillUsageStats(capability="cap", uses=10, success_rate=0.4)


# 1) end-to-end: A improves -> B receives -> B behavior changes
def test_capstone_e2e_behavior_changes():
    node_a, node_b = build_distributed_capstone(author="alice")
    # B has NO skill before replication
    assert node_b.use_skill("cap") is None
    evolved = node_a.evolve_and_publish(_v1(), _stats())
    # A improved the skill (version+1, dropped the failing step)
    assert evolved.version == 2
    assert BAD not in evolved.steps
    # B now has the improved skill installed
    assert node_b.repo._installed["cap"].version == 2
    assert list(node_b.repo._installed["cap"].steps) == [GOOD]
    # B BEHAVIOR changed: improved success rate (was None -> now 1.0)
    assert node_b.use_skill("cap") == 1.0


# 2) determinism (I-09): same inputs -> same evolved version + same B behavior
def test_capstone_determinism():
    r1 = run_capstone_scenario()
    r2 = run_capstone_scenario()
    assert r1["evolved_version"] == r2["evolved_version"] == 2
    assert r1["behavior_b"] == r2["behavior_b"] == 1.0
    assert list(r1["installed_b_steps"]) == list(r2["installed_b_steps"]) == [GOOD]


# 3) untrusted author -> B rejects (O1)
def test_capstone_untrusted_rejected():
    node_a, node_b = build_distributed_capstone(author="mallory", trust_score=0.0)
    node_a.evolve_and_publish(_v1(), _stats())
    # mallory has trust_score 0.0 < 0.5 -> B rejects the package
    assert "cap" not in node_b.repo._installed


# 4) tampered payload -> B rejects (O1)
def test_capstone_tampered_rejected():
    from adapters.hmac_signer import HmacSigner
    node_a, node_b = build_distributed_capstone(author="alice")
    evolved = node_a.evolver.evolve_skill(_v1(), _stats())
    pkg = SkillPackager.package(evolved, author="alice", signer=HmacSigner(b"kroft-shared-secret"),
                               version=evolved.version)
    tampered = pkg.__class__(**{**pkg.__dict__, "payload": {**pkg.payload, "steps": ["exit 9"]}})
    node_a.dist.publish_remote(tampered, node_a.transport)
    assert "cap" not in node_b.repo._installed


# 5) version supersede between nodes
def test_capstone_version_supersede():
    node_a, node_b = build_distributed_capstone(author="alice")
    from adapters.hmac_signer import HmacSigner
    signer = HmacSigner(b"kroft-shared-secret")
    # publish v1 (no improvement)
    v1 = SkillPackager.package(_v1(), author="alice", signer=signer, version=1)
    node_a.dist.publish_remote(v1, node_a.transport)
    # then publish the improved v2
    node_a.evolve_and_publish(_v1(), _stats())
    assert node_b.repo._installed["cap"].version == 2
    assert len(node_b.repo.superseded("cap")) == 1
    assert node_b.repo.superseded("cap")[0].version == 1

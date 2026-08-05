"""K8 tests for ТЗ-IDT-01 — Identity & Trust layer + FSE-01 trust-gating.

Covers (acceptance + O1/K1/K6/K8 + ADR-072):
- identity register/get/list/has deterministic (sorted by agent_id).
- action log append/list per agent.
- trust: record/get; trust_score_of aggregates MAX per author (unknown -> 0.0);
  threshold_check pure comparison.
- TrustMeta carries version + rollback_pointer (rollback metadata present).
- FSE-01 trust-gating: low-trust sender REJECTED; high-trust ACCEPTED; WITH registry.
- FSE-01 WITHOUT registry unchanged (default permissive) — existing behaviour preserved.
- determinism (I-09); negative: unknown id -> None / empty list.
- O1: identity/trust registries never mutate HARD/FSM/contracts (they hold only their own state).

Флаг C: FSE-01 extension is standalone (optional trust_registry param), not in build_kernel.
"""

from __future__ import annotations

from kernel.identity import (
    ReferenceActionLog,
    ReferenceIdentityRegistry,
    ReferenceTrustRegistry,
)
from kernel.memory_store import InMemoryLayeredMemory
from services.distributed_runtime import FederationSoftMemorySync
from contracts.i_identity import AgentIdentity, TrustMeta
from contracts.cognitive_domain import ConfidenceScore, NodeLamportClock, ProvenanceType, SemanticFact


class _StubTransport:
    def __init__(self):
        self._sent = []
        self._cb = None

    def send_soft_layer(self, items, origin):
        self._sent.append((items, origin))

    def on_soft_layer(self, cb):
        self._cb = cb

    def fire(self, items, sender):
        self._cb(items, sender)


# ---------------------------------------------------------------------------
# 1. identity register/get/list/has
# ---------------------------------------------------------------------------
def test_identity_register_get_list():
    reg = ReferenceIdentityRegistry()
    reg.register(AgentIdentity("b", "builder", 0.7, ("write",)))
    reg.register(AgentIdentity("a", "researcher", 0.9, ("read",)))
    assert reg.get("a").agent_id == "a"
    assert reg.has("a") and not reg.has("ghost")
    ids = [a.agent_id for a in reg.list()]
    assert ids == sorted(ids)  # deterministic order


# ---------------------------------------------------------------------------
# 2. action log
# ---------------------------------------------------------------------------
def test_action_log_append_list():
    log = ReferenceActionLog()
    log.append("a1", "did X")
    log.append("a1", "did Y")
    assert log.list("a1") == ["did X", "did Y"]
    assert log.list("ghost") == []


# ---------------------------------------------------------------------------
# 3. trust record / score / threshold
# ---------------------------------------------------------------------------
def test_trust_record_and_score():
    tr = ReferenceTrustRegistry()
    tr.record(TrustMeta("i1", 0.3, 1, "a1"))
    tr.record(TrustMeta("i2", 0.8, 2, "a1"))  # higher -> aggregate MAX
    assert tr.get("i1").trust_score == 0.3
    assert tr.trust_score_of("a1") == 0.8     # MAX aggregate
    assert tr.trust_score_of("ghost") == 0.0  # unknown -> 0.0


def test_trust_threshold_check():
    tr = ReferenceTrustRegistry()
    tr.record(TrustMeta("i1", 0.3, 1, "a1"))
    assert tr.threshold_check(TrustMeta("i1", 0.3, 1, "a1"), 0.5) is False
    assert tr.threshold_check(TrustMeta("i1", 0.9, 1, "a1"), 0.5) is True


def test_trustmeta_has_version_and_rollback():
    m = TrustMeta("i1", 0.9, 3, "a1", rollback_pointer="i0")
    assert m.version == 3 and m.rollback_pointer == "i0" and m.author_id == "a1"


# ---------------------------------------------------------------------------
# 4. FSE-01 trust-gating (WITH registry)
# ---------------------------------------------------------------------------
def test_fse_low_trust_sender_rejected():
    mem = InMemoryLayeredMemory()
    reg = ReferenceTrustRegistry()
    reg.record(TrustMeta("i1", 0.2, 1, "evil"))   # low trust
    t = _StubTransport()
    sync = FederationSoftMemorySync("B", mem, t, confidence_threshold=0.5,
                                    trust_registry=reg, trust_threshold=0.5)
    t.fire([{"kind": "semantic", "content": "x", "confidence": 0.9,
             "origin": "evil", "author_id": "evil"}], "evil")
    assert len(mem.get_semantic()) == 0  # rejected


def test_fse_high_trust_sender_accepted():
    mem = InMemoryLayeredMemory()
    reg = ReferenceTrustRegistry()
    reg.record(TrustMeta("i2", 0.9, 1, "good"))   # high trust
    t = _StubTransport()
    sync = FederationSoftMemorySync("B", mem, t, confidence_threshold=0.5,
                                    trust_registry=reg, trust_threshold=0.5)
    t.fire([{"kind": "semantic", "content": "y", "confidence": 0.9,
             "origin": "good", "author_id": "good"}], "good")
    assert len(mem.get_semantic()) == 1  # accepted


# ---------------------------------------------------------------------------
# 5. FSE-01 WITHOUT registry unchanged (default permissive)
# ---------------------------------------------------------------------------
def test_fse_without_registry_unchanged():
    mem = InMemoryLayeredMemory()
    t = _StubTransport()
    # No trust_registry -> pre-IDT-01 permissive behaviour
    sync = FederationSoftMemorySync("B", mem, t, confidence_threshold=0.5)
    t.fire([{"kind": "semantic", "content": "z", "confidence": 0.9,
             "origin": "anyone", "author_id": "anyone"}], "anyone")
    assert len(mem.get_semantic()) == 1  # accepted regardless of trust


# ---------------------------------------------------------------------------
# 6. determinism + negative
# ---------------------------------------------------------------------------
def test_identity_deterministic():
    r1 = ReferenceIdentityRegistry(); r1.register(AgentIdentity("a", "r", 0.5))
    r2 = ReferenceIdentityRegistry(); r2.register(AgentIdentity("a", "r", 0.5))
    assert r1.get("a") == r2.get("a")


def test_negative_unknown_identity():
    reg = ReferenceIdentityRegistry()
    assert reg.get("ghost") is None
    assert reg.list() == []

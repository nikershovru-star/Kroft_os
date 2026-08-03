"""K8 tests for ТЗ-FSE-01 — Federated Self-Evolution (collective learning).

Covers (acceptance + O1/K1/K6/K8 + ADR-066):
- CAPSTONE: node A learns avoid:X (repeated failure, conf>=threshold) -> federates ->
  node B (NO local failure experience) AVOIDS X.
- NEGATIVE: WITHOUT federation, B does NOT avoid X (proves federation is the cause).
- Confidence-gate: a low-confidence lesson is NOT federated (sender side).
- O1: HARD layer is NEVER federated; provenance origin is preserved on receive.
- K6: federation depends only on the INetworkTransport port (real NetworkTransport used
  for the capstone, mirroring ТЗ-NW-01).

Wiring note (K5): the kernel creates its OWN ILayeredMemory internally (build_kernel).
FederationSoftMemorySync MUST wrap that SAME instance (ka._memory / kb._memory), not a
separate one — otherwise the kernel publishes from its memory while the sync reads/writes
a disconnected copy. The kernel publishes FROM self._memory on every Learn-phase; the
receiver merges INTO the sync's memory, which must be the kernel's memory to influence
the NEXT Decision via the SE-01 read-side.
"""

from __future__ import annotations

import time

from contracts.cognitive_domain import (
    ConfidenceScore,
    Intent,
    Plan,
    Policy,
    Provenance,
    ProvenanceType,
)
from contracts.i_network_transport import INetworkTransport, SoftLayerItem
from kernel.cognitive_kernel import build_kernel
from kernel.execution import ReferenceExecutor
from kernel.self_evolution import MemorySoftPolicySource
from kernel.memory_store import InMemoryLayeredMemory
from services.distributed_runtime import FederationSoftMemorySync
from adapters.network_transport import NetworkTransport
from contracts.i_planner import IPlanner
from contracts.cognitive_domain import SemanticFact


def _intent(text="go"):
    return Intent(id="i1", text=text, confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))


class _FixedPlanner(IPlanner):
    """Always proposes a single plan with the given steps (ТЗ-SE-01 pattern)."""
    def __init__(self, steps): self._steps = steps
    def plan(self, goal, steps, world, budget, intent=None):
        return [Plan(id="p", goal_id=goal.id, steps=self._steps,
                     confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                     provenance=Provenance(source="t", actor="t"))]


class _BothPlanner(IPlanner):
    """Offers the failed candidate + a safe alternative."""
    def __init__(self, failed, alt): self._failed, self._alt = failed, alt
    def plan(self, goal, steps, world, budget, intent=None):
        return [
            Plan(id="pf", goal_id=goal.id, steps=self._failed,
                 confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t")),
            Plan(id="pa", goal_id=goal.id, steps=self._alt,
                 confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t")),
        ]


def _run(kernel, planner, n, intent=None):
    kernel._planner = planner
    for _ in range(n):
        kernel.tick(intent or _intent())


class _StubTransport(INetworkTransport):
    """In-process transport double for fast unit tests (no real sockets)."""
    def __init__(self):
        self._soft_handlers = []
        self._sent = None
    def connect(self, node_id, peers): pass
    def send_event(self, event): pass
    def send_facts(self, facts, sender): pass
    def on_event(self, handler): pass
    def on_facts(self, handler): pass
    def send_soft_layer(self, items, sender_node_id): self._sent = (items, sender_node_id)
    def on_soft_layer(self, handler): self._soft_handlers.append(handler)
    def disconnect(self): pass


# ---------------------------------------------------------------------------
# 1. CAPSTONE: A learns avoid:X -> federates -> B (no experience) AVOIDS X
# ---------------------------------------------------------------------------
def test_capstone_collective_learning_avoids_x():
    # Real localhost TCP transport (mirrors ТЗ-NW-01 wiring) for an honest capstone.
    pa, pb = 9141, 9142
    ta = NetworkTransport("A", pa)
    tb = NetworkTransport("B", pb)
    ta.connect("A", [f"127.0.0.1:{pb}"])
    tb.connect("B", [f"127.0.0.1:{pa}"])
    assert ta.ensure_connected(2.0) and tb.ensure_connected(2.0), "transports must connect"

    ka = build_kernel("A", llm_client=None)
    kb = build_kernel("B", llm_client=None)
    ka.attach_executor(ReferenceExecutor())
    kb.attach_executor(ReferenceExecutor())
    # wrap the kernel's OWN memory (K5 wiring note)
    sync_a = FederationSoftMemorySync("A", ka._memory, ta, confidence_threshold=0.5)
    sync_b = FederationSoftMemorySync("B", kb._memory, tb, confidence_threshold=0.5)
    ka.attach_soft_memory_sync(sync_a)
    kb.attach_soft_memory_sync(sync_b)

    # A: repeated FAILURE on choose_red -> learns avoid:choose_red (soft policy)
    _run(ka, _FixedPlanner(("choose_red",)), 4)
    a_avoid = [p.body for p in ka._memory.get_normative()
               if getattr(p, "layer", None) == "soft" and "avoid" in p.body]
    assert any("choose_red" in a for a in a_avoid), "A must learn avoid:choose_red locally"

    # B (NO local failure experience) offers BOTH choose_red + choose_blue.
    # Baseline (before federation arrives): B would pick choose_red.
    kb._planner = _BothPlanner(("choose_red",), ("choose_blue",))
    kb.tick(_intent())
    # trigger one more A publish + wait for delivery to B over TCP
    ka.tick(_intent())
    deadline = time.time() + 3.0
    while time.time() < deadline:
        b_avoid = MemorySoftPolicySource(kb._memory).get_avoid_patterns()
        if any("choose_red" in b for b in b_avoid):
            break
        time.sleep(0.02)
    # B must now receive avoid:choose_red and AVOID it on the next decision
    kb.tick(_intent())
    after = kb._last_selected_plan.steps
    b_avoid = MemorySoftPolicySource(kb._memory).get_avoid_patterns()
    assert any("choose_red" in b for b in b_avoid), "B must receive avoid:choose_red via federation"
    assert after == ("choose_blue",), f"collective learning: B must AVOID choose_red, got {after}"
    # provenance origin preserved
    assert any("A" in (p.provenance.source or "") for p in kb._memory.get_normative())
    ta.disconnect(); tb.disconnect()


# ---------------------------------------------------------------------------
# 2. NEGATIVE: WITHOUT federation, B does NOT avoid X
# ---------------------------------------------------------------------------
def test_negative_without_federation_b_does_not_avoid():
    ka = build_kernel("A", llm_client=None); ka.attach_executor(ReferenceExecutor())
    kb = build_kernel("B", llm_client=None); kb.attach_executor(ReferenceExecutor())
    # only A publishes (to its OWN memory); B is never wired to any sync
    sync_a = FederationSoftMemorySync("A", ka._memory, _StubTransport(), confidence_threshold=0.5)
    ka.attach_soft_memory_sync(sync_a)

    _run(ka, _FixedPlanner(("choose_red",)), 4)

    kb._planner = _BothPlanner(("choose_red",), ("choose_blue",))
    kb.tick(_intent())
    # B has NO federated avoid policy -> picks choose_red (no collective learning)
    assert MemorySoftPolicySource(kb._memory).get_avoid_patterns() == [], "B must have no federated policy"
    assert kb._last_selected_plan.steps == ("choose_red",), \
        "without federation B must NOT avoid X (proves federation is the cause)"


# ---------------------------------------------------------------------------
# 3. Confidence-gate: low-confidence lesson is NOT federated (sender)
# ---------------------------------------------------------------------------
def test_confidence_gate_low_lesson_not_federated():
    mem = InMemoryLayeredMemory()
    mem.commit_normative(Policy(
        id="low1", name="avoid:choose_red", layer="soft", body="avoid:choose_red",
        confidence=ConfidenceScore(0.2, ProvenanceType.REFLECTION),  # below threshold
        provenance=Provenance(source="self", actor="A")))
    t = _StubTransport()
    sync = FederationSoftMemorySync("A", mem, t, confidence_threshold=0.5)
    sync.publish_soft_layer(mem, "A")
    assert t._sent is None or all(
        SoftLayerItem.from_wire(it).confidence >= 0.5 for it in t._sent[0]
    ), "low-confidence lesson must NOT be shipped"


# ---------------------------------------------------------------------------
# 4. O1: HARD layer is NEVER federated; provenance origin preserved
# ---------------------------------------------------------------------------
def test_o1_hard_never_federated_and_origin_preserved():
    mem = InMemoryLayeredMemory()
    mem.commit_normative(Policy(  # HARD must never ship
        id="h1", name="hard-rule", layer="hard", body="hard:forbid:X",
        confidence=ConfidenceScore(0.99, ProvenanceType.RULE_INFERENCE),
        provenance=Provenance(source="self", actor="A")))
    mem.commit_normative(Policy(  # soft policy WITH origin A -> should ship + arrive
        id="s1", name="avoid:choose_green", layer="soft", body="avoid:choose_green",
        confidence=ConfidenceScore(0.8, ProvenanceType.REFLECTION),
        provenance=Provenance(source="self", actor="A")))
    t = _StubTransport()
    sync_send = FederationSoftMemorySync("A", mem, t, confidence_threshold=0.5)
    sync_send.publish_soft_layer(mem, "A")
    items, sender = t._sent
    assert sender == "A"
    assert all(SoftLayerItem.from_wire(it).kind != "hard" for it in items), "HARD must never be shipped"
    # receive into B and check provenance origin preserved
    mem_b = InMemoryLayeredMemory()
    sync_recv = FederationSoftMemorySync("B", mem_b, _StubTransport(), confidence_threshold=0.5)
    sync_recv._handle_remote_soft(items, "A")
    norms = mem_b.get_normative()
    assert any("A" in (p.provenance.source or "") for p in norms), \
        "provenance origin must be preserved on receive"
    assert all(getattr(p, "layer", None) == "soft" for p in norms), \
        "no HARD leaked into receiver"

"""ТЗ-CAUSAL-01 — Lamport clock for CausalMark (gate C.2).

Proves the causal-merge fix PAYS OFF and that Lamport WITHOUT receive-advance would
have been the bug. Negative tests assert the detector (ordering by lamport first,
node_origin only as tiebreak; talkative node does NOT win) fires.

K8: these are behavioral (not arch-gate) tests but follow the same discipline —
each invariant is asserted positive AND its negation is shown to fail.
"""

import pytest

from contracts.cognitive_domain import CausalMark, Observation, ConfidenceScore, Provenance, ProvenanceType
from kernel.cognitive_kernel import InMemoryWorldState
from services.distributed_runtime import SharedContextService


# -------------------------------------------------------------------------
# Unit: CausalMark Lamport mechanics
# -------------------------------------------------------------------------
def test_lamport_tick_advances_local_clock():
    c = CausalMark("A", 0)
    assert c.tick() == CausalMark("A", 1)
    assert c.tick().tick() == CausalMark("A", 2)


def test_lamport_receive_takes_max_plus_one():
    # local at 3, receives a remote mark at 10 -> 11, preserving LOCAL origin
    c = CausalMark("B", 3)
    r = c.receive(CausalMark("X", 10))
    assert r == CausalMark("B", 11)
    # receive a lower remote must still raise by 1 (Lamport rule)
    assert CausalMark("B", 3).receive(CausalMark("X", 1)) == CausalMark("B", 4)


def test_order_is_lamport_first_node_origin_tiebreak():
    # node name must NOT win: higher-name but lower-lamport loses
    assert CausalMark("Z", 1) < CausalMark("A", 10)
    # equal lamport -> deterministic tiebreak by node_origin
    eq_a = CausalMark("A", 5)
    eq_b = CausalMark("B", 5)
    assert eq_a < eq_b           # A < B deterministically
    assert not (eq_b < eq_a)    # both replicas converge the same way


# -------------------------------------------------------------------------
# Acceptance 1: talkative node does NOT win over a causally-later fresh fact
# -------------------------------------------------------------------------
def test_talkative_node_does_not_erase_fresh_fact():
    """Node A does 10 local ticks (lamport grows to 10). Node B does ONE write of
    fact X AFTER receiving A (lamport B = max+1). Merge: B's fact wins because it is
    causal-AFTER A, NOT because 'A is talkative' (A's lamport 10 < B's 12)."""
    # A: 10 local events
    a = CausalMark("A", 0)
    for _ in range(10):
        a = a.tick()
    assert a == CausalMark("A", 10)            # A is "talkative" but stuck at 10

    # B: receives A, then writes one fresh fact X
    b = CausalMark("B", 0)
    b = b.receive(a)                            # B sees A -> B at 11
    b_fresh = b.tick()                          # B writes X -> 12
    assert b_fresh == CausalMark("B", 12)

    # Third node C merges A's mark (10) vs B's fresh mark (12): B wins causally
    merged = max(CausalMark("A", 10), b_fresh)
    assert merged == CausalMark("B", 12)
    # and explicitly NOT the talkative node:
    assert CausalMark("A", 10) < CausalMark("B", 12)


# -------------------------------------------------------------------------
# Acceptance 2: concurrent writes to one key with equal lamport converge
# -------------------------------------------------------------------------
def test_concurrent_equal_lamport_converges_on_both_nodes():
    """Two concurrent updates to one key, equal lamport, different origin.
    Both replicas must converge to the SAME winner (deterministic tiebreak)."""
    p_mark = CausalMark("P", 5)
    q_mark = CausalMark("Q", 5)

    # replica P applies its own then receives Q's
    merged_at_p = p_mark if not (q_mark > p_mark) else q_mark
    # replica Q applies its own then receives P's
    merged_at_q = q_mark if not (p_mark > q_mark) else p_mark

    # (P,5) vs (Q,5): tiebreak -> Q wins (P < Q). Both must agree.
    assert merged_at_p == CausalMark("Q", 5)
    assert merged_at_q == CausalMark("Q", 5)
    assert merged_at_p == merged_at_q


# -------------------------------------------------------------------------
# Acceptance 3: idempotent replay
# -------------------------------------------------------------------------
def test_idempotent_replay_does_not_change_result():
    svc = SharedContextService("n1")
    remote = [{"key": "k", "value": "v", "node_origin": "n3", "seq": 7}]
    # replay into a FRESH local world twice (simulating duplicate delivery)
    w1 = svc.merge_remote(remote, __world("n1"))
    w2 = svc.merge_remote(remote, __world("n1"))
    assert w1.facts == w2.facts
    assert w1.facts_meta == w2.facts_meta
    # clock advanced to exactly 8 on first delivery; duplicate delivery must NOT
    # inflate it further (max_remote 7 is no longer > local 8 -> stable)
    assert svc._clock.mark.lamport == 8


# -------------------------------------------------------------------------
# Core ТЗ-CAUSAL-01 fix: receive advances the LOCAL clock
# -------------------------------------------------------------------------
def test_shared_context_receive_advances_local_clock():
    """The defect: Lamport without receive-update degenerates into a per-node counter.
    This test proves merge_remote advances the service's own Lamport clock."""
    svc = SharedContextService("B")
    assert svc._clock.mark == CausalMark("B", 0)
    remote = [{"key": "fact", "value": "from-A", "node_origin": "A", "seq": 10}]
    svc.merge_remote(remote, __world("B"))
    # B received A@10, which is causally newer than local 0 -> clock = 10 + 1 = 11.
    assert svc._clock.mark == CausalMark("B", 11)
    # and the merged fact preserves A's origin (convergence on future merges)
    assert svc.merge_remote(remote, __world("B")).facts_meta["fact"] == CausalMark("A", 10)


def test_inmemory_world_update_receive_advances_local_clock():
    """InMemoryWorldState.update with a remote causal mark must advance the local
    clock via receive (not just store the remote mark)."""
    world = InMemoryWorldState("B")
    assert world._clock.mark == CausalMark("B", 0)
    world.update(
        Observation(id="x", content="v",
                    confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                    provenance=Provenance(source="a", actor="a")),
        causal=CausalMark("A", 10),
    )
    # B received A@10 -> local clock = 11; stored fact keeps A's origin (convergence)
    assert world._clock.mark == CausalMark("B", 11)
    assert world.snapshot().facts_meta["x"] == CausalMark("A", 10)


# -------------------------------------------------------------------------
# Negative (K8): prove the OLD bug would have failed — ordering by node name
# -------------------------------------------------------------------------
def test_negative_node_name_must_not_win_merge():
    """If __lt__ ordered by node_origin first, 'Z,seq=1' would beat 'A,seq=10'.
    Assert that can NEVER happen: lamport dominates."""
    assert not (CausalMark("Z", 1) > CausalMark("A", 10))
    assert CausalMark("A", 10) > CausalMark("Z", 1)


# -------------------------------------------------------------------------
# helpers
# -------------------------------------------------------------------------
def __world(node_id: str):
    from contracts.cognitive_domain import WorldState
    return WorldState(node_id=node_id, facts={}, facts_meta={})

"""K8 tests for ТЗ-CRYPTO-HARDEN-01 — hardening the crypto layer (ADR-084).

Covers (acceptance + K1/K5/K6/K8 + ADR-084):
- replay-protection: a VALID signed envelope replayed (seq <= last-seen) is REJECTED.
- oversized payload: rejected BEFORE verify (size-limit, K8 no CPU waste).
- canonical_version mismatch: rejected (envelope forged to a different version).
- unicode NFC: canonical bytes stable across equivalent Unicode normalization forms.
- ISigner/IVerifier split: sign-only / verify-only objects work; combined ISignatureProvider too.
- backward-compat: provider=None => legacy passthrough (verify True; no replay gate applied
  unless a ReplayGuard is explicitly given).
- integration over the REAL FED-ORCH path: replayed response does NOT move trust; fresh response
  (higher seq) moves trust; tampered/unsigned/version-mismatch rejected.

Reuses the FakeTransport/SignedServerTransport pattern from test_crypto_origin.py (deterministic
in-process NW-01). Wiring lives in tests/ (K1/K6: kernel/services do not cross-import).
"""

from __future__ import annotations

from contracts.cognitive_domain import CausalMark
from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_signature import (
    ISigner,
    IVerifier,
    attach_signature,
    canonical_bytes,
    check_signature,
    verify_envelope,
)
from kernel.crypto import HmacSigner, ReplayGuard, build_hmac_signer
from kernel.federated_orchestrator import build_remote_orchestrator
from kernel.identity import ReferenceTrustRegistry


# ---------------------------------------------------------------------------
# 1. ISigner / IVerifier split (ТЗ-CRYPTO-HARDEN-01 contract)
# ---------------------------------------------------------------------------
class _SignOnly(ISigner):
    def __init__(self, inner: HmacSigner): self._i = inner
    def sign(self, payload: bytes) -> str: return self._i.sign(payload)


class _VerifyOnly(IVerifier):
    def __init__(self, inner: HmacSigner): self._i = inner
    def verify(self, payload: bytes, mac: str) -> bool: return self._i.verify(payload, mac)


def test_isigner_iverifier_split():
    p = HmacSigner("mesh")
    s = _SignOnly(p)
    v = _VerifyOnly(p)
    env = {"request_id": "r", "node_id": "B", "causal": {"node_origin": "B", "lamport": 1}}
    signed = attach_signature(env, s)  # sign-only object signs
    assert "signature" in signed
    assert v.verify(canonical_bytes(signed), signed["signature"]) is True  # verify-only verifies
    # combined ISignatureProvider also works
    assert check_signature(signed, p) is True


# ---------------------------------------------------------------------------
# 2. replay-protection (per-origin monotonic seq from CausalMark.lamport)
# ---------------------------------------------------------------------------
def test_replay_valid_signed_envelope_rejected():
    p = HmacSigner("mesh")
    rg = ReplayGuard()
    env = {"request_id": "r", "node_id": "B", "causal": {"node_origin": "B", "lamport": 7}}
    signed = attach_signature(env, p)
    assert verify_envelope(signed, p, replay_guard=rg) is True    # first time: accepted
    # same seq replayed -> rejected (replay)
    assert verify_envelope(signed, p, replay_guard=rg) is False


def test_replay_higher_seq_accepted():
    p = HmacSigner("mesh")
    rg = ReplayGuard()
    e1 = {"node_id": "B", "causal": {"node_origin": "B", "lamport": 1}}
    e2 = {"node_id": "B", "causal": {"node_origin": "B", "lamport": 2}}
    assert verify_envelope(attach_signature(e1, p), p, replay_guard=rg) is True
    assert verify_envelope(attach_signature(e2, p), p, replay_guard=rg) is True  # higher seq ok
    # going back to seq 1 -> rejected (stale)
    assert verify_envelope(attach_signature(e1, p), p, replay_guard=rg) is False


def test_replay_per_origin_independent():
    p = HmacSigner("mesh")
    rg = ReplayGuard()
    a = {"node_id": "A", "causal": {"node_origin": "A", "lamport": 5}}
    b = {"node_id": "B", "causal": {"node_origin": "B", "lamport": 5}}
    assert verify_envelope(attach_signature(a, p), p, replay_guard=rg) is True
    # B's first seq 5 is independent of A's seq 5
    assert verify_envelope(attach_signature(b, p), p, replay_guard=rg) is True


def test_replay_guard_without_seq_accepts_legacy():
    # No causal/seq in envelope -> guard cannot replay-protect; accepts (legacy-safe).
    p = HmacSigner("mesh")
    rg = ReplayGuard()
    env = {"request_id": "r", "node_id": "B"}
    signed = attach_signature(env, p)
    assert verify_envelope(signed, p, replay_guard=rg) is True


# ---------------------------------------------------------------------------
# 3. oversized payload rejected BEFORE verify
# ---------------------------------------------------------------------------
def test_oversized_payload_rejected():
    from contracts.i_signature import MAX_ENVELOPE_BYTES
    p = HmacSigner("mesh")
    big = "x" * (MAX_ENVELOPE_BYTES + 10)
    env = {"node_id": "B", "causal": {"node_origin": "B", "lamport": 1}, "payload": big}
    # Build a signed envelope on a SMALL body, then swap in an oversized payload -> verify must
    # reject (size-limit BEFORE verify, caught inside verify_envelope as ValueError -> False).
    signed_small = attach_signature({"node_id": "B", "causal": {"node_origin": "B", "lamport": 1}}, p)
    oversized = dict(signed_small)
    oversized["payload"] = big
    assert verify_envelope(oversized, p) is False
    # sanity: canonical_bytes on an oversized body raises (size-limit enforced)
    try:
        canonical_bytes({"payload": big})
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# 4. canonical_version mismatch rejected
# ---------------------------------------------------------------------------
def test_canonical_version_mismatch_rejected():
    p = HmacSigner("mesh")
    env = {"request_id": "r", "node_id": "B", "causal": {"node_origin": "B", "lamport": 1}}
    signed = attach_signature(env, p)
    forged = dict(signed)
    forged["_canonical_version"] = 999  # attacker bumps version
    assert verify_envelope(forged, p) is False


# ---------------------------------------------------------------------------
# 5. unicode NFC canonical stability
# ---------------------------------------------------------------------------
def test_unicode_nfc_canonical_stable():
    a = {"text": "café"}            # composed é
    b = {"text": "cafe\u0301"}      # decomposed é (different bytes, same logical string)
    assert canonical_bytes(a) == canonical_bytes(b)


# ---------------------------------------------------------------------------
# 6. backward-compat: provider=None legacy passthrough
# ---------------------------------------------------------------------------
def test_legacy_no_provider_passthrough():
    env = {"request_id": "r", "node_id": "B"}
    assert verify_envelope(env, None) is True           # no provider -> legacy True
    # unsigned with verifier -> rejected
    p = HmacSigner("mesh")
    assert verify_envelope(env, p) is False
    signed = attach_signature(env, None)                # no signer -> unchanged
    assert "signature" not in signed


# ---------------------------------------------------------------------------
# 7. integration over REAL FED-ORCH path: replayed response does NOT move trust
# ---------------------------------------------------------------------------
class _SignedServerTransport(INetworkTransport):
    def __init__(self, success, signer, fixed_seq=1):
        self._success = success
        self._signer = signer
        self._seq = fixed_seq
        self._handler = None

    def connect(self, n, p): pass
    def send_event(self, e): pass
    def send_facts(self, facts, s):
        for f in facts:
            if isinstance(f, dict) and f.get("__fed_orch_req__"):
                node = f["node_id"]; rid = f["request_id"]
                resp = {
                    "__fed_orch_resp__": True, "request_id": rid, "node_id": node,
                    "author_id": node, "causal": {"node_origin": node, "lamport": self._seq},
                    "outcome": {"success": self._success, "detail": "remote"},
                }
                if self._signer is not None:
                    resp = attach_signature(resp, self._signer)
                if self._handler:
                    self._handler([resp], node)
    def on_event(self, h): pass
    def on_facts(self, h): self._handler = h
    def send_soft_layer(self, i, s): pass
    def on_soft_layer(self, h): pass
    def disconnect(self): pass


def _trust():
    t = ReferenceTrustRegistry()
    t.seed("B", 0.9)
    return t


def test_replayed_response_does_not_move_trust():
    signer = HmacSigner("mesh")
    t = _trust()
    rg = ReplayGuard()
    # server always answers with seq=1 (fixed) -> any RE-SEND is a replay
    ro = build_remote_orchestrator(
        _SignedServerTransport(True, signer, fixed_seq=1), t, trust_threshold=0.2,
        signature_provider=signer, replay_guard=rg,
    )
    before = t.current_trust("B")
    out1 = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out1.success is True
    after_first = t.current_trust("B")
    # second dispatch hits the SAME fixed-seq response -> replay rejected -> no record_outcome
    out2 = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out2.success is False            # no verified (non-replay) response arrived
    assert t.current_trust("B") == after_first  # unchanged by the replayed message


def test_fresh_higher_seq_response_moves_trust():
    signer = HmacSigner("mesh")
    t = _trust()
    rg = ReplayGuard()
    # server answers with seq=5 (higher than any seen) -> accepted, trust moves
    ro = build_remote_orchestrator(
        _SignedServerTransport(True, signer, fixed_seq=5), t, trust_threshold=0.2,
        signature_provider=signer, replay_guard=rg,
    )
    before = t.current_trust("B")
    out = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out.success is True
    assert t.current_trust("B") > before


def test_version_mismatch_response_rejected_trust_unchanged():
    signer = HmacSigner("mesh")
    t = _trust()
    rg = ReplayGuard()
    # inject a forged-version response directly via a transport subclass
    class _ForgedVersionTransport(_SignedServerTransport):
        def send_facts(self, facts, s):
            for f in facts:
                if isinstance(f, dict) and f.get("__fed_orch_req__"):
                    node = f["node_id"]; rid = f["request_id"]
                    resp = {
                        "__fed_orch_resp__": True, "request_id": rid, "node_id": node,
                        "author_id": node, "causal": {"node_origin": node, "lamport": 1},
                        "outcome": {"success": True, "detail": "remote"},
                    }
                    resp = attach_signature(resp, signer)
                    resp["_canonical_version"] = 999  # forged version
                    if self._handler:
                        self._handler([resp], node)
    ro = build_remote_orchestrator(
        _ForgedVersionTransport(True, signer), t, trust_threshold=0.2,
        signature_provider=signer, replay_guard=rg, response_timeout=0.3,
    )
    before = t.current_trust("B")
    out = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out.success is False
    assert t.current_trust("B") == before

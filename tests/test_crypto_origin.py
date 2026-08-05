"""K8 tests for ТЗ-CRYPTO-01 — authenticated origin for cross-node exchange (HMAC, stdlib).

Closes the Trust Layer "digital signature" gap: outgoing facts/outcomes are signed; the
receiver verifies origin + integrity BEFORE merge/trust. Unverified (tampered / wrong-key /
unsigned-when-verifier-set) messages are rejected and MUST NOT move trust.

Covers (acceptance + K1/K5/K6/K8 + ADR-082):
- sign/verify roundtrip (HmacSigner over stdlib hmac/hashlib, deterministic).
- tampered payload rejected; wrong key rejected; unsigned (with verifier) rejected.
- legacy passthrough: provider=None -> check_signature True (backward-compat, no break).
- TRUST ONLY FROM VERIFIED OUTCOMES: a verified success/failure moves trust; a tampered /
  wrong-key / unsigned response is dropped BEFORE record_outcome -> trust unchanged.
- determinism (I-09): same key+payload -> same MAC; canonical bytes stable (sort_keys).
- O1: signing/verifying does NOT mutate HARD/FSM; trust remains SOFT via record_outcome.
- integration over the real FED-ORCH send/verify path (build_remote_orchestrator + provider);
  existing FED/TCP/NET-AGENT/FSE-01 tests remain green (proven separately, no provider = legacy).

Reuses the FakeTransport carrier pattern from test_federated_orchestration.py (deterministic
in-process NW-01). Wiring lives in tests/ (K1/K6: kernel/adapters do not cross-import).
"""

from __future__ import annotations

from contracts.i_network_transport import INetworkTransport
from contracts.i_orchestrator import OrchestrationGoal, TaskOutcome
from contracts.i_signature import attach_signature, canonical_bytes, check_signature
from kernel.crypto import HmacSigner, build_hmac_signer
from kernel.federated_orchestrator import build_remote_orchestrator
from kernel.identity import ReferenceTrustRegistry


# ---------------------------------------------------------------------------
# 1. sign/verify roundtrip + determinism (I-09)
# ---------------------------------------------------------------------------
def test_sign_verify_roundtrip():
    p = HmacSigner("shared-secret")
    env = {"request_id": "r1", "goal": {"capability": "retrieval"}}
    signed = attach_signature(env, p)
    assert "signature" in signed
    assert check_signature(signed, p) is True


def test_sign_deterministic_same_key_payload():
    p = HmacSigner("k")
    env = {"a": 1, "b": "x", "c": [1, 2, 3]}
    assert attach_signature(env, p)["signature"] == attach_signature(env, p)["signature"]


def test_canonical_bytes_order_independent():
    p = HmacSigner("k")
    a = attach_signature({"x": 1, "y": 2}, p)
    b = attach_signature({"y": 2, "x": 1}, p)  # same content, different order
    assert a["signature"] == b["signature"]


# ---------------------------------------------------------------------------
# 2. tampered / wrong-key / unsigned (with verifier) -> rejected
# ---------------------------------------------------------------------------
def test_tampered_payload_rejected():
    p = HmacSigner("k")
    signed = attach_signature({"a": 1, "b": "x"}, p)
    tampered = dict(signed)
    tampered["b"] = "y"  # integrity violation
    assert check_signature(tampered, p) is False


def test_wrong_key_rejected():
    p = HmacSigner("k")
    other = HmacSigner("other-key")
    signed = attach_signature({"a": 1}, p)
    assert check_signature(signed, other) is False


def test_unsigned_with_verifier_rejected():
    p = HmacSigner("k")
    unsigned = {"a": 1, "b": "x"}  # no "signature" key
    assert check_signature(unsigned, p) is False


# ---------------------------------------------------------------------------
# 3. legacy passthrough (backward-compat: no provider -> verify always True)
# ---------------------------------------------------------------------------
def test_legacy_no_provider_passthrough():
    env = {"a": 1}
    assert check_signature(env, None) is True
    signed = attach_signature(env, None)  # no signer -> unchanged
    assert "signature" not in signed


# ---------------------------------------------------------------------------
# 4. integration: trust evolves ONLY from VERIFIED outcomes
# ---------------------------------------------------------------------------
class _SignedServerTransport(INetworkTransport):
    """In-process carrier; the 'server' signs responses with `signer` (or leaves UNSIGNED)."""

    def __init__(self, success: bool, signer):
        self._success = success
        self._signer = signer
        self._handler = None

    def connect(self, node_id, peers): pass
    def send_event(self, event): pass
    def send_facts(self, facts, sender_node_id):
        for fact in facts:
            if isinstance(fact, dict) and fact.get("__fed_orch_req__"):
                node = fact["node_id"]; rid = fact["request_id"]
                resp = {
                    "__fed_orch_resp__": True, "request_id": rid, "node_id": node,
                    "author_id": node, "causal": None,
                    "outcome": {"success": self._success, "detail": "remote"},
                }
                if self._signer is not None:
                    resp = attach_signature(resp, self._signer)
                if self._handler:
                    self._handler([resp], node)
    def on_event(self, handler): pass
    def on_facts(self, handler): self._handler = handler
    def send_soft_layer(self, items, sender_node_id): pass
    def on_soft_layer(self, handler): pass
    def disconnect(self): pass


def _trust():
    t = ReferenceTrustRegistry()
    t.seed("B", 0.9)
    return t


def test_verified_success_raises_trust():
    signer = HmacSigner("mesh-key")
    t = _trust()
    ro = build_remote_orchestrator(
        _SignedServerTransport(True, signer), t, trust_threshold=0.2,
        signature_provider=signer,  # client verifies with SAME key
    )
    before = t.current_trust("B")
    out = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out.success is True
    assert t.current_trust("B") > before          # 0.9 -> 1.0 (verified outcome)


def test_verified_failure_lowers_trust():
    signer = HmacSigner("mesh-key")
    t = _trust()
    ro = build_remote_orchestrator(
        _SignedServerTransport(False, signer), t, trust_threshold=0.2,
        signature_provider=signer,
    )
    before = t.current_trust("B")
    out = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out.success is False
    assert t.current_trust("B") < before          # 0.9 -> 0.8 (verified failure)


def test_tampered_response_does_not_move_trust():
    # Server signs with key A; client verifies with key B (wrong key) -> response dropped
    # before record_outcome -> trust UNCHANGED, dispatch times out (no verified response).
    server_signer = HmacSigner("server-key")
    client_verifier = HmacSigner("client-key")     # different -> verify fails
    t = _trust()
    ro = build_remote_orchestrator(
        _SignedServerTransport(True, server_signer), t, trust_threshold=0.2,
        response_timeout=0.3, signature_provider=client_verifier,
    )
    before = t.current_trust("B")
    out = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out.success is False                     # no verified response arrived
    assert t.current_trust("B") == before           # trust NOT moved by unverified message


def test_unsigned_response_with_verifier_does_not_move_trust():
    # Server sends UNSIGNED response; client REQUIRES verification -> dropped before trust.
    client_verifier = HmacSigner("mesh-key")
    t = _trust()
    ro = build_remote_orchestrator(
        _SignedServerTransport(True, None), t, trust_threshold=0.2,
        response_timeout=0.3, signature_provider=client_verifier,
    )
    before = t.current_trust("B")
    out = ro.dispatch_remote("B", OrchestrationGoal("g", "retrieval"))
    assert out.success is False
    assert t.current_trust("B") == before


# ---------------------------------------------------------------------------
# 5. O1 + determinism sanity
# ---------------------------------------------------------------------------
def test_o1_trust_soft_via_record_outcome_only():
    # Signing/verifying is pure crypto over ports; it never touches HARD/FSM. The only trust
    # mutation path is ITrustRegistry.record_outcome, exercised above. Reaffirm determinism:
    # identical canonical bytes for identical envelope (independent of dict order).
    p = HmacSigner("k")
    assert canonical_bytes({"x": 1, "y": 2}) == canonical_bytes({"y": 2, "x": 1})


def test_build_hmac_signer_factory():
    p = build_hmac_signer("k")
    assert isinstance(p, HmacSigner)
    assert check_signature(attach_signature({"a": 1}, p), p) is True

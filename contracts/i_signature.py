"""Authenticated origin for cross-node exchange (ТЗ-CRYPTO-01, ADR-082).

K5 (commit 0): НЕ дублирует порты. Разведка показала:
- wire-VO для федерации — `RemoteGoalRequest`/`RemoteOutcomeResponse` (i_federated_orchestrator.py,
  dict-конверты через encode_*/decode_*) и `SoftLayerItem` (i_network_transport.py, to_wire/from_wire).
- СУЩЕСТВУЮЩИЙ crypto: только content-hash `hashlib` в embedding/graph/tracker/audit — НЕТ HMAC и
  НЕТ signature-provider. Значит `ISignatureProvider` — НОВЫЙ порт (one-port-per-boundary), не дублирует.
- send-пути: ReferenceRemoteOrchestrator.dispatch_remote (encode_goal_request+send_facts),
  ReferenceRemoteExecutionListener._on_facts (encode_outcome_response+send_facts),
  FederationSoftMemorySync.publish_soft_layer (send_soft_layer).
- receive/trust-пути: client._on_facts (decode_outcome_response -> record_outcome), server._on_facts
  (decode_goal_request -> orch.dispatch), FSE-01 _handle_remote_soft (from_wire -> merge).

Контракт: `ISignatureProvider.sign(payload: bytes) -> str` и `verify(payload: bytes, mac: str) -> bool`.
Канонизация (canonical bytes) — детерминированная и единственная точка истины (K5), поэтому живёт
здесь, а НЕ размазана по каждому VO. `attach_signature(dict) -> dict` добавляет ключ "signature"
(Optional[str]); `check_signature(dict, provider) -> bool` верифицирует. Когда provider is None ->
check_signature возвращает True (legacy/backward-compat поведение: верификация отключена).

K1: contracts + stdlib only (typing). K8: детерминизм канонизации (sort_keys) обязателен для
воспроизводимых подписей. O1: подпись/верификация НЕ мутирует HARD/FSM.
"""

from __future__ import annotations

import json
from typing import Any, Optional

SIGNATURE_KEY = "signature"


def canonical_bytes(envelope: dict) -> bytes:
    """Deterministic canonical bytes of an envelope for signing.

    The "signature" key (if present) is EXCLUDED so a signed envelope verifies against
    itself. Sorting keys makes dict ordering irrelevant (JSON object is unordered).
    """
    clean = {k: v for k, v in envelope.items() if k != SIGNATURE_KEY}
    return json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")


def attach_signature(envelope: dict, provider: "ISignatureProvider") -> dict:
    """Return a COPY of `envelope` with a "signature" field produced by `provider`.

    When provider is None, returns the envelope unchanged (no signature) — backward-compat.
    """
    if provider is None:
        return envelope
    env = dict(envelope)
    env[SIGNATURE_KEY] = provider.sign(canonical_bytes(envelope))
    return env


def check_signature(envelope: dict, provider: Optional["ISignatureProvider"]) -> bool:
    """Verify `envelope["signature"]` against its canonical bytes using `provider`.

    - provider is None  -> True (legacy mode: verification disabled, previous behaviour).
    - "signature" absent when a provider IS configured -> False (unsigned rejected).
    - mac present       -> provider.verify(canonical_bytes, mac).
    """
    if provider is None:
        return True
    mac = envelope.get(SIGNATURE_KEY)
    if mac is None:
        return False
    return provider.verify(canonical_bytes(envelope), mac)


class ISignatureProvider:
    """Authenticates origin + integrity of a cross-node message (ТЗ-CRYPTO-01, ADR-082).

    Reference impl: `HmacSigner` (kernel/crypto.py) over stdlib hmac/hashlib with a pre-shared
    per-node key. Asymmetric crypto (ECDSA/RSA) is FUTURE (needs an external lib) — out of scope.
    """

    def sign(self, payload: bytes) -> str:
        """Return a MAC/token authenticating `payload`. Deterministic for the same key+payload."""
        raise NotImplementedError

    def verify(self, payload: bytes, mac: str) -> bool:
        """Return True iff `mac` authenticates `payload` under this provider's key."""
        raise NotImplementedError

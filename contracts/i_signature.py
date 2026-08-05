"""Authenticated origin + hardening for cross-node exchange (ТЗ-CRYPTO-01 ADR-082 + ТЗ-CRYPTO-HARDEN-01 ADR-084).

K5 (commit 0, both ТЗ): НЕ дублирует порты. Разведка показала:
- wire-VO федерации — `RemoteGoalRequest`/`RemoteOutcomeResponse` (i_federated_orchestrator.py,
  dict-конверты через encode_*/decode_*) и `SoftLayerItem` (i_network_transport.py, to_wire/from_wire).
  Оба уже транслируют `causal` (CausalMark: node_origin + lamport) в wire-словарь. Значит
  `seq` для replay-protection УЖЕ присутствует в конверте (causal["lamport"]) — НЕ создаём новый
  формат (K5 no-dup). ReplayGuard переиспользует (origin/node_id, causal.lamport) как per-origin ключ.
- СУЩЕСТВУЮЩИЙ crypto: только content-hash hashlib в embedding/graph/tracker/audit. HMAC-провайдер
  (HmacSigner) появился в CRYPTO-01. `ISignatureProvider` уже есть (combined sign+verify) — расширяем
  split-интерфейсами `ISigner`/`IVerifier`, НЕ дублируя; `ISignatureProvider` остаётся combined (compat).
- Интеграционные точки (CRYPTO-01): client dispatch_remote (encode+send_facts), server _on_facts
  (decode+dispatch), FSE-01 _handle_remote_soft (from_wire+merge). HARDEN-01 добавляет к ним
  replay/version/size/unicode-проверки ДО merge/trust.

Контракт: `canonical_bytes` — единственная точка истины (K5). Детерминизм (sort_keys), исключает
ключи signature/canonical_version из подписываемого тела, нормализует str через Unicode NFC,
проверяет размер payload ДО подписи/верификации. `attach_signature`/`check_signature` (provider=None
=> legacy True) сохранены для compat. Добавлены `ISigner`/`IVerifier` + `verify_envelope` (verify +
 replay + version + size) — единый reject-контракт для receiver.

K1: contracts + stdlib only (typing, json, unicodedata). K8: детерминизм канонизации обязателен.
O1: подпись/верификация/реплей НЕ мутируют HARD/FSM.
"""

from __future__ import annotations

import json
import unicodedata
from typing import Any, Optional

SIGNATURE_KEY = "signature"
# ТЗ-CRYPTO-HARDEN-01: canonical_version кодируется в подписываемое тело. Mismatch => reject.
# Исключается из canonical bytes (как и signature), чтобы верификация была воспроизводимой.
CANONICAL_VERSION_KEY = "_canonical_version"
CANONICAL_VERSION = 1
# Максимальный размер подписываемого/верифицируемого тела. Проверяется ДО verify (K8: не тратим
# CPU на огромные сообщения). 256 КБ — достаточно для фактов/исходов федерации; настраивается.
MAX_ENVELOPE_BYTES = 256 * 1024

# Ключи, исключаемые из canonical bytes (мета-поля подписи/версии не входят в тело).
_EXCLUDED_KEYS = frozenset({SIGNATURE_KEY, CANONICAL_VERSION_KEY})


def _nfc(value: Any) -> Any:
    """Recursively normalize all str values to Unicode NFC (ТЗ-CRYPTO-HARDEN-01).

    Different Unicode normalization forms of the SAME logical string (e.g. composed vs
    decomposed accents, or the 'K' Kelvin sign vs 'K') would otherwise produce DIFFERENT
    canonical bytes and thus different MACs — letting an attacker forge a signature by
    swapping equivalent-looking characters. NFC canonicalization makes canonical bytes
    stable across equivalent string encodings (K8 determinism; replay/integrity safety).
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_nfc(k): _nfc(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_nfc(v) for v in value]
    return value


def canonical_bytes(envelope: dict) -> bytes:
    """Deterministic canonical bytes of an envelope body for signing.

    Excludes signature + canonical_version (meta). Sorts keys (JSON object unordered).
    Normalizes every str to NFC. Raises ValueError if the canonical body exceeds
    MAX_ENVELOPE_BYTES (size-limit BEFORE sign/verify — K8).
    """
    body = {k: v for k, v in envelope.items() if k not in _EXCLUDED_KEYS}
    normalized = _nfc(body)
    data = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_ENVELOPE_BYTES:
        raise ValueError(
            f"envelope exceeds MAX_ENVELOPE_BYTES ({len(data)} > {MAX_ENVELOPE_BYTES})"
        )
    return data


def extract_seq(envelope: dict) -> Optional[int]:
    """Replay key: monotonic seq from the envelope's embedded CausalMark (K5: reuse wire format).

    Returns `causal["lamport"]` (the Lamport logical clock) or None when absent. Per-origin
    ordering is by (origin/node_id, lamport) — see ReplayGuard.
    """
    causal = envelope.get("causal")
    if isinstance(causal, dict):
        seq = causal.get("lamport")
        if isinstance(seq, int):
            return seq
    return None


def extract_origin(envelope: dict) -> Optional[str]:
    """Replay/verification origin: node_id (FED-ORCH/EXEC) or origin (FSE-01 SoftLayerItem)."""
    for key in ("node_id", "origin", "author_id"):
        val = envelope.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def attach_signature(envelope: dict, provider: "ISignatureProvider") -> dict:
    """Return a COPY of `envelope` with canonical_version + "signature" produced by `provider`.

    When provider is None, returns the envelope unchanged (no signature) — backward-compat.
    """
    if provider is None:
        return envelope
    env = dict(envelope)
    env[CANONICAL_VERSION_KEY] = CANONICAL_VERSION
    env[SIGNATURE_KEY] = provider.sign(canonical_bytes(env))
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


# ---------------------------------------------------------------------------
# Split interfaces (ТЗ-CRYPTO-HARDEN-01): ISigner / IVerifier
# ISignatureProvider remains the combined (sign+verify) contract for backward-compat;
# it inherits both so any existing provider keeps working.
# ---------------------------------------------------------------------------
class ISigner:
    """Produces a MAC authenticating `payload` (origin + integrity). Deterministic for key+payload."""

    def sign(self, payload: bytes) -> str:
        raise NotImplementedError


class IVerifier:
    """Verifies a MAC authenticates `payload` under this provider's key (constant-time expected)."""

    def verify(self, payload: bytes, mac: str) -> bool:
        raise NotImplementedError


class ISignatureProvider(ISigner, IVerifier):
    """Combined origin/integrity provider for cross-node messages (ТЗ-CRYPTO-01, ADR-082).

    Reference impl: `HmacSigner` (kernel/crypto.py) over stdlib hmac/hashlib with a pre-shared
    per-node key. Asymmetric crypto (ECDSA/RSA) and PKI/key-rotation are FUTURE (need an external
    lib) — out of scope (ADR-082 non-scope, ADR-084 post-MVP).
    """


def verify_envelope(
    envelope: dict,
    provider: Optional["ISignatureProvider"],
    replay_guard: Optional["ReplayGuard"] = None,
) -> bool:
    """Receiver-side reject contract (ТЗ-CRYPTO-HARDEN-01): verify + version + size + replay.

    Returns True ONLY if the envelope is (a) signed/verified (or legacy when provider is None),
    (b) canonical_version matches, (c) within size limit, and (d) NOT a replay. Any failure =>
    False (drop before merge/trust). When `provider is None`, legacy mode skips (a)/(b)/(c) but
    `replay_guard` (if provided) STILL applies — replay protection is independent of signing.
    """
    if provider is not None:
        if envelope.get(CANONICAL_VERSION_KEY) != CANONICAL_VERSION:
            return False
        try:
            # canonical_bytes() also enforces MAX_ENVELOPE_BYTES (size-limit BEFORE verify —
            # K8: don't waste CPU hashing an oversized message). A breach (ValueError) => reject.
            if not check_signature(envelope, provider):
                return False
        except ValueError:
            return False
    if replay_guard is not None:
        return replay_guard.observe(envelope)
    return True

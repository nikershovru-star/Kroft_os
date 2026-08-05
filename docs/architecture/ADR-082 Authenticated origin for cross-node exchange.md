---
id: ADR-082
title: Authenticated origin for cross-node exchange (HMAC, stdlib; closes Trust Layer "digital signature")
status: accepted
date: 2026-08-05
relates_to:
  - ADR-075
  - ADR-076
  - ADR-066
  - ADR-081
tz: TZ-CRYPTO-01
laws:
  - K1
  - K5
  - K6
  - K8
  - O1
  - I-09
evidence_level: V
---

# ADR-082 — Authenticated origin for cross-node exchange

## Context

Федерация (FED-ORCH/EXEC/TCP/NET-AGENT/FSE-01) обменивается `RemoteGoalRequest` /
`RemoteOutcomeResponse` / `SoftLayerItem` БЕЗ аутентификации: приёмник верит любому отправителю.
Trust Layer визии явно требует «цифровую подпись». Без аутентификации злоумышленник может
внедрить подделанный факт/исход и «доверие» ему. ТЗ-CRYPTO-01 закрывает это: исходящие
сообщения подписываются (HMAC, stdlib), приёмник верифицирует происхождение + целостность ДО
merge/trust; непроверенное отклоняется. Stdlib-only (hmac/hashlib), без внешних SDK (K6).
Асимметричная подпись (ECDSA) — future.

## K5 reconnaissance (commit 0)

- wire-VO: `RemoteGoalRequest`/`RemoteOutcomeResponse` (i_federated_orchestrator.py, dict-конверты
  через `encode_*`/`decode_*`) + `SoftLayerItem` (i_network_transport.py, `to_wire`/`from_wire`).
- СУЩЕСТВУЮЩИЙ crypto: только content-hash `hashlib` в embedding/graph/tracker/audit — НЕТ HMAC и
  НЕТ signature-provider. => `ISignatureProvider` — НОВЫЙ порт (one-port-per-boundary), НЕ дублирует.
- send-пути: `ReferenceRemoteOrchestrator.dispatch_remote` (encode_goal_request+send_facts),
  `ReferenceRemoteExecutionListener._on_facts` (encode_outcome_response+send_facts),
  `FederationSoftMemorySync.publish_soft_layer` (send_soft_layer).
- receive/trust-пути: client `_on_facts` (decode -> record_outcome), server `_on_facts`
  (decode -> orch.dispatch), FSE-01 `_handle_remote_soft` (from_wire -> merge).

## Decision

1. `contracts/i_signature.py` — НОВЫЙ порт `ISignatureProvider.sign(payload:bytes)->str` /
   `verify(payload:bytes, mac:str)->bool`, плюс канонизация (single source of truth):
   `canonical_bytes(dict)` (sort_keys, исключает ключ `signature` — детерминизм), `attach_signature`
   (добавляет ключ `signature`), `check_signature` (provider=None => True legacy; signature
   отсутствует при настроенном verifier => False = reject).
2. `kernel/crypto.py` — `HmacSigner(ISignatureProvider)` на stdlib `hmac`+`hashlib` (pre-shared
   per-node key, симметричный), `hmac.compare_digest` (constant-time). `build_hmac_signer` фабрика.
3. Интеграция (extend, НЕ break): sender подписывает исходящие факты/исходы; receiver верифицирует
   ДО merge/trust; tampered/wrong-key/unsigned-при-verifier отбрасываются. `signature_provider`
   опционален во всех точках (client/server/FSE-01) => без провайдера поведение НЕ меняется (compat).
4. Точка проброса trust: client верифицирует response ПЕРЕД `record_outcome` — trust эволюционирует
   ТОЛЬКО из верифицированных исходов (acceptance). Server верифицирует request ПЕРЕД исполнением.

## Constraints (закрыты)

- **K1/K6**: stdlib `hmac`/`hashlib` в `kernel/crypto.py` (порт + domain), НЕТ внешних SDK в домене.
- **K5**: НОВЫЙ порт `ISignatureProvider` НЕ дублирует `INetworkTransport`/`ITrustRegistry`/
  `IRemoteOrchestrator`/`IRemoteExecutionListener`.
- **K8**: tampered/wrong-key/unsigned-при-verifier отклоняются; roundtrip детерминирован.
- **O1**: подпись/верификация НЕ мутирует HARD/FSM; trust SOFT (через `record_outcome`).
- **I-09**: canonical bytes (sort_keys) — воспроизводимые подписи; correlation по request_id.
- **Backward-compat**: `signature_provider=None` => `check_signature` True (legacy preserved).
- **Флаг C**: `build_hmac_signer` standalone, НЕ в `build_kernel`.

## Consequences

- Сеть замыкает аутентичность: удалённый узел принимает ТОЛЬКО подписанные (своим ключом)
  факты/исходы; подделка отклоняется ДО merge/trust. Trust-гейтинг теперь опирается на
  проверенное происхождение, а не только на trust-score.
- Федерация устойчива в недоверенной среде (минимально: симметричный pre-shared key per mesh).

## Non-scope / future debt

- Асимметричная криптография (ECDSA/RSA) — нужна внешняя либа; future.
- Key distribution / rotation / PKI — future (reference использует один pre-shared key).
- Multi-hop routing / discovery / консенсус — отдельные волны.

## Verification

- `tests/test_crypto_origin.py`: **13 K8 passed** (roundtrip + determinism; tampered/wrong-key/
  unsigned rejected; legacy passthrough; TRUST ONLY FROM VERIFIED OUTCOMES — verified success
  raises 0.9→1.0, verified failure lowers 0.9→0.8, tampered/unsigned response => trust unchanged).
- Существующие FED-ORCH/EXEC/FSE-01: 19 passed без провайдера (backward-compat).
- Full suite 0 failed; arch-gate 14 passed; akb-lint PASSED.

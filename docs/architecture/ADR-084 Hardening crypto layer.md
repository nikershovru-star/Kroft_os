---
id: ADR-084
title: Hardening the crypto layer — replay-protection, canonical version, size-limit, unicode NFC, ISigner/IVerifier split
status: accepted
date: 2026-08-05
relates_to:
  - ADR-082
  - ADR-075
  - ADR-076
  - ADR-066
  - ADR-054
tz: TZ-CRYPTO-HARDEN-01
laws:
  - K1
  - K5
  - K6
  - K8
  - O1
  - I-09
evidence_level: V
---

# ADR-084 — Hardening the crypto layer (ТЗ-CRYPTO-HARDEN-01)

## Context

Внешний аудит ТЗ-CRYPTO-01 (ADR-082) выявил реальные дыры MVP. Берём 5 дешёвых и серьёзных пунктов:
1. **replay-protection** (самая серьёзная дыра) — захваченный валидный подписанный исход можно
   переотправить и манипулировать trust.
2. **canonical_version** — без версии формата нельзя отвергать будущие несовместимые изменения.
3. **max payload size** — огромное сообщение не должно тратить CPU на HMAC-верификацию.
4. **unicode NFC** — эквивалентные строки в разных формах нормализации давали бы разные canonical bytes.
5. **ISigner/IVerifier split** — разделение подписанта и верификатора (minimal audit surface).

Асимметричная криптография (Ed25519/ECDSA/RSA), key-rotation/PKI, envelope Header/Payload, cross-lang
float — **post-MVP** (задокументировано, нужны внешние либы).

## K5 reconnaissance (commit 0)

- **`seq` для replay уже есть в wire**: `CausalMark.lamport` течёт в `RemoteGoalRequest`/`RemoteOutcomeResponse`
  (`i_federated_orchestrator.py`, через `encode_*`/`decode_*` → `causal` dict) и в `SoftLayerItem`
  (`i_network_transport.py`, `to_wire`/`from_wire` → `causal` dict). ReplayGuard переиспользует
  `causal["lamport"]` + `node_id`/`origin` как per-origin ключ — **НЕ создаём новый формат** (K5 no-dup).
- `ISignatureProvider` уже существует (combined sign+verify). Добавляем `ISigner`/`IVerifier` как
  родительские интерфейсы; существующий провайдер не дублируется.
- `INetworkTransport`/`ITrustRegistry`/`IRemoteOrchestrator`/`IRemoteExecutionListener` — переиспользуются.

## Decision

1. **Контракт** (`contracts/i_signature.py`): `ISigner.sign` / `IVerifier.verify` — split; `ISignatureProvider`
   наследует оба (compat). `canonical_bytes` — детерминированная точка истины: исключает `signature` +
   `canonical_version` из тела, сортирует ключи (sort_keys), нормализует ВСЕ str через **Unicode NFC**
   (recursive), проверяет размер ≤ `MAX_ENVELOPE_BYTES` (256 KiB) ДО подписи/верификации.
2. **Версия**: `CANONICAL_VERSION` (int=1) кодируется в тело при `attach_signature`; `verify_envelope`
   отвергает `canonical_version != CANONICAL_VERSION`.
3. **Impl** (`kernel/crypto.py`): `HmacSigner` dual (ISigner+IVerifier). `ReplayGuard` — per-origin
   монотонное окно: `observe(env)` возвращает True ТОЛЬКО если `seq` СТРОГО > последнего для origin;
   `seq <= last` ⇒ reject (replay/stale); envelope без seq ⇒ accept (legacy-safe). `NodeLamportClock`
   (из `cognitive_domain`) — источник monotonic seq для исходящих сообщений.
4. **Integration** (extend, НЕ break): FED client прикрепляет `causal.seq` к запросу; server прикрепляет
   `causal.seq` к ответу и верифицирует входящий запрос ДО исполнения; оба верифицируют входящее через
   `verify_envelope(+ReplayGuard)` ДО merge/trust. FSE-01 `publish_soft_layer` прикрепляет DISTINCT `seq`
   на КАЖДЫЙ item (НЕ на batch — иначе второй item батча отбрасывается как replay); `_handle_remote_soft`
   верифицирует ДО merge. Все точки принимают опц `replay_guard` (shared между client+server узла).
5. **Backward-compat**: `signature_provider=None`/`replay_guard=None` ⇒ legacy поведение (доказано:
   32 existing теста passed без провайдера).

## Constraints (закрыты)

- **K1/K6**: stdlib `hmac`/`hashlib`/`unicodedata`/`json` в contracts + kernel; НЕТ внешних SDK в домене.
- **K5**: НЕ дублирован порт; reuse `CausalMark.lamport` как replay-key.
- **K8**: reject replay/oversized/version-mismatch/unsigned/tampered; NFC-стабильность; size-limit ДО verify.
- **O1**: signing/verifying/replay НЕ мутирует HARD/FSM; trust SOFT через `record_outcome` только из
  verified + non-replay исходов.
- **I-09**: canonical bytes (sort_keys + NFC) — воспроизводимые подписи; correlation по request_id.
- **Флаг C**: `build_hmac_signer`/`build_remote_orchestrator`/etc — standalone, НЕ в `build_kernel`.

## Consequences

- Federated обмен теперь устойчив к replay (захваченный исход не может дважды двинуть trust), к
  version-skew, к oversized-DoS и к Unicode-обфускации подписи. Attack surface подписанта/верификатора
  разделён минимально.

## Non-scope / future debt

- Асимметричная криптография (Ed25519/ECDSA/RSA) — внешняя либа; future.
- Key distribution / rotation / PKI — future.
- Envelope Header/Payload split, cross-lang float сериализация — future.
- Multi-hop routing / discovery / консенсус — отдельные волны.

## Verification

- `tests/test_crypto_harden.py`: **12 K8 passed** (ISigner/IVerifier split; replay rejected; oversized
  rejected; version-mismatch rejected; NFC stable; legacy passthrough; integration: replayed response
  does NOT move trust, fresh higher-seq response DOES, forged-version rejected + trust unchanged).
- Существующие CRYPTO-01 + FED/FSE-01: **32 passed** без провайдера (backward-compat).
- Full suite 0 failed; arch-gate 14 passed; akb-lint PASSED.

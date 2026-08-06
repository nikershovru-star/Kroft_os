---
id: ADR-098
title: Key distribution + rotation/revocation for per-author HMAC keys (ТЗ-KEYDIST-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-096   # AUTHOR-KEYS-01 per-author HMAC keys
  - ADR-082   # CRYPTO-01 ISignatureProvider (HMAC)
  - ADR-093   # MARKETPLACE-01 SkillRepository
decision: >-
  AUTHOR-KEYS-01 привязал автора к HMAC-ключу, но ключи сиделись in-process (build_author_key_registry)
  — multi-node узлы не могли узнать ключи друг друга, ротация/отзыв отсутствовали. KEYDIST-01 даёт
  lightweight key-distribution: bootstrap trust-anchor (pre-shared HMAC-ключ, MVP допущение) HMAC-подписывает
  key-records; узел верифицирует bootstrap-подпись перед принятием ключа; ротация (version bump supersedes)
  и отзыв (revoked -> reject). K5-разведка: IAuthorKeyRegistry/ISignatureProvider (CRYPTO-01) УЖЕ есть —
  переиспользуем (НЕ дублируем). canonical_bytes/check_signature (i_signature) переиспользуются для
  bootstrap-подписи KeyRecord. KeyRecord (frozen VO: author, key, version, signed_by, signature, revoked) +
  IKeyDistribution (publish_key/fetch_key/is_revoked/revoke/get_signer). KeyDistributionService (composition,
  Флаг C) строит bootstrap-signed KeyRecord через HmacSigner(bootstrap_key), верифицирует bootstrap-подпись
  в fetch_key (tampered -> None), rotation (version > existing, иначе ValueError), revoke (fetch -> None).
  SkillRepository.verify (services, K6: services->contracts only) приоритизирует valid+не-revoked distributed
  key, затем локальный author_key_registry, затем shared signer (backward-compat). Ed25519/PKI — post-MVP.
evidence_level: V
addresses:
  - TZ-KEYDIST-01
---
## Context
AUTHOR-KEYS-01 закрыл Флаг 3 (автор криптографически привязан к ключу), но ключи сиделись in-process.
Реальный multi-node узел не мог получить ключ автора (key distribution), и не было ротации/отзыва.
KEYDIST-01 — production-hardening: bootstrap trust-anchor подписывает key-records; узлы верифицируют
bootstrap-подпись; поддержаны rotation (version bump) и revocation.

## Decision
- contracts/i_key_distribution.py: KeyRecord (frozen VO) + IKeyDistribution (publish_key/fetch_key/
  is_revoked/revoke/get_signer). НОВЫЙ шов; НЕ дублирует IAuthorKeyRegistry/ISignatureProvider.
- composition/key_distribution_service.py (Флаг C): KeyDistributionService — bootstrap-anchor HMAC-подпись
  через canonical_bytes/check_signature (reuse i_signature) + HmacSigner (reuse adapters); fetch_key
  верифицирует bootstrap-подпись (tampered -> None); rotation (version > existing, ValueError иначе);
  revoke (fetch/get_signer -> None, is_revoked True). get_signer возвращает HmacSigner(rec.key).
- services/skill_marketplace.py (K6: services->contracts only): SkillRepository + key_distribution
  параметр; verify приоритет: distribution (valid+не revoked) -> author_key_registry -> shared signer.

## Consequences
- Multi-node: узел принимает ключ автора только с валидной bootstrap-подписью; tampered/revoked -> reject (O1).
- Rotation: version bump supersedes старый ключ (история сохраняется). Revocation: reject future packages.
- Backward-compat: без key_distribution -> локальный registry/shared signer (MARKETPLACE/FED-REPL/CAPSTONE
  сценарии зелёные).
- Non-scope (post-MVP): Ed25519/PKI асимметрия, web-of-trust, реальный bootstrap (не pre-shared), OCSP-like
  real-time revocation.
- I-09: детерминизм HMAC; O1: tampered/revoked/unknown -> safe deny; Флаг C (НЕ в build_kernel).

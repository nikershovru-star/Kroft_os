---
id: ADR-096
title: Per-author HMAC keys — author cryptographically bound to its key (ТЗ-AUTHOR-KEYS-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-082   # CRYPTO-01 ISignatureProvider (HMAC)
  - ADR-093   # MARKETPLACE-01 SkillPackage / ISkillRepository
  - ADR-094   # FED-REPL-01 ISkillDistributor
  - ADR-095   # CAPSTONE-02
decision: >-
  MARKETPLACE-01/FED-REPL-01/CAPSTONE-02 подписывали ВСЕ пакеты ОДНИМ общим HMAC-ключом, поэтому
  подпись доказывала «подписал кто-то с общим ключом», а НЕ «подписала alice» (Флаг 3, накапливается
  в 3 ТЗ). ТЗ-AUTHOR-KEYS-01 закрывает это прагматично (stdlib, без Ed25519): каждый автор имеет
  СОБСТВЕННЫЙ HMAC-ключ в IAuthorKeyRegistry; пакет подписывается ключом автора и верифицируется
  зарегистрированным ключом этого автора. Подделка автора (чужой ключ) -> rejected. K5-разведка:
  ISignatureProvider/HmacSigner (CRYPTO-01) УЖЕ есть — переиспользуем (НЕ дублируем). SkillPackager
  УЖЕ принимает `signer` (per-author HmacSigner) — НЕ меняем сигнатуру. SkillRepository.verify
  расширен: если автор зарегистрирован в IAuthorKeyRegistry -> verify через get_signer(author)
  (HmacSigner(author_key)); ИНАЧЕ fallback на общий `_signer` (backward-compat с MARKETPLACE/FED-REPL/
  CAPSTONE shared-key сценариями). IAuthorKeyRegistry + AuthorKey — НОВЫЙ шов (НЕ дублирует
  ISignatureProvider). AuthorKeyRegistry (composition, Флаг C) строит HmacSigner из зарегистрированного
  ключа (get_signer). K6: services/skill_marketplace.py импортирует ТОЛЬКО contracts.i_author_keys
  (IAuthorKeyRegistry интерфейс); concrete HmacSigner живёт в adapters/composition (services НЕ импортирует adapters).
evidence_level: V
addresses:
  - TZ-AUTHOR-KEYS-01
---

## Context
Распределённая дистрибуция навыков (MARKETPLACE/FED-REPL/CAPSTONE) использовала ОДИН общий HMAC-ключ.
Это накапливающийся Флаг 3: подпись не привязывает автора криптографически — любой узел с общим
ключом может подделать пакет от имени любого автора, а trust-гейт затем проверяет trust_score_of
этого (возможно поддельного) автора. Полноценный Ed25519/PKI требует внешней либы (post-MVP);
per-author HMAC-ключи закрывают брешь прагматично, stdlib-only.

## Decision
- **contracts/i_author_keys.py**: `AuthorKey` (frozen VO: author, key) + `IAuthorKeyRegistry`
  (register_key / get_key / get_signer / has). NEW seam; НЕ дублирует ISignatureProvider (get_signer
  возвращает ISignatureProvider, НЕ реализует HMAC).
- **services/skill_marketplace.py** (K6: services->contracts only): `SkillRepository.__init__` принимает
  `author_key_registry`. `verify` предпочитает `registry.get_signer(pkg.author)` когда автор
  зарегистрирован, иначе fallback на общий `_signer` (backward-compat). install -> verify (unchanged flow).
- **composition/author_keys_factory.py** (Флаг C): `AuthorKeyRegistry` (in-memory) + `build_author_key_registry`
  (seeding author->key). get_signer строит HmacSigner(key) из adapters. НЕ в build_kernel.
- **Backward-compat**: незарегистрированный автор (или registry=None) -> verify через общий ключ, как
  раньше. Все существующие MARKETPLACE/FED-REPL/CAPSTONE сценарии (общий ключ) продолжают работать.

## Consequences
- Автор криптографически привязан к своему ключу: пакет alice, подписанный alice_key, верифицируется
  ТОЛЬКО через зарегистрированный alice_key; чужой/неправильный ключ -> verify fail -> rejected (O1).
- Non-scope (post-MVP): Ed25519/PKI (асимметрия + внешняя либа); ротация/отзыв ключей; key distribution.
- Флаг 3 (MARKETPLACE/FED-REPL/CAPSTONE) закрыт прагматично. Флаг 1 (in-process transport) и Флаг 2
  (in-memory SUPERSEDED-история) — наследуются от предыдущих ТЗ.
- I-09: HMAC детерминизм; O1: untrusted/tampered/wrong-key -> safe default-deny.

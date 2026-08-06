---
id: ADR-093
title: Marketplace — package / sign / publish / install with trust gating (ТЗ-MARKETPLACE-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-082   # CRYPTO-01 HMAC ISignatureProvider
  - ADR-084   # CRYPTO-HARDEN-01 verify_envelope (replay/version/size)
  - ADR-071   # PLUGIN-01 ICapabilityPlugin/IPluginRegistry
  - ADR-080   # IDT-01 ITrustRegistry (trust_score_of)
  - ADR-090   # AGENT-LOOP-01
  - ADR-092   # EVOLUTION-01 Procedure versioning
decision: >-
  Навыки улучшаются (EVOLUTION-01), плагины регистрируются (PLUGIN-01), доверие есть (IDT-01),
  сеть есть (FED-*). Но нет дистрибуции: упаковать навык в подписанный пакет, опубликовать,
  установить на другой узел с проверкой подписи и доверия. ТЗ-MARKETPLACE-01 даёт SkillPackage +
  repository + install с trust-гейтингом. K5-разведка: contracts/i_signature.py УЖЕ имеет
  ISignatureProvider + attach_signature/check_signature (HMAC, stdlib) — переиспользуем (НЕ
  дублируем). HmacSigner есть только в kernel/crypto.py (K6: services НЕ импортирует kernel) ->
  создан adapters/hmac_signer.py (адаптер-слой, К5: services->adapters OK, НЕ дубль kernel.crypto).
  contracts/i_identity.py УЖЕ имеет ITrustRegistry (trust_score_of) — переиспользуем для trust-гейта.
  Procedure (i_memory, с version/lifecycle из EVOLUTION-01) + PluginManifest (plugin.py, PLUGIN-01)
  — переиспользуем как payload. SkillPackage + ISkillRepository — НОВЫЕ швы (НЕ дублируют порты).
  SkillPackager (services) package Procedure/Plugin -> signed SkillPackage (HMAC). SkillRepository
  (services, K6: services->contracts+adapters) publish/verify/install: install верифицирует подпись
  + trust-гейт (untrusted/tampered -> reject, O1), version supersede (old SUPERSEDED). Детерминизм
  (I-09). composition/skill_marketplace_factory.py (Флаг C): build_default_marketplace (НЕ в build_kernel).
evidence_level: V
addresses:
  - TZ-MARKETPLACE-01
---

## Context
EVOLUTION-01 замыкает локальное улучшение навыков, PLUGIN-01 регистрирует плагины, IDT-01 даёт
доверие, FED-* — сеть. Но навыки/плагины НЕ дистрибутируются между узлами. Этапы 6–7 требуют
упаковки в подписанный пакет, публикации и установки с проверкой подписи и доверия.

## Decision
- **SkillPackage** (contracts/i_marketplace.py, frozen VO): id, name, version, author, capabilities,
  payload_type ("procedure"|"plugin"), payload (asdict of Procedure/PluginManifest), signature (HMAC).
- **ISkillRepository**: publish / verify / install(trust_registry, threshold) / list. install верифицирует
  подпись (check_signature с тем же ISignatureProvider) И гейтит по trust_score_of(author) >= threshold;
  untrusted/tampered -> None, НЕ мутирует store (O1). Новая версия supersede старой (SUPERSEDED).
- **adapters/hmac_signer.py**: HmacSigner(ISignatureProvider) — адаптер-слой (K6: services->adapters).
  НЕ дубль kernel/crypto.HmacSigner (разные слои).
- **services/skill_marketplace.py**: SkillPackager (package -> attach_signature) + SkillRepository
  (in-memory/local-dir, verify + trust gate + supersede). K6: services->contracts+adapters; signer +
  trust_registry инъектируются.
- **composition/skill_marketplace_factory.py** (Флаг C): build_default_marketplace (HmacSigner + repo).

## Consequences
- Дистрибуция навыков/плагинов: package -> sign -> publish -> install с trust-гейтингом.
- Non-scope (post-MVP): Ed25519/PKI (HMAC с pre-shared key сейчас); multi-host repository server
  (in-memory/local-dir); desktop/GUI (Stage 8). SUPERSEDED-история in-memory (как EVOLUTION-01 Флаг 2).
- Флаг 1 (light): HMAC с pre-shared author-key (НЕ асимметричная криптография) — post-MVP Ed25519.
- Флаг 2 (light): trust-гейт по trust_score_of (MAX TrustMeta); current_trust (LATEST) — альтернатива.

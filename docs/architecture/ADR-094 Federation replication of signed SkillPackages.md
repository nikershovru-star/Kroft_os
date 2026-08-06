---
id: ADR-094
title: Federation replication of signed SkillPackages (ТЗ-FED-REPL-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-082   # CRYPTO-01 ISignatureProvider (HMAC)
  - ADR-084   # CRYPTO-HARDEN-01 verify_envelope
  - ADR-044   # NW-01 INetworkTransport
  - ADR-066   # FSE-01 FederationSoftMemorySync (pattern)
  - ADR-080   # IDT-01 ITrustRegistry
  - ADR-093   # MARKETPLACE-01 SkillPackage / ISkillRepository
decision: >-
  MARKETPLACE-01 дал упаковку/подпись/установку навыков, FED-* — сеть, IDT-01 — доверие,
  FSE-01 — soft-обмен. Но подписанные SkillPackage НЕ распространяются между узлами.
  ТЗ-FED-REPL-01 связывает: узел A публикует подписанный пакет в сеть, узел B принимает,
  верифицирует подпись + гейтит по trust автора + устанавливает (version supersede).
  K5-разведка: contracts/i_network_transport.py УЖЕ имеет INetworkTransport.send_soft_layer/
  on_soft_layer (NW-01) — переиспользуем для передачи SkillPackage как wire-dict (НЕ создаём
  новый transport-канал). services/distributed_runtime.py FederationSoftMemorySync (FSE-01) —
  ПАТТЕРН (publish via send_soft_layer + on_soft_layer handler + verify + trust-gate). Следуем
  ЭТОМУ ЖЕ shape (НЕ дублируем). contracts/i_marketplace.py УЖЕ имеет SkillPackage + ISkillRepository
  (install = verify + trust gate + version supersede) — переиспользуем на принимающем узле (второй
  install-путь НЕ создаём). ISignatureProvider (i_signature) + ITrustRegistry (i_identity)
  переиспользуются внутри ISkillRepository.install. ISkillDistributor — НОВЫЙ шов (НЕ дублирует
  INetworkTransport/ISkillRepository/ISignatureProvider/ITrustRegistry).
  SkillDistributor (services) publish_remote (send_soft_layer([asdict(pkg)], node_id)) + on_remote_package
  (rebuild SkillPackage -> SkillRepository.install). K6: services->contracts only; transport/repository/
  trust инъектируются. composition/skill_distributor_factory.py (Флаг C) build_default_skill_distributor
  (НЕ в build_kernel). Deterministic (I-09); O1: НЕ устанавливает до verify+trust-gate (untrusted/tampered -> None).
evidence_level: V
addresses:
  - TZ-FED-REPL-01
---

## Context
MARKETPLACE-01 даёт локальную упаковку/подпись/установку навыков с trust-гейтингом, но они НЕ
реплицируются между узлами. Этап 6 (завершение) требует кросс-узловой дистрибуции подписанных
SkillPackage: A публикует -> B принимает -> verify(signature) + trust-гейт + install (version supersede).

## Decision
- **ISkillDistributor** (contracts/i_skill_distributor.py): `publish_remote(pkg, transport)` (ship via
  `transport.send_soft_layer([asdict(pkg)], node_id)`) + `on_remote_package(pkg_dict, trust_registry,
  threshold) -> Optional[Any]` (rebuild SkillPackage -> `SkillRepository.install`). NEW seam, НЕ дублирует
  INetworkTransport/ISkillRepository/ISignatureProvider/ITrustRegistry.
- **SkillDistributor** (services/skill_distributor.py, K6: services->contracts): следует FSE-01 shape —
  `on_soft_layer(self._handle_inbound)` в конструкторе/bind. `on_remote_package` перестраивает SkillPackage
  и делегирует `SkillRepository.install` (verify + trust-gate + version supersede). Deterministic (I-09).
- **composition/skill_distributor_factory.py** (Флаг C): `build_default_skill_distributor` (SkillRepository +
  transport + trust) — НЕ в build_kernel.
- **Bug-fix (MARKETPLACE-01 install):** version supersede ранее искал old_pkg в `_packages` (заполняется
  только через `publish()`); federation-installs приходят БЕЗ `_packages`, поэтому old не попадал в
  superseded. Исправлено: supersede добавляет `prev` (уже установленный payload), который ВСЕГДА присутствует.

## Consequences
- Кросс-узловая дистрибуция навыков/плагинов: package -> sign -> publish_remote -> B verify+trust-gate+install.
- Non-scope (post-MVP): Ed25519/PKI (HMAC с общим ключом; Флаг 1 MARKETPLACE-01 — author не привязан
  криптографически к ключу); multi-host TCP (in-process transport в тестах); desktop/GUI (Stage 8).
- Флаг 1 (light): SUPERSEDED-история in-memory (как EVOLUTION/MARKETPLACE Флаг 2).
- O1: untrusted/tampered -> safe default-deny (store untouched). Deterministic HMAC (I-09).

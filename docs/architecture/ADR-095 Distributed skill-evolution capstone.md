---
id: ADR-095
title: Distributed skill-evolution capstone — end-to-end self-evolution across nodes (ТЗ-CAPSTONE-02)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-092   # EVOLUTION-01 SkillEvolver
  - ADR-093   # MARKETPLACE-01 SkillPackage / ISkillRepository
  - ADR-094   # FED-REPL-01 ISkillDistributor
  - ADR-080   # IDT-01 ITrustRegistry
  - ADR-082   # CRYPTO-01 ISignatureProvider (HMAC)
  - ADR-044   # NW-01 INetworkTransport
decision: >-
  EVOLUTION-01 (улучшение навыков), MARKETPLACE-01 (упаковка/подпись/установка), FED-REPL-01
  (кросс-узловая репликация) готовы по отдельности. Капстоун доказывает их СОВМЕСТНУЮ работу
  end-to-end: узел A улучшает навык через SkillEvolver, упаковывает через SkillPackager,
  реплицирует через SkillDistributor узлу B; B верифицирует подпись + гейтит по trust + устанавливает
  (version supersede); поведение B меняется из улучшенного навыка A. Кульминация распределённой
  самоэволюции (Этапы 5–7). K5-разведка: НИЧЕГО нового не создаётся (капстоун — композиция).
  Переиспользуются SkillEvolver (EVOLUTION-01), SkillPackager/SkillRepository (MARKETPLACE-01),
  SkillDistributor (FED-REPL-01), ITrustRegistry (IDT-01), ISignatureProvider/HmacSigner (CRYPTO-01),
  SubprocessSandbox (ADR-039), InMemoryProceduralMemory, INetworkTransport (NW-01). composition/
  capstone_distributed.py строит 2 узла (DistributedNode: evolver+repo+distributor+trust) поверх
  in-process LoopbackTransport (composition-scoped). composition/capstone_scenario.py run_capstone_scenario
  прогоняет цикл. Флаг C: composition only, НЕ в build_kernel. НЕТ новых портов/контрактов.
  Поведение B РЕАЛЬНО меняется (use_skill выполняет установленный Procedure через sandbox -> success_rate).
evidence_level: V
addresses:
  - TZ-CAPSTONE-02
---

## Context
EVOLUTION-01, MARKETPLACE-01, FED-REPL-01 реализованы изолированно. Капстоун (Этап 6→7 кульминация)
требует доказать их совместную работу: A улучшает навык → упаковывает → реплицирует B → B устанавливает
и меняет поведение. Это замыкание распределённой самоэволюции KROFT_OS.

## Decision
- **composition/capstone_distributed.py** (Флаг C, НЕ в build_kernel): `LoopbackTransport` (INetworkTransport,
  in-process, shared bus), `DistributedNode` (оборачивает SkillEvolver + SkillRepository + SkillDistributor +
  ITrustRegistry + injected SubprocessSandbox/InMemoryProceduralMemory), `build_distributed_capstone()`
  (2 узла A,B, shared signer+trust+bus). `DistributedNode.evolve_and_publish` (sender) и `use_skill` (receiver,
  выполняет установленный Procedure через sandbox → success_rate = поведение).
- **composition/capstone_scenario.py** (Флаг C): `run_capstone_scenario()` — A: low-eff skill → evolve →
  package → publish_remote → B: install → use_skill (behavior changes). Deterministic (I-09).
- **K5:** ZERO new ports/contracts. Pure composition over EVOLUTION/MARKETPLACE/FED-REPL/IDT/CRYPTO/NW-01.
- **O1:** untrusted/tampered package → B rejects (inherited from MARKETPLACE/FED-REPL trust+signature gate).
- **I-09:** LLM-free evolver + HMAC → reproducible scenario.

## Consequences
- Замкнут цикл распределённой самоэволюции: A улучшает → B получает улучшенный навык → поведение B меняется.
- Non-scope (post-MVP): Ed25519/PKI (Флаг 1 MARKETPLACE-01 — общий HMAC-ключ не привязывает author);
  real multi-host TCP (in-process loopback, Флаг 3); desktop/GUI (Stage 8); SUPERSEDED-история in-memory (Флаг 2).
- Поведение B доказуемо меняется: scenario v1 (bad step) → success_rate 0.5, v2 (dropped bad) → 1.0.

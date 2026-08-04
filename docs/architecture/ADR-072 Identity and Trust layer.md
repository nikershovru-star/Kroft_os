---
id: ADR-072
title: "Identity & Trust layer — agent identity + trust-gating of federation (ТЗ-IDT-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [identity, trust, federation, security, multi-node, I-09, K1, K6, K8, O1]
---

# ADR-072 — Identity & Trust layer (ТЗ-IDT-01)

## Context
Визия (GitS): несколько KROFT_OS обмениваются знаниями/навыками/стратегиями, но не всему
можно доверять. FSE-01 (ТЗ-FSE-01, ADR-066) федератирует SOFT-слой БЕЗ trust-гейтинга —
дыра: любой узел может влить недоверенные факты в локальную память (влияет на NEXT Decision
через SE-01 read-side). Агенты имеют `AgentState` (lifecycle FSM, ТЗ-AGENT-001), но НЕТ
консолидированной идентичности (trust/permissions/history) и НЕТ trust-проверки на границе
федерации. IDT-01 вводит Identity (агент как постоянный участник) + Trust (trust-score/version/
author/rollback) + trust-гейтинг федерации.

K5-разведка (commit 0): порт Identity/Trust НЕ существовал. Смежные сущности УЖЕ есть и
переиспользуются, НЕ дублируются: `AgentState` (ТЗ-AGENT-001 lifecycle-FSM — ДРУГАЯ граница,
НЕ трогаем), `Provenance`/`CausalMark` (cognitive_domain — переиспользуем для trust-метаданных),
`FederationSoftMemorySync` (FSE-01 — расширяем опциональным gating, НЕ дублируем).

## Decision
- `contracts/i_identity.py`: `AgentIdentity` (frozen VO: agent_id, specialization, trust_level,
  permissions, memory_ref), `IIdentityRegistry`, `TrustMeta` (frozen VO: item_id, trust_score,
  version, author_id, rollback_pointer), `ITrustRegistry` (record/get/trust_score_of/threshold_check),
  `IActionLog` (append/list per agent).
- `kernel/identity.py`: `ReferenceIdentityRegistry` / `ReferenceTrustRegistry` / `ReferenceActionLog`
  (in-memory, deterministic). `trust_score_of` агрегирует MAX записанный trust_score по author
  (детерминированно); unknown -> 0.0.
- FSE-01 extension (commit 3): `SoftLayerItem` + `author_id` (Optional, обратно совместимо);
  `FederationSoftMemorySync.__init__` + `trust_registry: Optional[ITrustRegistry]=None`,
  `trust_threshold: float=0.0` (после `confidence_threshold` -> позиционные вызовы FSE-01 целы).
  Sender помечает `author_id=origin`; receiver отклоняет ВЕСЬ batch, если
  `trust_score_of(sender) < threshold`. БЕЗ registry -> поведение byte-for-byte pre-IDT-01
  (default permissive) -> существующие FSE-01 тесты зелёные.

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: контракты + stdlib only; services/distributed_runtime импортирует только contracts
  (ITrustRegistry), НЕ конкретные реализации.
- **O1**: identity/trust реестры НЕ мутируют HARD/FSM/контракты — держат только своё состояние.
- **I-09 (determinism)**: trust_score_of детерминирован (MAX-агрегация); gating — чистое сравнение.
- **Флаг C**: FSE-01 extension standalone (опц. параметр), НЕ в build_kernel (god-factory не
  усугубляется); identity/trust registry создаются напрямую, НЕ через build_kernel.
- **K8 (negative)**: unknown id -> None / empty list; low-trust sender -> rejected (PluginResult
  аналог: тихий reject, НЕ исключение на границе федерации).
- **Обратная совместимость FSE-01**: registry опционален, default permissive.

## Consequences
- ✅ Дыра FSE-01 закрыта: недоверенные узлы не вливают факты в локальную память (low-trust reject).
- ✅ Identity как отдельная граница (AgentIdentity ≠ AgentState lifecycle-FSM) — one-port-per-boundary.
- ✅ K1/K6: contracts + stdlib; kernel/identity импортирует только contracts; services→contracts only.
- ✅ K8: negative тесты (unknown id, low-trust reject, FSE-01 без registry неизменен).
- ✅ O1: реестры read/write-only своё состояние.
- ⚠️ Non-scope (future): криптографические подписи (real signing) — сейчас только trust-score/
  provenance; обмен агентами (не только знаниями) — future. Per-agent (не per-node) trust — future
  (author_id уже в DTO, но FSE-01 уровня узла пока author==origin).

## Alternatives considered
- Встроить trust прямо в FSE-01 без отдельного порта -> ОТВЕРГНУТО: смешивало бы federation-логику
  с trust-логикой; нарушило бы one-port-per-boundary и усложнило тестирование. Отдельный
  ITrustRegistry + опц. wiring в FSE-01 — чище.
- Дублировать AgentState для identity -> ОТВЕРГНУТО: AgentState уже есть (lifecycle-FSM), это
  другая граница; создание второго = нарушение K5.

## Evidence
- `tests/test_identity_trust.py`: 10 K8 тестов (identity/action-log/trust/FSE-gating/rollback/
  determinism/negative/FSE-без-registry).
- Smoke: FSE-01 no-registry evil accepted; registry low-trust rejected; high-trust accepted.
- Full suite GREEN, gate 14/14, akb-lint PASSED.

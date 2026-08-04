---
id: ADR-074
title: "Procedural memory / Skills — consolidation of repeated success into reusable Procedures + skill-recall in orchestration (ТЗ-SKILL-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [procedural-memory, skills, memory-layer, orchestration, consolidation, I-09, K1, K5, K6, K8, O1]
---

# ADR-074 — Procedural memory / Skills (ТЗ-SKILL-01)

## Context
Memory Layer визии не хватало процедурной памяти («как выполнять задачи»). ORCH-01 дал исходы
(success/failure) + ActionLog; SE-01 — эволюцию. ТЗ-SKILL-01 замыкает: успешные последовательности
действий консолидируются в Procedure (skill), который оркестратор/planner вспоминает (recall)
вместо повторного вывода. Завершает Memory Layer (working/episodic/semantic/normative + procedural)
и делает эволюцию продуктивной (опыт -> навык).

K5-разведка (commit 0) КРИТИЧНА и спасла от дублирования: ТЗ предписывал
`contracts/i_procedural.py` (`IProceduralMemory` + `Skill` VO), НО:
- `IProceduralMemory` УЖЕ существует в `contracts/i_memory.py` (Wave 9 / ADR-012) с
  `record_procedure`/`recall_procedure`.
- `InMemoryProceduralMemory` УЖЕ есть в `services/memory_platform.py`.
- `class Skill` УЖЕ есть в `contracts/cognitive_domain.py` (Marketplace / TZ-021).
- `ILayeredMemory` (i_cognitive_kernel.py) — episode/semantic/normative; процедурный = ОТД. role
  (`IProceduralMemory`), НЕ дублируется.
- ORCH-01 `IActionLog` + `TaskOutcome` переиспользуются для learning-входа.

Решение (K5 one-port-per-boundary): НЕ создавать `i_procedural.py`. Расширить СУЩЕСТВУЮЩИЙ
`IProceduralMemory` новыми методами (`store_skill`/`recall_skill_by_capability`/`list_skills`/
`has_skill`) + добавить `Procedure` VO (frozen, НЕ дублирует `cognitive_domain.Skill`).
Старые `record_procedure`/`recall_procedure` СОХРАНЕНЫ (обратная совместимость; тесты целы).

## Decision
- `contracts/i_memory.py`: `Procedure` (frozen VO: skill_id, name, capability, steps, preconditions,
  confidence, provenance, causal) + `IProceduralMemory` расширен (store_skill / recall_skill_by_capability /
  list_skills / has_skill). K5: расширение порта, НЕ новый порт.
- `services/memory_platform.py`: `InMemoryProceduralMemory` реализует новые методы (in-memory по capability).
- `kernel/procedural.py`: `ProcedureConsolidator` (LLM-free, детерминированный learning). `learn(capability,
  steps, success)`: при `success_count >= threshold` И `success_rate >= min_rate` -> `store_skill`
  ровно ОДИН раз (idempotent). Steps первого успешного исхода фиксируются детерминированно
  (порядок вызовов не влияет). `build_procedural` фабрика (Флаг C, standalone).
- `kernel/orchestrator.py` (ORCH-01): `ReferenceOrchestrator` ОПЦИОНАЛЬНО принимает
  `IProceduralMemory` (`procedural=None` -> обратная совместимость). `route()` сначала
  `recall_skill_by_capability(capability)`: если known-good Procedure есть -> `RoutingDecision(
  kind='skill', rationale='skill-recall:<cap>', score=confidence)`, переопределяя обычный
  agent/plugin scoring. Standalone (Флаг C), НЕ в build_kernel.

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: contracts + stdlib; services->contracts only; kernel->contracts only.
- **O1**: Procedure — SOFT (не мутирует HARD/FSM); orchestrator НЕ мутирует Procedure (только recall).
- **I-09**: консолидация и recall детерминированы (порог N + success-rate, НЕ стохастичны; order-independent).
- **Флаг C**: standalone фабрики (`build_procedural`, `build_orchestrator`), НЕ в build_kernel.
- **K8 (negative)**: нет skill -> обычный routing (НЕ сломан); recall None для unknown capability.
- **К5**: НЕ дублирует IProceduralMemory / cognitive_domain.Skill / ILayeredMemory / ORCH.

## Consequences
- ✅ Memory Layer ЗАВЕРШЁН: working/episodic/semantic/normative + procedural (Procedure/skill).
- ✅ Эволюция стала продуктивной: опыт (repeated success) -> Procedure (skill) -> recall вместо вывода.
- ✅ K5: переиспользован СУЩЕСТВУЮЩИЙ IProceduralMemory (расширен, НЕ дублирован) + Procedure VO
  (НЕ дублирует cognitive_domain.Skill). ILayeredMemory/ORCH НЕ дублированы.
- ✅ K1/K6: contracts + stdlib; kernel/services -> contracts only.
- ✅ O1: Procedure SOFT; orchestrator только recall.
- ✅ I-09: консолидация + recall детерминированы (idempotent, order-independent).
- ⚠️ Non-scope (future): реальное мульти-агент исполнение (NW-01) — agent-dispatch outcomes придут
  оттуда (Флаг 2 ORCH-01: agent-trust монотонно растёт до NW-01); RL/авто-синтез процедур — только
  детерминированная консолидация из лога; LLM-backed skill synthesis — future.

## Alternatives considered
- Создать `contracts/i_procedural.py` (новый IProceduralMemory + Skill) как предписал ТЗ -> ОТВЕРГНУТО:
  дублировало бы существующий порт (K5 one-port-per-boundary) и `cognitive_domain.Skill`. Расширение
  существующего порта — чище и не ломает тесты Wave 9.
- Консолидировать из `IActionLog` напрямую -> ОТВЕРГНУТО: `IActionLog` из IDT-01 хранит только
  `(agent_id, action)`, НЕ capability/steps/TaskOutcome. Явный `learn(capability, steps, success)`-вход
  детерминирован и не мутирует ActionLog (K5 переиспользование, НЕ дублирование семантики).

## Evidence
- `tests/test_procedural_memory.py`: 9 K8 тестов (store/recall детерминированы; consolidation из
  repeated success; idempotent; orchestrator skill-recall; negative; O1 SOFT; I-09 order-independent).
- Smoke: below-threshold/all-fail -> NO skill; 3-й success -> Procedure (skill:retrieval, conf 1.0);
  orchestrator с skill -> kind='skill', rationale='skill-recall:retrieval'.
- Full suite GREEN, gate 14/14, akb-lint PASSED.

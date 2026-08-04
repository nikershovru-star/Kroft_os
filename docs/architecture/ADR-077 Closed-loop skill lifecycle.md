---
id: ADR-077
title: "Closed-loop skill lifecycle — skill confidence evolves from dispatch outcomes + confidence-gated recall (ТЗ-SKILL-EVOLVE-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.9
confidence: high
tags: [skill-evolution, procedural-memory, orchestration, I-09, K1, K5, K6, K8, O1]
---

# ADR-077 — Closed-loop skill lifecycle (ТЗ-SKILL-EVOLVE-01)

## Context
SKILL-01 дал процедурную память (`Procedure`), но цикл навыка был ОТКРЫТ (Флаг 1 SKILL-01):
Procedure пишется один раз, `confidence` не эволюционирует, исходы dispatch не кормят skill
обратно; recall был БЕЗУСЛОВНЫМ (Флаг 2 SKILL-01) — низко-уверенный/устаревший skill вытеснял
сильного агента. ТЗ-SKILL-EVOLVE-01 замыкает петлю: исход skill-recall-dispatch обновляет
confidence навыка (success +, failure -), при устойчивых провалах навык инвалидируется, и recall
гейтится по confidence. Это делает эволюцию навыков полноценной (опыт → навык → recall → исход →
эволюция навыка), по образцу trust-эволюции ORCH-01.

K5-разведка (commit 0): `IProceduralMemory` (Wave 9/ADR-012) УЖЕ есть со `store_skill`/
`recall_skill_by_capability`/`list_skills`/`has_skill` + `Procedure` frozen VO (`confidence: float`).
`InMemoryProceduralMemory` реализует их. `ReferenceOrchestrator` (ORCH-01) делал skill-recall
безусловно, dispatch для `kind='skill'` НЕ обновлял confidence. `ITrustRegistry.record_outcome`
(IDT-01) — ОБРАЗЕЦ паттерна эволюции (success +delta, failure -delta). РЕШЕНИЕ: расширить
СУЩЕСТВУЮЩИЙ порт (НЕ создавать новый), НЕ дублировать Procedure/ReferenceOrchestrator.

## Decision
- `contracts/i_memory.py` (commit 1, расширение ТЗ-SKILL-01): `IProceduralMemory` дополнен
  (НЕ новый порт): `record_skill_outcome(capability, success, delta)` (эволюция confidence,
  frozen→новая версия через store_skill, idempotent, I-09), `invalidate_skill(capability)`
  (удаление при confidence<floor), `recall_skill_by_capability(capability, min_confidence=0.0)`
  (ОБРАТНО-СОВМЕСТИМО: gate опционален, default 0.0 = старый recall). Старые методы СОХРАНЕНЫ.
- `services/memory_platform.py` (commit 2): `InMemoryProceduralMemory` реализует новые методы
  (replace для confidence; min_confidence gate в recall; invalidate удаляет).
- `kernel/procedural.py` (commit 2): `SkillEvolution` (по образцу trust-эволюции ORCH-01) —
  `on_skill_outcome(capability, success)` → `record_skill_outcome` + `invalidate_skill` при
  confidence<floor. `build_skill_evolution` фабрика (Флаг C).
- `kernel/orchestrator.py` (commit 3, ORCH-01): `ReferenceOrchestrator` опц. принимает
  `skill_recall_min_confidence` (default 0.0). `route()` — confidence-gated skill-recall (Флаг 2
  ЗАКРЫТ: низко-уверенный skill НЕ вытесняет агента/плагин); `dispatch()` для `kind='skill'`
  исполняет skill локально (`_execute_skill`: plugin по capability, иначе agent-delegation) и
  кормит РЕАЛЬНЫЙ исход в `record_skill_outcome` (Флаг 1 ЗАКРЫТ: петля замкнута). `build_orchestrator`
  принимает `skill_recall_min_confidence` (Флаг C, standalone, НЕ в build_kernel).

Обязательные ограничения (reviewer flags + ТЗ):
- **K1/K6**: contracts + stdlib; services/kernel → contracts only.
- **O1**: skills — SOFT; эволюция навыка (confidence/validity) НЕ мутирует HARD/FSM.
- **I-09**: детерминизм — confidence-эволюция + инвалидация детерминированы (одинаковые исходы →
  идентичная траектория).
- **Флаг C**: standalone фабрики (`build_skill_evolution`), НЕ в build_kernel.
- **К5**: НЕ дублирован IProceduralMemory/Procedure/ReferenceOrchestrator — расширен (one-port-
  per-boundary). Frozen Procedure обновляется как НОВАЯ версия (store_skill, idempotent, НЕ плодит).
- **K8 (negative)**: low-confidence skill НЕ вспоминается (gate); инвалидированный skill →
  обычный routing (НЕ сломан).

## Consequences
- ✅ Петля навыка ЗАМКНУТА (Флаг 1 SKILL-01): confidence эволюционирует из РЕАЛЬНЫХ dispatch-исходов
  (success +, failure -); при устойчивых провалах навык инвалидируется → оркестратор возвращается
  к обычному routing. Опыт → навык → recall → исход → эволюция навыка.
- ✅ Confidence-gated recall (Флаг 2 SKILL-01 ЗАКРЫТ): низко-уверенный/устаревший skill НЕ вытесняет
  сильного агента/плагин.
- ✅ K5: СУЩЕСТВУЮЩИЙ порт расширен (НЕ дублирован); Procedure/VО переиспользованы; паттерн
  эволюции по образцу ITrustRegistry.record_outcome.
- ✅ K1/K6: contracts + stdlib; kernel/services → contracts only.
- ✅ O1: skills SOFT; HARD/FSM нетронуты (только confidence/validity).
- ✅ I-09: детерминизм (gate + confidence-эволюция + инвалидация).
- ⚠️ Non-scope (future): RL/авто-синтез процедур; LLM-backed skill synthesis; реальное мульти-агент
  exec для навыков, маршрутизированных к агенту (Флаг 2 FED-EXEC-01: агентский «real outcome»
  придёт только с полноценным мульти-агентным исполнением — задокументировано, не блок).

## Alternatives considered
- Создать НОВЫЙ порт ISkillEvolution -> ОТВЕРГНУТО: нарушало бы K5 one-port-per-boundary (порт
  процедурной памяти УЖЕ есть). Расширение IProceduralMemory чище.
- LLM-генерировать confidence из текста исхода -> ОТВЕРГНУТО: ТЗ LLM-free (I-09); confidence
  эволюционирует из бинарного success/failure, как trust (ORCH-01).

## Evidence
- `tests/test_skill_evolution.py`: 7 K8 тестов (confidence evolves success+/failure-; missing→None;
  repeated failure→invalidate→normal routing; gated recall excludes low-confidence; orchestrator
  closed loop feeds outcome; determinism; O1 skills SOFT).
- Smoke: store 0.8 → success 0.9 → failure 0.8; gate 0.5 excludes 0.3 skill→plugin; SkillEvolution
  invalidate при floor 0.3; orchestrator dispatch 0.8→0.9.
- Full suite GREEN, gate 14/14, akb-lint PASSED.

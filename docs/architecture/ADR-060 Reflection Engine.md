---
id: ADR-060
title: "Reflection Engine — metacognitive outcome-based loop closing Self-Evolving (ТЗ-RF-01 / TZ-COG-005)"
status: accepted
evidence_level: V
date: "2026-08-03"
decision_score: 0.88
confidence: high
risk: low
related: [ADR-046, ADR-054, ADR-055, ADR-056, ADR-057, ADR-058, ADR-059]
addresses: [TZ-RF-01, FLAG1, FLAG2]
---

## 1. Context
Deliberate + Learn компонентны (ТЗ-RE/WM/PL/ME-01), но нет АНАЛИТИЧЕСКОГО контура:
кто смотрит на накопленный опыт и решает, что консолидировать / забыть / изменить.
Memory Evolution (ТЗ-ME-01) — исполнительная часть; предложений не было. Reflection
Engine замыкает когнитивный цикл: ... -> Decision -> Execution -> Observation ->
REFLECTION -> Learning (ME-01) -> Memory Update.

**ФЛАГ 1 (ТЗ-ME-01):** консолидация шла по тексту intent, не по outcome — «запоминание
повторений запроса», не «обучение из опыта». Reflection адресует это: OUTCOME-BASED
анализ (успех/неуспех/utility). **ФЛАГ 2 (ТЗ-ME-01):** soft_policies из consolidate
игнорировались в kernel — закрыт commit 0 (ТЗ-RF-01): kernel коммитит их в normative
с тем же O1 guard.

## 2. Decision
- **Контракт:** `IReflectionEngine` (contracts/i_reflection.py) — `reflect(memory, world,
  recent_events, outcomes) -> ReflectionReport`. Reflection ПРЕДЛАГАЕТ (не пишет память).
- **ReflectionReport** (contracts/cognitive_domain.py, frozen): `consolidation_candidates
  (Tuple[SemanticFact])`, `deprecation_candidates (Tuple[str])`, `policy_suggestions
  (Tuple[Policy], SOFT-only)`, `insights`, `confidence`, `causal`.
- **ExecutionOutcome** (contracts/cognitive_domain.py, frozen): `episode_id, success,
  utility, confidence, causal` — ФЛАГ 1 feedback proxy. `ProvenanceType.REFLECTION`
  добавлен.
- **Reference impl** `kernel/reflection.py` (`ReferenceReflectionEngine`, LLM-free, I-09):
  повторяющийся УСПЕШНЫЙ опыт (success + utility>=threshold, >=N) -> consolidation_candidates;
  повторяющийся НЕУСПЕШНЫЙ -> deprecation_candidates; БЕЗ опыта -> пустой report.
  Читает episodes + semantic + ExecutionOutcome (не intent-текст).
- **Интеграция:** `CognitiveKernel` принимает `IReflectionEngine`; `tick` записывает
  `ExecutionOutcome` после Execute (proxy: success = decision принят, utility = conf),
  затем REFLECTION-фаза ДО Learn: `reflect()` -> consolidation_candidates коммитятся в
  semantic (под O1 guard), deprecation_candidates -> Memory Evolution (forget). Reflection
  аналитический, Memory Evolution исполняет (I-14: learning не пишет напрямую).
  `build_kernel` проводит `ReferenceReflectionEngine` (shared clock).
- **CognitiveEventType.REFLECTION_COMPLETED** (уже был) используется.

## 3. Alternatives considered
- **Reflection пишет память напрямую** — отвергнуто: нарушает разделение (Reflection
  аналитический, ME-01 исполнительный под O1 guard). Reflection предлагает, kernel роутит.
- **Консолидация по intent-тексту (старый ФЛАГ 1)** — отвергнуто: нет feedback loop.
  Outcome-based (успех/utility) — честное обучение из опыта.
- **Runtime/system reflection (adaptive auto-tuning)** — отвергнуто (non-scope): здесь
  только COGNITIVE reflection; runtime-контур — future ТЗ.

## 4. Consequences
- Когнитивный цикл замкнут: Perception -> ... -> Decision -> Execution -> Observation ->
  REFLECTION -> Learning -> Memory Update.
- Outcome-based learning (ФЛАГ 1) реализован: успех консолидируется, неуспех депрецируется.
- Self-Evolving guard (O1) сохранён: предложения Reflection проходят hard_violations ДО
  commit; эволюция только SOFT.
- ФЛАГ 2 закрыт: soft_policies из consolidate коммитятся в normative с O1 guard (или
  явно пусты — reference не производит policy).

## 5. Risks / limitations (честно)
- **Outcome — PROXY** (ФЛАГ 1): success/utility из decision, не реальный feedback из среды
  (RL/reward). Reflection драйвится ими — для настоящего Self-Evolving нужен реальный
  feedback (future ТЗ). Честно помечено.
- **ValueSystem duck-typing по .confidence** (флаг ТЗ-PL-01): guard читает
  `candidate.confidence.value`. Если checker читает Policy/Plan-поля — упадёт на
  SemanticFact/ExecutionOutcome. Future: явный протокол `IValuable`.
- Multi-step / RL / LLM-backed reflection — future.

## 6. Traceability
- ТЗ-RF-01, TZ-COG-005 (Reflection phase), ADR-059 (Memory Evolution + guard), раунд-2
  (cognitive reflection; Self-Evolving within immutable kernel).
- K8: tests/test_reflection_engine.py (11) — outcome-based + O1 guard negative.
- ФЛАГ 1 (outcome) и ФЛАГ 2 (soft_policies) закрыты.
- Non-scope: runtime/system reflection, RL/reward, реальная сеть (TcpEventBus).

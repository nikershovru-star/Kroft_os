---
id: ADR-056
title: "Reasoning Engine — parametric Deliberate component (ТЗ-RE-01)"
status: accepted
evidence_level: V
date: "2026-08-02"
decision_score: 0.88
confidence: high
risk: low
related: [ADR-054, ADR-055, ТЗ-RE-01, FLAG1, FLAGD, FLAG3]
supersedes: []
---

# ADR-056: Reasoning Engine — parametric Deliberate component (ТЗ-RE-01)

## 1. Context
Ревью (флаг 4) честно пометило: dedicated **Reasoning Engine как КОМПОНЕНТ**
отсутствует — в FSM есть только фаза `Deliberate` (Reasoning→Planning→Decision
в общем виде). Без выделенного движка Reasoning не параметризуется Intent и не
читает WorldState, а Decision (`IDecisionEngine.select`) не видит WorldState
(флаг D: bind()-хак в тестах). Также три независимых Lamport-clock (kernel/world/
federation) с хардкодом `node_origin="kernel"` ломали causal order и federation
tiebreak (флаг 1).

## 2. Decision
1. **Reasoning Engine** — выделенный параметризуемый движок фазы `Deliberate`,
   запускаемый ПЕРЕД Planning (ADR-054: Reasoning → Planning → Decision).
   - Порт `IReasoningEngine.reason(intent, world, attention_context, budget)`
     → `List[ReasoningStep]`. Каждый step несёт `ConfidenceScore` (ADR-054 I-12)
     + `CausalMark` единого node clock (ТЗ-CAUSAL-01 / ТЗ-RE-01 flag 1).
   - Reference-имплементация `ReferenceReasoningEngine` — детерминированная,
     LLM-free (I-09). Читает Intent + WorldState через Attention; генерирует
     world-aware candidates. Без релевантного факта — единственный low-confidence
     `explore`-step (negative-test hook: иной candidate).
2. **World-aware Decision** (флаг D): `IDecisionEngine.select` получает
   `world: WorldState` + `intent: Intent` (опционально). Производственный engine
   читает world напрямую через порт — bind()-хаки удалены.
3. **Single node clock** (флаг 1): один `NodeLamportClock` на узел, инжектится в
   CognitiveKernel + InMemoryWorldState + SharedContextService. `node_origin`
   везде = `node_id` (не литерал `"kernel"`). Три независимых clock упразднены.
4. **Wire key** (флаг 3): federation wire несёт `lamport` (не legacy `seq`).

## 3. Enforcement (K8)
- `ReasoningStep` frozen, несёт `confidence` + `causal` (gate-тест: без — отклоняется).
- `CognitiveKernel.tick` эмитит `REASONING_STEP` между `GOAL_CREATED` и
  `PLAN_GENERATED` (invariant: Reasoning строго до Planning).
- Negative-тест: reasoning БЕЗ world-fact даёт иной candidate, чем С фактом.

## 4. Reuse
- `NodeLamportClock` (ADR-055 §6 Lamport) — единый clock узла.
- `IAttention` / `IResourceManager` (ADR-054 I-05/I-06) — reasoning через них.
- `CausalMark`, `ConfidenceScore`, `ReasoningStep` (ADR-054/055).

## 5. Validation
- Suite: +8 тестов (ТЗ-RE-01 acceptance + K8 negative) в tests/test_reasoning_engine.py.
- Full suite 1010 passed, gate 14/14, akb-lint PASSED.
- Ad-hoc verifier: reasoning candidate зависит от world fact; single clock согласован
  (kernel event + world fact один causal order, node_origin=node_id); wire "lamport".

## 6. Amendment to ADR-055 §6 (флаг 2) — state idempotence vs order-dependent clock
Лампорт-clock упорядочивает СОБЫТИЯ, но не делает СОСТОЯНИЕ идемпотентным само по себе.
Idempotent replay достигается отдельным правилом в `SharedContextService.merge_remote`:
clock растёт только при causally-NEWER remote mark (`max_remote.lamport > local.lamport`);
повторная доставка того же сообщения не инфлирует часы. То есть ПОРЯДОК (clock) и
ИДЕМПОТЕНТНОСТЬ СОСТОЯНИЯ (merge-правило) — два независимых механизма; менять один
без другого нельзя (флаг 2 clarification зафиксирован здесь).

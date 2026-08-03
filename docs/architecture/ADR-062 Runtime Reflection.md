---
id: ADR-062
title: "Runtime / System Reflection — adaptive runtime contour over operational metrics (ТЗ-RT-01, round 2)"
status: accepted
evidence_level: V
date: "2026-08-03"
decision_score: 0.82
confidence: high
risk: low
related: [ADR-054, ADR-055, ADR-059, ADR-060, ADR-061, TZ-015, RE-01, ME-01, RF-01]
addresses: [TZ-RT-01, O1, SELF-EVOLVING]
---

## 1. Context
RF-01 (ТЗ-RF-01) замкнул **когнитивный** цикл reflection: система анализирует
когнитивный опыт (ExecutionOutcome + отражение) и эволюционирует **SOFT-контент**
(semantic facts, soft policies) под O1 guard. Но это «ЧТО система знает», не
«КАК она работает».

ТЗ-RT-01 (раунд 2 system reflection) требует **вторую петлю**: система наблюдает
свои **ОПЕРАЦИОННЫЕ** метрики (доставка фактов, рост памяти, латентность connect —
источник дала ТЗ-NW-01), отражает их и **адаптивно тюнингует SOFT runtime-параметры**
под O1 guard. Это «КАК система работает», а не «что она знает».

NW-01 дала реальные операционные метрики и доказала cognitive value (commit 0
ТЗ-RT-01 усилил proof до семантического сравнения steps, не plan-id).

## 2. Decision
- **Две НЕЗАВИСИМЫЕ петли (separation от RF-01):**
  - RF-01 (cognitive reflection): опыт → SOFT *контент* (semantic facts, soft policies).
    НЕ трогает операционные параметры.
  - RT-01 (runtime/system reflection): операционные метрики → тюнинг SOFT *параметров*
    (timeouts / thresholds / budgets). **НЕ пишет semantic/policy контент** (это RF-01 + ME-01).
- **Контракты (K1, contracts/i_runtime_reflection.py):**
  - `IRuntimeMetrics.collect() -> List[RuntimeMetric]`
  - `IRuntimeReflection.reflect(metrics) -> List[TuningProposal]` (LLM-free, deterministic)
  - `ITuningApplier.apply(proposal) -> bool` под O1 guard
  - `RuntimeMetric` (frozen VO): name/value/confidence/causal — операционная метрика.
  - `TuningProposal` (frozen VO): param/old_value/new_value/rationale/confidence/causal/layer.
    **Конструктор ЗАПРЕЩАЕТ `layer=HARD`** (O1 на входе).
- **Reference impl (LLM-free, I-09):**
  - `ReferenceRuntimeReflection`: детерминированные правила R1–R3 (low delivery →
    raise connect timeout; fast memory growth → raise min_repetitions; low consolidation
    confidence → raise confidence_threshold). old→new честно из `*.current` метрик, bounded.
  - `ReferenceTuningApplier.apply`: O1 — отклоняет НЕ-SOFT / не-whitelist / без target.
  - `RuntimeSupervisor.step()`: collect → reflect → apply (только SOFT).
- **Тюнингуемые цели (реально тюнингуемые, SOFT-only):**
  - `ReferenceMemoryEvolution`: `min_repetitions`, `confidence_threshold`
  - `NetworkTransport`: `ensure_connected_timeout` (добавлен `_connect_timeout`, K6)
  - `SimpleResourceManager`: `budgets.tokens`
- **O1 Self-Evolving guard:** runtime reflection тюнингует ТОЛЬКО SOFT runtime-параметры.
  FSM-инварианты (I-01..I-20), HARD-политики, контракты, структура ядра — НЕИЗМЕННЫ.
  Enforcement: `TuningProposal` запрещает `layer=HARD` при конструировании; `ITuningApplier.apply`
  отвергает non-SOFT / unknown-param. Whitelist `ALLOWED_SOFT_PARAMS` — единственная
  поверхность мутации.

## 3. Architecture (adaptive loop)
```
RuntimeSupervisor.step():
  metrics = IRuntimeMetrics.collect()              # operational snapshot (current tunables + signals)
  proposals = IRuntimeReflection.reflect(metrics)  # detect patterns -> SOFT TuningProposal
  for p in proposals:
      ITuningApplier.apply(p)                       # O1: SOFT+whitelisted+targeted only
  # targets mutate: net._connect_timeout, mem._min_rep/_thr, rm._budgets
```
`build_runtime_metrics(...)` собирает snapshot из живых целей (current values) +
операционных сигналов (federation delivery rate, memory growth, consolidation conf).

## 4. Relationship to RF-01 / O1
- RF-01 и RT-01 — **разные петли, разные targets**: RF-01 = content (SOFT layer
  semantic/policy), RT-01 = operational parameters. Ни одна не дублирует другую.
- O1 (round 2): обе эволюции SOFT-only; HARD-слой (контракты, FSM, kernel-структура)
  immutable. RT-01 не имеет доступа к commit_semantic/commit_normative — только к
  numeric runtime tunables через `setattr` на зарегистрированные target-объекты.

## 5. Constraints / Non-scope
- K1/K6/K8 соблюдены (contracts + stdlib; services→adapters через порты).
- LLM-backed runtime reflection — НЕ в scope (только детерминированный reference).
- Полная self-optimization / RL / bayesian — НЕ в scope (reference только).
- Реальный outcome-feedback из среды — следующее ТЗ (coupled с EXECUTION-слоем).

## 6. Test Stability (honest note)
Тесты K8 (tests/test_runtime_reflection.py, 14 passed) детерминированы и не требуют
сети/тайминговых барьеров. Adaptive-behavior тесты измеряют ПОВЕДЕНИЕ (timeout-wait
duration, consolidation count) — воспроизводимы. `--count=5` не требовался (нет
fire-and-forget сетевой доставки).

## 7. Future Work
- Подключить реальные операционные сигналы из `NetworkFederationService` (delivery
  rate из `replicate_world` success/fail) и `ReferenceMemoryEvolution` (growth/conf).
- LLM-backed runtime reflection (когда контракты стабилизированы) при сохранении
  LLM-free core как fallback.
- Связать с EXECUTION-слоем для real outcome-feedback (сделать Self-Evolving неподдельным).

---
id: ADR-064
title: "Self-Evolution Behavioral Closure — deliberation reads the evolved SOFT layer (ТЗ-SE-01)"
status: accepted
evidence_level: V
date: "2026-08-04"
decision_score: 0.85
confidence: high
risk: low
related: [ADR-054, ADR-060, ADR-062, ADR-063, TZ-015, RF-01, ME-01, EX-01, I-10, I-11]
addresses: [TЗ-SE-01, EX-01-FLAG3, O1]
---

## 1. Context
ТЗ-EX-01 дал настоящий исход, RF-01+ME-01 эволюционируют SOFT-слой (semantic facts, soft
policies). Но deliberation (reasoning/planner/decision) читала ТОЛЬКО `WorldState` — не
эволюционировавший слой. ФЛАГ 3 (ТЗ-EX-01): система учится и пишет в память, но выученное
НЕ читается обратно при принятии решений. Self-Evolving менял память, а не поведение.

ТЗ-SE-01 замыкает петлю: исходы → эволюция → deliberation читает выученное → решения
меняются → новые исходы. Делает Self-Evolving поведенчески эффективным, а не «записью в
память».

## 2. Decision
- **Контракт (K1, contracts/i_self_evolution.py):** новый порт `ISoftPolicySource`
  (read-side closure) — НЕ ломает сигнатуры `IValueSystem`/`IReasoningEngine`.
  - `SoftPolicyPreference` (frozen VO): kind=prefer/avoid, pattern, weight.
  - `get_prefer_patterns()` / `get_avoid_patterns()` / `get_recall_facts()` читают
    ЭВОЛЮЦИОНИРОВАВШИЙ SOFT-слой (soft policies + semantic facts) БЕЗ мутации памяти.
- **Reference impl (LLM-free, I-09; kernel/self_evolution.py):**
  - `MemorySoftPolicySource(ISoftPolicySource)`: читает `ILayeredMemory` (soft normative
    + semantic) через порт (K6-clean).
  - `PolicyAwareValueSystem(SimpleValueSystem)`: `score()` добавляет бонус за prefer- и
    штраф за avoid-pattern в steps. O1: ТОЛЬКО SOFT влияет, HARD нетронут.
  - `KnowledgeAwareReasoning(ReferenceReasoningEngine)`: `reason()` выводит consolidated
    semantic facts (`decided:<action>`) как grounded candidate-направления.
- **Интеграция (build_kernel):** wire `MemorySoftPolicySource(memory)` →
  `PolicyAwareValueSystem` + `KnowledgeAwareReasoning`. Proxy/real outcome (EX-01) без
  изменений. `SimpleValueSystem` вынесен в `kernel/value_system.py` (разрыв import-цикла:
  self_evolution импортировал cognitive_kernel → цикл; K5-проверка поймала до прогона).
- **Learn-фаза (kernel.tick):** repeated FAILURE (deprecation_candidates) → SOFT
  `avoid:<pattern>` policy (commit_normative, O1 layer=='soft', dedup). episode summary
  связан с plan steps (`decided:choose_red`), чтобы avoid-pattern матчился с raw candidate.

## 3. Architecture (closed behavioral loop)
```
outcomes -> RF-01 reflect -> ME-01 consolidate/deprecate -> ILayeredMemory (SOFT)
   -> ISoftPolicySource (read-side) -> PolicyAwareValueSystem.score (prefer/avoid)
                                      -> KnowledgeAwareReasoning.reason (recall facts)
   -> DecisionEngine.select -> НОВОЕ решение -> НОВЫЙ исход
```

## 4. Capstone proof (tests/test_self_evolution_closure.py, 6 passed)
- repeated SUCCESS по X → consolidation semantic fact → следующий tick **ВЫБИРАЕТ X**.
- repeated FAILURE по Y → deprecation → avoid-policy → следующий tick **ИЗБЕГАЕТ Y**.
- NEGATIVE: БЕЗ wiring (plain SimpleValueSystem + ReferenceReasoningEngine) эволюция НЕ
  меняет решение (доказывает, что именно wiring меняет поведение, не память alone).
- O1: avoid-policy `layer=='soft'`; deliberation не мутирует HARD/FSM. K6: чтение через
  порт, не import памяти.

## 5. Relationship to RF-01 / ME-01 / EX-01 / O1
- **ФЛАГ 3 ТЗ-EX-01 ЗАКРЫТ:** deliberation читает эволюционировавший SOFT-слой.
- **O1:** deliberation читает SOFT, НЕ мутирует HARD/FSM/контракты. Avoid-policy имеет
  `layer=='soft'`, HARD отвергается на commit (hard_violations check).
- **K1/K6/K8:** contracts+stdlib; services→adapters через порты; negative-тесты на
  wiring/O1 обязательны.

## 6. Constraints / Non-scope
- НЕ ломать сигнатуры IValueSystem/IReasoningEngine (расширение через порт).
- Реальные LLM/agent-адаптеры executor — future (Флаг 2 EX-01). RL — reference reward
  только как сигнал. Multi-agent оркестрация (ТЗ-AGENT) — НЕ переоткрывать.

## 7. Test Stability (honest note)
Тесты K8 детерминированы, не требуют сети/таймингов. Rule-map среды + deterministic
kernel → воспроизводимо. `--count=5` не требовался.

## 8. Future Work
- Подключить реальные LLM/agent executor (Флаг 2 EX-01) → avoid/recall на настоящем исходе.
- Policy-aware reasoning мог бы менять НЕ только candidates, но и confidence weighting.

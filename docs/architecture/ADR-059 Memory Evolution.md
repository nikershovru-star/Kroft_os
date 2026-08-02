---
id: ADR-059
title: "Long-Term Memory Evolution — consolidation / forgetting / lifecycle (ТЗ-ME-01 / ADR-046)"
status: accepted
evidence_level: V
date: "2026-08-03"
decision_score: 0.87
confidence: high
risk: low
related: [ADR-046, ADR-054, ADR-055, ADR-056, ADR-057, ADR-058]
---

## 1. Context
`SimpleLearningPolicy` был stub: `ILearningPolicy.propose` есть, но реальной эволюции
памяти нет. `ILayeredMemory` (episode vs normative) и `ILearningPolicy` (I-14: learning
предлагает, не пишет напрямую) заложены, но SOFT-слой консолидации отсутствовал. Memory
Evolution делает learning настоящим: консолидация повторяющегося high-confidence опыта →
semantic facts / нормативные правила; forgetting (депрекация low-confidence / устаревшего);
lifecycle норм (active/deprecated/superseded). Это МЕХАНИЗМ Self-Evolving (раунд 2).

**Несущий инвариант (O1, раунд 2):** эволюционирует только SOFT, HARD — неизменен.
Контракты ядра, KROFT Laws, инварианты FSM как hard constraints НЕ подлежат эволюции из
опыта. Self-Evolving within immutable kernel invariants.

## 2. Decision
- **Контракт:** `IMemoryEvolution` (contracts/i_memory_evolution.py) — `consolidate(
  episodes) -> (List[SemanticFact], List[Policy])`, `forget(episodes) -> List[id]`,
  `supersede(old, new)`. `consolidate` НЕ производит HARD-политик (O1).
- **SemanticFact** (contracts/cognitive_domain.py, frozen): `content + ConfidenceScore +
  CausalMark` (единого clock) `+ source_episodes`. Confidence АГРЕГИРУЕТСЯ по source episodes
  через `aggregate_confidence` (ADR-055, MIN rule), не наивный max.
- **PolicyLifecycle** (Enum): ACTIVE / DEPRECATED / SUPERSEDED. `Policy.lifecycle` поле
  (default ACTIVE, обратно совместимо).
- **ILayeredMemory расширен** (contracts/i_cognitive_kernel.py): `+ commit_semantic /
  get_semantic / get_normative / deprecate_normative`. HARD policy deprecation → raise (O1).
- **Reference impl** `kernel/memory_evolution.py` (`ReferenceMemoryEvolution`, LLM-free,
  I-09): консолидация при conf>порога И повтор>=N; forgetting low-conf; supersede.
- **Интеграция:** `CognitiveKernel` принимает `IMemoryEvolution` + `ILayeredMemory`; Learn-
  фаза `tick` записывает episode и зовёт consolidate/forget с **Self-Evolving guard**
  (`values.hard_violations` ДО commit — убивает нарушающие KROFT Laws факты). `build_kernel`
  проводит `ReferenceMemoryEvolution` (shared clock) + `InMemoryLayeredMemory`.
- **CognitiveEventType:** `+ SEMANTIC_CONSOLIDATED / NORMATIVE_DEPRECATED`.

## 3. Alternatives considered
- **Learning пишет память напрямую** — отвергнуто: нарушает I-14 (write routing by layer в
  памяти, не в learning). Memory Evolution предлагает, kernel роутит через `ILayeredMemory`.
- **Эволюция HARD-слоя** — отвергнуто: ломает O1 (Self-Evolving within immutable kernel).
  Hard constraints immutable; только SOFT (semantic facts, soft policies, skills, utilities).

## 4. Consequences
- Learning стал настоящим: опыт → консолидация → SOFT-слой. Deliberate + Learn компонентны.
- Self-Evolving guard механически проверен (negative-тест: hard-violating fact не попадает
  в семантический слой; HARD policy deprecation raises).
- ConfidenceScore консолидированных фактов агрегирован (не наивный max) — честная калибровка.

## 5. Risks / limitations
- **ValueSystem duck-typing по .confidence** (флаг из ТЗ-PL-01): guard читает
  `candidate.confidence.value`. Если появится checker, читающий Plan/Policy-поля, он
  упадёт на `SemanticFact` (нет `.steps`). На будущее: явный протокол `IValuable` или
  разделение `hard_violations` для Plan vs PredictedState vs SemanticFact, либо семантическая
  проверка `projected_facts`/`content` против Normative-правил (future). Reference допустимо.
- Consolidation ключится по `summary` эпизода (в kernel — `decided:{intent.text}`). Для
  продакшена нужен стабильный опытный ключ (не uuid plan-id). Упрощение reference.
- Multi-step / RL / LLM-backed learning — future (non-scope).

## 6. Traceability
- ТЗ-ME-01, ADR-046 (Memory Evolution), ADR-054 (Layered Memory I-14), ADR-055 (aggregate),
  раунд-2 (Self-Evolving within immutable kernel).
- K8: tests/test_memory_evolution.py (10) — включая SELF-EVOLVING GUARD negative (O1).
- Non-scope: Reflection Engine (следующее ТЗ), реальная сеть (TcpEventBus), RL/LLM-learning.

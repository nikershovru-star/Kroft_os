---
id: ADR-058
title: "Autonomous Planner — value-aware lookahead over World Model (ТЗ-PL-01 / ADR-045)"
status: accepted
evidence_level: V
date: "2026-08-03"
decision_score: 0.85
confidence: high
risk: low
related: [ADR-045, ADR-047, ADR-054, ADR-057, ADR-056]
---

## 1. Context
Planning в `build_kernel` был лямбда-генератором candidates — последний крупный stub в
фазе Deliberate (Reasoning ✅ → Planning ⚠️ → Decision ✅). ТЗ-WM-01 дал `WorldModel.simulate`
(rollout), но он оставался недоиспользованным. ТЗ-PL-01 превращает Planning в выделенный
движок, который использует simulate для lookahead и ранжирует планы по PREDICTED
VALUE-AWARE utility.

Закрывает: последний крупный stub Deliberate; флаг 2 (evaluate мёртвый параметр →
value-aware); продолжает WM-01 (simulate → lookahead).

## 2. Decision
- **Компонент:** `IPlanner` (contracts/i_planner.py) — `plan(goal, reasoning_steps, world,
  budget, intent=None) -> List[Plan]`, ранжированный BEST-first. Заменяет лямбда-planner.
  `ReferencePlanner` (kernel/planning.py, LLM-free, I-09).
- **Lookahead:** каждый candidate plan прогоняется через `WorldModel.simulate(world, plan,
  horizon=1)` → `evaluate(predicted, intent, values)` для каждого шага rollout.
  Predicted utility = min по rollout (план настолько хорош, насколько слаб его худший
  предсказанный шаг). Заносится в `Plan.confidence` (frozen — поле добавить нельзя).
- **Value-aware (флаг 2):** `evaluate` РЕАЛЬНО использует `values`: hard violation
  predicted-состояния → utility 0 (veto, KROFT Laws применяются к предсказаниям, не
  только к реализованным планам); иначе soft utility через `values.score`. Без `values`
  → backward-compatible confidence*relevance.
- **Relevance:** считается по ACTION EFFECT (ключи `effect:*` в projected_facts), НЕ по
  carry-over всех фактов мира — иначе каждый predicted state выглядит одинаково релевантным
  (флаг 3: planner оценивает в полном мире, но relevance отражает ЭФФЕКТ действия).
- **Разделение ролей (I-03/I-09):** Planner РАНЖИРУЕТ, Decision ВЫБИРАЕТ. Planner не делает
  финальный выбор. `CognitiveKernel.tick` зовёт `planner.plan(...)`, затем
  `decision.select(goal, candidates, values, world, intent)`.
- **Backward compatible:** без WorldModel planner ранжирует по confidence reasoning steps.
  Без `intent` evaluate не может быть value-aware — fallback.

## 3. Alternatives considered
- **RankedPlan-обёртка** (Plan + predicted_utility отдельно) — отвергнуто: Plan frozen,
  обёртка ломает существующий contract Decision.select(plans). Confidence-поле Plan
  достаточно (Decision читает confidence).
- **Planner делает выбор** — отвергнуто: нарушает I-03/I-09 (Decision = единственный
  детерминированный выбор).

## 4. Consequences
- Deliberate полностью компонентна: Reasoning → Planning → Decision, все три — порты.
- WorldModel.simulate теперь используется в живом пути (lookahead), не dead code.
- Candidate ranking = predicted value-aware utility, не word-relevance (флаг 2 закрыт).
- Hard constraints (K1 Contracts First и др.) отсекают predicted states на уровне оценки.

## 5. Risks / limitations
- **Transition model = stub** (честно, см. amendment ADR-057): `predict` = carry-over всех
  фактов + `effect:{action.id}` + decay confidence. Это grounding+decay, не содержательная
  transition dynamics («как действие меняет мир»). Настоящая transition model — future
  (LLM-backed / learned). Reference допустим.
- **Isolate-world grounding** в Reasoning (ТЗ-WM-01) остаётся: reasoning оценивает step в
  изолированном мире (только факт), чтобы Y>X сошёлся детерминированно. Production-reasoning
  должен оценивать в ПОЛНОМ мире (контекст других фактов меняет последствия) — упрощение
  reference, не дефект.
- Lookahead horizon=1 (один шаг). Multi-step replanning / dynamic re-planning — future.

## 6. Traceability
- ТЗ-PL-01, ADR-045 (Planning), ADR-047 (World Model), ADR-057 (evaluate refinement),
  ADR-056 (Reasoning Engine), ADR-054 (Deliberate FSM).
- Флаг 2 (value-aware evaluate) — коммит 0 как prerequisite.
- Флаг 3 (full-world eval в planner) — реализовано через relevance по effect.
- K8: tests/test_autonomous_planner.py (9) + tests/test_world_model.py (3 value-aware).
- Non-scope: LLM-planner, RL, real network (TcpEventBus), real transition dynamics.

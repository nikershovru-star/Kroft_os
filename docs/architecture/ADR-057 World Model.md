---
id: ADR-057
title: "World Model — predictive advisor over WorldState (ТЗ-WM-01 / ADR-047)"
status: accepted
evidence_level: V
date: "2026-08-02"
decision_score: 0.86
confidence: high
risk: low
related: [ADR-047, ADR-056, ADR-054, ТЗ-WM-01, ТЗ-RE-01, FLAGA]
supersedes: []
---

# ADR-057: World Model — predictive advisor over WorldState (ТЗ-WM-01 / ADR-047)

## 1. Context
Reasoning Engine (ADR-056) был честно помечен как rule-based grounding по token-overlap
(заглушка). World Model делает reasoning настоящим: предсказывает последствия действий
и оценивает будущие состояния, позволяя planning/decision выбирать по **predicted
utility**, а не по совпадению слов. Раунд 1: World State = SSOT (текущее), World Model =
предиктор поверх (Prediction → Simulation → Planning).

## 2. Decision
1. **Контракт** `IWorldModel` (`contracts/i_world_model.py`, K1):
   - `predict(world, action, horizon) -> PredictedState` (одно действие).
   - `simulate(world, plan) -> List[PredictedState]` (rollout по шагам плана; horizon
     растёт вдоль плана, позже = неопределённее).
   - `evaluate(predicted, intent, values) -> float` (predicted utility 0..1).
2. **PredictedState** (frozen, `cognitive_domain.py`): `horizon` + `projected_facts` +
   `ConfidenceScore` + `CausalMark` единого node clock (ТЗ-RE-01 flag 1).
3. **Reference impl** `ReferenceWorldModel` (`kernel/world_model.py`, LLM-free I-09):
   confidence **МОНОТОННО падает с horizon** (0.25/шаг); grounding базируется на
   релевантных world-фактах; без фактов — LOW confidence (0.2).
4. **Интеграция** (ТЗ-WM-01): `ReferenceReasoningEngine` принимает опц. `world_model`;
   grounded-step confidence = predicted utility (через `predict`→`evaluate`). `build_kernel`
   проводит `ReferenceWorldModel` (shared clock) в reasoning. **Финальный выбор остаётся
   за детерминированным Decision** (World Model = adviser, I-09).
5. **flag A (fix):** `CognitiveKernel.__init__` строит дефолтный clock из
   `world.snapshot().node_id` (не литерал `"kernel"`). `SharedContextService.publish_selective`
   нормализует sentinel-origin (`"kernel"`/`"local"`) в `self_node_id` с warning (не
   молчаливая утечка в федерацию).

## 3. Enforcement (K8)
- `predict` confidence падает с horizon (тест assert h1 > h3).
- `simulate` возвращает ровно `len(plan.steps)` состояний.
- no-fact prediction < 0.3 (low).
- `PredictedState.causal.node_origin == node_id` (фикс флага A).
- Negative: constant-confidence model нарушает свойство horizon-decay (тест детектирует).

## 4. Reuse
- `NodeLamportClock` (ADR-055) — единый clock узла.
- `ReasoningStep` / `IReasoningEngine` (ADR-056) — World Model советует Reasoning.
- `ConfidenceScore`, `CausalMark`, `WorldState`, `Action`, `Plan` (ADR-054/055).

## 5. Validation
- Suite: +10 тестов (ТЗ-WM-01 acceptance + K8 negative) в tests/test_world_model.py.
- Full suite **1020 passed**, gate **14/14**, akb-lint PASSED.
- Ad-hoc verifier: confidence падает с horizon; reasoning с WM ранжирует по predicted
  utility (Y > X); node_origin = node_id при прямом конструировании (flag A).

## 6. Non-scope (explicit)
LLM-backed World Model, полная simulation/RL/learning, реальная сеть (TcpEventBus),
vector clock/HLC — будущие раунды. Здесь только детерминированный reference (I-09).

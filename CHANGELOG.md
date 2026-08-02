# Changelog

All notable changes to KROFT_OS are documented here, grouped by ТЗ/Wave.
Format: `commit-range | scope | summary`.

---

## 2026-08-03 — ТЗ-ME-01 (Long-Term Memory Evolution, Self-Evolving) — DONE

`dce8d96 fe13fbd d9adde6 bb7b20b <docs>`

- **Контракт Memory Evolution.** `contracts/i_memory_evolution.py`: `IMemoryEvolution`
  (consolidate/forget/supersede). `contracts/cognitive_domain.py`: `SemanticFact` (frozen;
  aggregated ConfidenceScore + CausalMark + source_episodes), `PolicyLifecycle` (Enum
  ACTIVE/DEPRECATED/SUPERSEDED), `Policy.lifecycle` поле. `ILayeredMemory` расширен
  (commit_semantic/get_semantic/get_normative/deprecate_normative; HARD deprecation -> raise).
- **Reference impl (LLM-free, I-09).** `kernel/memory_evolution.py`: `ReferenceMemoryEvolution`
  — повторяющийся high-conf опыт (conf>порога, повтор>=N) -> SemanticFact (confidence
  агрегируется через `aggregate_confidence`/MIN, не наивный max); low-conf -> forgetting;
  supersede. HARD-политики НЕ производятся (O1). `kernel/memory_store.py`:
  `InMemoryLayeredMemory` (semantic layer + lifecycle, O1 guard).
- **Интеграция + SELF-EVOLVING GUARD (O1).** `CognitiveKernel` принимает `IMemoryEvolution`
  + `ILayeredMemory`; Learn-фаза `tick` записывает episode и зовёт consolidate/forget с
  guard: `values.hard_violations` ДО commit — hard-violating факты НЕ попадают в SOFT-слой.
  `build_kernel` проводит `ReferenceMemoryEvolution` (shared clock) + `InMemoryLayeredMemory`.
  `CognitiveEventType` + SEMANTIC_CONSOLIDATED / NORMATIVE_DEPRECATED.
- **Тесты (K8).** `tests/test_memory_evolution.py` (+10): consolidation (repeated high-conf
  -> SemanticFact, aggregated conf + CausalMark node_origin); forgetting (low-conf ->
  deprecated); norm lifecycle (supersede); **O1 guard**: HARD policy deprecation raises,
  hard-violating consolidated fact rejected before commit (kernel + unit); negative: no
  consolidation below threshold / single / engine never emits HARD policy. crashtest-B
  `InMemoryLayeredMemory` обновлён под новый `ILayeredMemory`.
- **Docs.** `ADR-059` (accepted) — Memory Evolution + Self-Evolving guard; AKB (adrs/issues);
  CHANGELOG; PROJECT_STATUS.

**Verification:** full suite `1042 passed, 19 skipped, 1 xpassed, 0 failed`;
arch-gate `14 passed`; akb-lint PASSED.

---

## 2026-08-03 — ТЗ-PL-01 (Autonomous Planner, value-aware lookahead) — DONE

`21b1da1 a0373f7 9c460e8 539a015 ec984f3 <docs>`

- **flag 2 — evaluate value-aware (prerequisite).** `IWorldModel.evaluate(predicted,
  intent, values)` РЕАЛЬНО использует `values`: `hard_violations(predicted)` -> utility 0
  (veto predicted states, нарушающих KROFT Laws / hard constraints); иначе soft utility
  через `values.score`. Без `values` -> backward-compatible confidence*relevance.
  `ReferenceReasoningEngine` теперь несёт `IValueSystem` и передаёт в `evaluate`, так что
  predicted utility value-aware (не просто word-relevance). `build_kernel` проводит values.
- **Контракт Planner.** `contracts/i_planner.py`: `IPlanner.plan(goal, reasoning_steps,
  world, budget, intent=None) -> List[Plan]` ранжированный BEST-first (через
  `Plan.confidence`). Заменяет lambda-candidate-генератор в `build_kernel`.
- **Reference impl (LLM-free, I-09).** `kernel/planning.py`: `ReferencePlanner` — один
  candidate Plan на reasoning step; каждый прогоняется через `WorldModel.simulate`
  (lookahead, horizon=1) и `evaluate(intent, values)`; `Plan.confidence` = predicted
  value-aware utility; ранжируется BEST-first. Без WorldModel -> fallback на step
  confidence. Relevance считается по ACTION EFFECT (`effect:*` ключи), не carry-over
  (флаг 3: planner в полном мире, но relevance отражает эффект действия).
- **Интеграция.** `CognitiveKernel` принимает `IPlanner`; `tick` зовёт
  `planner.plan(goal, steps, world_snapshot, budget, intent)`. `build_kernel` проводит
  `ReferencePlanner` (shared clock + world_model + values). Planner РАНЖИРУЕТ;
  детерминированный Decision ВЫБИРАЕТ (I-03/I-09) — planner не подменяет Decision.
- **Тесты (K8).** `tests/test_autonomous_planner.py` (+9): ranked best-first; lookahead
  через simulate (1 call/candidate); hard-veto -> utility 0; soft-utility re-ranks;
  negative: без WorldModel -> иной порядок (fallback на step confidence); Decision
  всё ещё выбирает финал. `tests/test_world_model.py` (+3 value-aware): hard-veto,
  soft-rerank, no-values fallback. Legacy planner-лямбды в тестах -> `IPlanner`.
- **Docs.** `ADR-058` (accepted) — Autonomous Planner; `ADR-057` amended (§7: evaluate
  value-aware, transition = stub честно, relevance по effect); AKB (adrs/issues);
  CHANGELOG; PROJECT_STATUS.

**Verification:** full suite `1032 passed, 19 skipped, 1 xpassed, 0 failed`;
arch-gate `14 passed`; akb-lint PASSED.

---

## 2026-08-02 — ТЗ-WM-01 (World Model, предиктивный советник) — DONE

`b0523d6 f26eb7e 07d7730 66043a4 f33c5fc <docs>`

- **flag A — clock fix.** `CognitiveKernel.__init__` строит дефолтный `NodeLamportClock`
  из `world.snapshot().node_id` (больше нет литерала `"kernel"`). `SharedContextService.
  publish_selective` нормализует sentinel-origin (`"kernel"`/`"local"`) в `self_node_id`
  с warning (не молчивая утечка в федерацию).
- **Контракт World Model.** `contracts/i_world_model.py`: `IWorldModel.predict(world,
  action, horizon)`, `simulate(world, plan)` (rollout по шагам), `evaluate(predicted,
  intent, values)` -> float. `PredictedState` (frozen: `horizon` + `projected_facts` +
  `ConfidenceScore` + `CausalMark` единого clock).
- **Reference impl (LLM-free, I-09).** `kernel/world_model.py`: `ReferenceWorldModel` —
  confidence ПАДАЕТ с horizon (0.25/шаг), grounding по world-фактам, без фактов -> LOW
  (0.2). `simulate` — одна `PredictedState` на шаг плана (horizon растёт).
- **Интеграция.** `ReferenceReasoningEngine` принимает опц. `world_model`; grounded-step
  confidence = predicted utility (через `predict`->`evaluate`). `build_kernel` проводит
  `ReferenceWorldModel` (shared clock). Финальный выбор — за детерминированным Decision
  (World Model = adviser).
- **Тесты (K8).** `tests/test_world_model.py` (+10): confidence падает с horizon;
  simulate rollout; reasoning с WM ранжирует по predicted utility (Y > X); без WM — иной
  выбор; no-fact = low; `PredictedState.causal.node_origin == node_id`; flag A; K8
  negative: constant-confidence модель нарушает horizon-decay.
- **Docs.** `ADR-057` (accepted) — World Model contract; AKB (adrs/issues); CHANGELOG;
  PROJECT_STATUS.

**Verification:** full suite `1020 passed, 19 skipped, 1 xpassed, 0 failed`;
arch-gate `14 passed`; akb-lint PASSED.

---

## 2026-08-02 — ТЗ-RE-01 (Reasoning Engine W2-gap) — DONE (prior)

`47d96bd 4ac6ce5 0f86b9f 1a66633 cd525df <docs>`

- **flag 1 — Single node Lamport clock.** `NodeLamportClock` (shared holder) injected
  into `CognitiveKernel` + `InMemoryWorldState` + `SharedContextService`. Removed the
  three independent `self._clock` instances. `node_origin` is now `node_id` everywhere
  (was hardcoded `"kernel"`), fixing causal order + federation tiebreak.
- **Reasoning Engine (parametric Deliberate component).** New `IReasoningEngine` port
  + frozen `ReasoningStep` (carries `ConfidenceScore` + `CausalMark` from the shared
  clock). `ReferenceReasoningEngine` is deterministic, LLM-free (I-09): reads Intent +
  WorldState via Attention, yields world-aware candidates. `CognitiveKernel.tick` runs
  **Reasoning → Planning → Decision**; planner signature extended to `(goal, steps)`.
- **flag D — World-aware Decision.** `IDecisionEngine.select` now receives `world` +
  `intent` via the port. `DeterministicDecisionEngine` accepts them (ignores for
  determinism). The `bind()` hack in the federation test engine is removed.
- **flag 3 — Wire key.** Federation wire emits `lamport` (was legacy `seq`).
- **Tests (K8).** `tests/test_reasoning_engine.py` (+8): acceptance + negative (reasoning
  without a world fact yields a *different* candidate; explore-only assertion).
- **Docs.** `ADR-056` (accepted) — Reasoning Engine; amendment to ADR-055 §6
  (state idempotence vs order-dependent clock, per flag 2).

**Verification:** `1010 passed, 0 failed`; gate `14 passed`; ad-hoc `13/13 PASS`.

---

## 2026-08-02 — ТЗ-CAUSAL-01 (CausalMark → Lamport) — DONE (prior)

`65a3ee2 3724248 23dc711`

- `CausalMark` rebased on Lamport logical clock (`lamport` / `node_origin`,
  `__lt__` by `(lamport, node_origin)`).
- `merge_remote` + `InMemoryWorldState.update` do `receive` on remote facts; local
  events do `tick()`. Idempotent replay (clock grows only on causally-newer marks).
- `tests/test_causal_mark_lamport.py` (+9 tests). Wire key emitted as `seq` (renamed
  to `lamport` in ТЗ-RE-01).

**Verification:** `1002 passed, 0 failed`; gate `14 passed`; ad-hoc `13/13 PASS`.

---

## Baseline — v1.0 (ТЗ-002 D2)

V1/V2/V3 CLOSED, No High Architectural Debt. Metrics: `768 passed / 0 failed /
0 open violations`.

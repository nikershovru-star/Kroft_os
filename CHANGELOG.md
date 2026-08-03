# Changelog

All notable changes to KROFT_OS are documented here, grouped by ТЗ/Wave.
Format: `commit-range | scope | summary`.

---

## 2026-08-03 — ТЗ-RF-01 (Reflection Engine, outcome-based Self-Evolving) — DONE

`29e1448 a0806f0 6454bf7 909618f 02a5e26 <docs>`

- **Commit 0 — фикс флага 2 (integration).** `CognitiveKernel` Learn-фаза больше не
  игнорирует `soft_policies` из `IMemoryEvolution.consolidate`: они коммитятся в
  `normative` с тем же Self-Evolving guard (HARD -> reject, O1; hard_violations ДО commit).
- **Контракт Reflection Engine.** `contracts/i_reflection.py`: `IReflectionEngine.reflect(
  memory, world, recent_events, outcomes) -> ReflectionReport` (PROPOSALS, не пишет память).
  `contracts/cognitive_domain.py`: `ReflectionReport` (consolidation_candidates /
  deprecation_candidates / policy_suggestions[SOFT-only] / insights + ConfidenceScore +
  CausalMark), `ExecutionOutcome` (episode_id, success, utility, confidence, causal —
  ФЛАГ 1 feedback proxy), `ProvenanceType.REFLECTION`.
- **Reference impl (LLM-free, I-09).** `kernel/reflection.py`: `ReferenceReflectionEngine`
  — OUTCOME-BASED: повторяющийся УСПЕШНЫЙ опыт (success + utility>=thr, >=N) ->
  consolidation_candidates (SemanticFact, aggregated conf + CausalMark); повторяющийся
  НЕУСПЕШНЫЙ -> deprecation_candidates. Без опыта -> пустой report.
- **Интеграция.** `CognitiveKernel` принимает `IReflectionEngine`; `tick` записывает
  `ExecutionOutcome` после Execute (proxy), затем REFLECTION-фаза ДО Learn: `reflect()`
  предлагает, kernel коммитит consolidation_candidates в semantic (O1 guard), deprecation
  -> Memory Evolution. Reflection — аналитический, Memory Evolution — исполнительный.
  `build_kernel` проводит `ReferenceReflectionEngine` (shared clock).
- **Тесты (K8).** `tests/test_reflection_engine.py` (+11): reflect yields report; OUTCOME-
  BASED (success->consolidation, failure->deprecation, assert по ExecutionOutcome не intent-
  тексту); O1 guard (report conf+causal, kernel rejects hard-violating, never emits HARD);
  negative: no experience/outcomes -> empty; ФЛАГ 2 fix (reference emits no policies, kernel
  commits SOFT with guard); ReflectionReport conf+causal node_origin.
- **Docs.** `ADR-060` (accepted) — Reflection Engine + outcome-based + ФЛАГ 1/2; AKB;
  CHANGELOG; PROJECT_STATUS.

**Verification:** full suite `1053 passed, 19 skipped, 1 xpassed, 0 failed`;
arch-gate `14 passed`; akb-lint PASSED.

---

## 2026-08-03 — ТЗ-RT-01 (Runtime / System Reflection, adaptive runtime contour) — DONE

`19fbd9f 3badd8a b71aed2 e587dc3 5d0a7c9 <docs>`

- **Commit 0 — усиление cognitive-value proof (честность NW-01).** `CognitiveKernel`
  сохраняет `_last_selected_plan` (Plan-объект, не только id) как introspection.
  Тест `test_federation_cognitive_value_changes_decision` БОЛЬШЕ НЕ сравнивает plan-ID
  (uuid всегда уникальны -> вакуумное доказательство): инжектится world-aware planner,
  federated факт `pref:blue` переворачивает ВЫБРАННЫЙ ПЛАН по СОДЕРЖАНИЮ (steps
  choose_red -> choose_blue). Cognitive value доказан СЕМАНТИКОЙ, не id.
- **Контракты (K1).** `contracts/i_runtime_reflection.py`: `IRuntimeMetrics.collect()
  -> List[RuntimeMetric]`; `IRuntimeReflection.reflect(metrics) -> List[TuningProposal]`
  (LLM-free, deterministic); `ITuningApplier.apply(proposal) -> bool` под O1 guard.
  `RuntimeMetric` / `TuningProposal` (frozen VOs); конструктор `TuningProposal` ЗАПРЕЩАЕТ
  `layer=HARD` (O1 на входе).
- **Reference impl (LLM-free, I-09).** `kernel/runtime_reflection.py`:
  `ReferenceRuntimeReflection` (правила R1-R3: low delivery -> raise timeout; fast
  memory growth -> raise min_repetitions; low consolidation conf -> raise threshold;
  old->new честно из `*.current` метрик, bounded); `ReferenceTuningApplier` (O1:
  отклоняет НЕ-SOFT/unknown/без target); `ReferenceRuntimeMetrics`.
- **Интеграция.** `kernel/runtime_supervisor.py`: `RuntimeSupervisor.step()` collect ->
  reflect -> apply (только SOFT); `build_runtime_metrics()` собирает snapshot из живых
  целей + операционных сигналов. Тюнингуемые цели (реально тюнингуемые, SOFT-only):
  `ReferenceMemoryEvolution` (min_repetitions/confidence_threshold),
  `NetworkTransport` (ensure_connected_timeout — добавлен `_connect_timeout`, K6),
  `SimpleResourceManager` (budgets.tokens). O1: FSM-инварианты/HARD/контракты неизменны.
- **Тесты (K8).** `tests/test_runtime_reflection.py` (14 passed): metrics->proposal;
  O1 apply (SOFT меняется / unknown rejected / HARD запрещён конструктором); adaptive
  behavior (выше timeout -> ensure_connected ждёт дольше; выше min_repetitions -> меньше
  консолидаций); negative (нет метрик -> нет proposals); разделение с RF-01 (runtime НЕ
  пишет semantic контент); full loop применяет 3 SOFT proposal к реальным целям.
- **Docs.** `ADR-062` (accepted) — Runtime/System Reflection + разделение с RF-01 + O1
  guard; AKB (`adrs.yaml` ADR-062, `issues.yaml` RT-01); CHANGELOG; PROJECT_STATUS.

**Verification:** full suite `1063+ passed, 0 failed`; arch-gate `14 passed`;
akb-lint PASSED; ad-hoc verifier (cognitive-value semantic) `17/17 PASS`.

---

## 2026-08-03 — ТЗ-EX-01 (Execution Layer + Real Outcome-Feedback, replacement of outcome-proxy) — DONE

`c45ceb1 824011e 6e849d0 403cb11 <docs>`

- **Commit 1 — контракты (K1).** `contracts/i_execution.py`: `IExecutor.execute(action,
  timeout) -> ExecutionResult`; `IExecutionEnvironment.step(action) -> ExecutionResult`
  (среда); `IActionAdapter` (опц., маппинг `action.kind` -> backend). `ExecutionResult`
  (frozen VO) — СЫРОЙ ответ среды (action_id/success/observation/reward/...). НЕ путать
  с `ExecutionOutcome` (RF-01), который СТРОИТСЯ ИЗ результата.
- **Commit 2 — reference impl (LLM-free, I-09).** `kernel/execution.py`:
  `ReferenceExecutionEnvironment` (deterministic rule-map: `choose_blue`->success/0.9,
  `choose_red`->fail/0.1, unknown->fail/0.0); `ReferenceExecutor` (маршрутизация по kind,
  без wall-clock sleep).
- **Commit 3 — интеграция (замена proxy).** `CognitiveKernel.attach_executor(executor)`
  + Execute-фаза: при executor выбранный Plan -> `Action(kind="execute_plan",
  payload=steps)` -> `executor.execute` -> `ExecutionResult` -> РЕАЛЬНЫЙ `ExecutionOutcome`
  (success=result.success, utility=result.reward). Без executor — **proxy fallback**
  (decision accepted / confidence), backward compat. O1: executor НЕ мутирует HARD/FSM/
  контракты.
- **Commit 4 — тесты K8 (9 passed):** execute возвращает реальный ExecutionResult;
  FAILED action -> success=False ДАЖЕ при принятом decision (negative vs proxy); реальный
  outcome заменяет proxy; repeated real failures -> RF-01 deprecation; negative (нет
  executor -> proxy, unknown -> fail); разделение Result/Outcome; O1 (executor без
  поверхности мутации HARD).
- **Commit 5 — docs.** `ADR-063` (accepted) — Execution layer + real outcome + разделение
  Result/Outcome + закрытие RF-01 ФЛАГ 2; AKB (`adrs.yaml` ADR-063, `issues.yaml` EX-01);
  CHANGELOG; PROJECT_STATUS.

**Verification:** full suite `1077+ passed, 0 failed`; arch-gate `14 passed`;
akb-lint PASSED; ad-hoc verifier (real vs proxy outcome) подтверждён в тестах.


---

## 2026-08-04 — ТЗ-SE-01 (Self-Evolution Behavioral Closure, замыкание петли) — DONE

`2bb0331 386a508 9bd91f4 5f53337 <docs>`

- **Commit 1 — контракт (K1).** `contracts/i_self_evolution.py`: `ISoftPolicySource`
  (read-side порт замыкания поведения) + `SoftPolicyPreference` (frozen VO). НЕ ломает
  сигнатуры `IValueSystem`/`IReasoningEngine` — расширение через отдельный порт.
- **Commit 2 — reference impl (LLM-free, I-09).** `kernel/self_evolution.py`:
  `MemorySoftPolicySource` (читает SOFT-слой из `ILayeredMemory` через порт, K6-clean);
  `PolicyAwareValueSystem(SimpleValueSystem)` (score += prefer/avoid бонус-штраф, O1
  SOFT-only); `KnowledgeAwareReasoning(ReferenceReasoningEngine)` (recall semantic facts
  как grounded candidates).
- **Commit 3 — интеграция.** `build_kernel` wire `MemorySoftPolicySource(memory)` ->
  `PolicyAwareValueSystem` + `KnowledgeAwareReasoning`. `SimpleValueSystem` вынесен в
  `kernel/value_system.py` (разрыв import-цикла — K5-проверка поймала). Learn-фаза:
  repeated FAILURE -> SOFT `avoid:<pattern>` policy (O1 layer=='soft', dedup). episode
  summary связан с plan steps (`decided:choose_red`).
- **Commit 4 — тесты K8 (6 passed, capstone):** repeated SUCCESS -> consolidation ->
  NEXT решение ВЫБИРАЕТ learned; repeated FAILURE -> deprecation -> NEXT ИЗБЕГАЕТ failed;
  NEGATIVE: без wiring эволюция НЕ меняет решение; O1 (avoid-policy soft, нет мутации
  HARD/FSM); K6 (чтение через порт).
- **Commit 5 — docs.** `ADR-064` (accepted) + AKB (`adrs.yaml` ADR-064, `issues.yaml`
  SE-01) + CHANGELOG + PROJECT_STATUS.

**Verification:** full suite `1086+ passed, 0 failed`; arch-gate `14 passed`;
akb-lint PASSED. Капстоун-петля замкнута: исходы -> эволюция -> deliberation читает
выученное -> решения меняются -> новые исходы. ФЛАГ 3 ТЗ-EX-01 ЗАКРЫТ.


---

## 2026-08-04 — ТЗ-LLM-01 (LLM-as-advisor plug-in + graceful fallback, валидация I-10) — DONE

`7d32578 2bd95c0 b98b63f 7659be7 <docs>`

- **Commit 1 — контракт (K1/K6).** `contracts/i_llm_advisor.py`: `ILLMAdvisor` (порт)
  + `LLMAdvice` (frozen VO) + `LLMError`/`LLMTimeout` + `AdviseContext`. `adapter_for(ILlm)`
  мостит существующий Model Platform порт `contracts/i_llm.ILlm` в advisor (порт НЕ
  дублирован — KROFT «one port per boundary»). Ядро зависит только от `ILLMAdvisor`.
- **Commit 2 — reference impl (LLM-free core сохранён).** `kernel/llm_advisor.py`:
  `MockLLMClient` (детерминированный rule-based advisor; `fail=True` -> `LLMError`);
  `LLMAdvisorReasoning(KnowledgeAwareReasoning)` (boosted step из advice; сбой ->
  fallback на reference); `LLMAdvisorPlanner(ReferencePlanner)` (re-rank через advice;
  сбой -> `super().plan()` чистый reference result). LLM НЕ выбирает финал (I-03).
- **Commit 3 — интеграция.** `build_kernel(node_id, clock, llm_client=None)`: advisor
  опционален (`ILlm` через `adapter_for` ИЛИ `ILLMAdvisor`); без client -> `advisor=None`
  -> обёртки == PURE reference (поведение идентично LLM-free build). Интеграционный
  капстоун: `build_kernel()` == `build_kernel(MockLLMClient(fail=True))` по
  `selected_plan.steps` — kernel LLM-free ПО СУТИ, не по декларации.
- **Commit 4 — тесты K8 (7 passed):** advice меняет ranking (boosted->фронт), но
  Decision (не LLM) выбирает; `LLMError`/`LLMTimeout` -> fallback == результат без
  LLM (без краша); без LLM неизменно; LLM НЕ выбирает, advisor read-only (O1); K6
  (kernel зависит только от порта).
- **Commit 5 — docs.** `ADR-065` (accepted) + AKB (`adrs.yaml` ADR-065, `issues.yaml`
  LLM-01) + CHANGELOG + PROJECT_STATUS.

**Verification:** full suite GREEN; arch-gate `14 passed`; akb-lint PASSED. I-10
(kernel purity) ТЕПЕРЬ ПРОВЕРЕНО КОДОМ, а не декларацией.


- **Commit 0 — фикс флага 1 (integration, ТЗ-RF-01).** Reflection больше НЕ коммитит
  semantic; ME-01 — единственный writer SOFT-слоя; дедупликация против уже
  закоммиченных `get_semantic()` (не только внутри тика). Один опыт → ровно 1 факт.
- **Commit 1 — детерминизация WP14-RACE.** `RaftLiteElector.wait_leader` /
  `CrdtGraphEngine.wait_node` — барьеры (`threading.Event`), просыпаются на событии
  выбора лидера, НЕ на `time.sleep`. xfail снят. ФЛАГ 2 (ADR-061): `RaftLiteElector` —
  упрощённый Raft (нет self-election в 2-узловой паре, split-brain при симметричном
  старте); кластерные тесты → 3+ узла или assert «ровно один лидер».
- **Commit 2 — контракт.** `contracts/i_network_transport.py`: `INetworkTransport`.
  `contracts/i_distributed_runtime.py`: `ISharedContext.replicate_to` (non-abstract).
- **Commit 3 — impl (K6).** `adapters/network_transport.py`: `NetworkTransport`
  (поверх `TcpEventBus`, background retry + `ensure_connected` барьер). K5-поймал:
  `ISharedContext` в `i_distributed_runtime.py` (не `i_shared_context.py`);
  `CognitiveEvent.from_bus` не существовал; `CalibrationType` без `'MODEL'`.
  `services/distributed_runtime.py`: `SharedContextService.replicate_to` (real) +
  `NetworkFederationService` (receiver-side causal merge, K6: только через порт).
- **Commit 4 — интеграция ядер.** `kernel/cognitive_kernel.py`: `InMemoryWorldState.apply_remote`
  (causal merge в SSOT) + `CognitiveKernel.attach_federation` (идемпотентный, проверяемый).
- **Commit 5 (CONT) — закрыть ФЛАГ 1 (блокер).** `attach_federation` проверяет wiring
  (receiver → `_on_federated_world` по `__func__`/`__self__`), receiver lock после bind
  (пост-attach override игнорируется). `NetworkFederationService.receiver`/`has_receiver`/
  `lock_receiver`.
- **Tests (K8).** `tests/test_network_federation.py` (+10): реальная репликация
  CognitiveEvent/WorldState через TCP; PARTITION→RECONNECT causal merge (idempotent);
  ДЕТЕРМИНИЗМ (--count=5); FEDERATION COGNITIVE VALUE (Decision@B меняется от federated
  факта); ФЛАГ 1 (нет дублей SemanticFact); 3-узловой leader (ровно один).
- **Docs.** `ADR-061` (accepted) — Real Network Federation + честные ограничения
  `RaftLiteElector`. `issues.yaml`: WP14-RACE closed, NW-01 added.

**Verification:** ad-hoc `hermes-verify-nw01-flag1.py` `7/7 PASS`; B facts != 0;
cognitive value доказан (base_plan != fed_plan); gate `14`; full suite 0 failed.


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

## 2026-08-04 — ТЗ-FSE-01 (Federated Self-Evolution, коллективное обучение) — DONE

Кульминация «локально и в сети»: выученный SOFT-слой (semantic facts + soft policies)
федерируется и меняет поведение КАЖДОГО узла. Переиспользует NW-01 (NetworkFederationService
+ расширенный INetworkTransport), не изобретая транспорт.

- **Commit 1 — контракт + ADR-066.** `INetworkTransport` расширен вторым каналом:
  `send_soft_layer(items, sender_node_id)` + `on_soft_layer(handler)` (топик `cog.soft`,
  зеркально `cog.facts`). `SoftLayerItem` (frozen VO wire-DTO, НЕ duck-object — урок
  Флага 1 LLM-01): kind/content/confidence/origin/causal/provenance + to_wire/from_wire.
  ADR-066 ЯВНО фиксирует что федерировать: semantic=ДА; soft policies=ДА с confidence-гейтом
  + provenance; HARD=НИКОГДА (O1). Гейты двойные (sender+receiver).
- **Commit 2 — reference impl (LLM-free, K1).** `FederationSoftMemorySync`
  (services/distributed_runtime.py): sender собирает semantic+soft (conf>=threshold), НЕ
  ships HARD; receiver мержит с ВТОРЫМ confidence-гейтом, dedup, provenance сохранён.
  Read-side SE-01 (`MemorySoftPolicySource`/`KnowledgeAwareReasoning`) НЕ меняется.
- **Commit 3 — интеграция.** `build_kernel` + `attach_soft_memory_sync`: после локальной
  Learn-фазы learned layer реплицируется; inbound мержится в `ILayeredMemory` и влияет на
  СЛЕДУЮЩУЮ Decision. HARD не шлётся (O1). Optional: no-op без sync.
- **Commit 4 — тесты K8 (4 passed, capstone).** A учит avoid:X (repeated FAILURE) ->
  федерация (реальный NetworkTransport localhost TCP) -> B (БЕЗ опыта) ИЗБЕГАЕТ X.
  NEGATIVE: без федерации B НЕ избегает (доказывает причину). Confidence-гейт: low lesson
  НЕ рассылается. O1: HARD НЕ шлётся; provenance origin сохраняется. Тесты нашли баг:
  `lock_receiver` отключал receiver -> исправлено.
- **Commit 5 — docs.** ADR-066 + issues + CHANGELOG + PROJECT_STATUS.

Капстоун (доказательство коллективного обучения): узел A наступает на грабли (FAIL по X),
выучивает avoid:X, рассылает -> узел B, НЕ испытавший неуспеха, начинает ИЗБЕГАТЬ X.
Ядро LLM-free; федерация знаний, не моделей (I-10).

**Verification:** `1103 passed, 0 failed`; gate `14 passed`; ad-hoc `10/10 PASS`; akb-lint PASSED.

---

## Baseline — v1.0 (ТЗ-002 D2)

V1/V2/V3 CLOSED, No High Architectural Debt. Metrics: `768 passed / 0 failed /
0 open violations`.

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

## 2026-08-04 — ТЗ-OBS-01 (Observability, автономная runtime-адаптация) — DONE

Закрывает долг RT-01: метрики были injectable-snapshot (адаптация не автономна). OBS-01
инструментирует ядро/execution/память живыми счётчиками и кормит RuntimeSupervisor,
который адаптируется АВТОНОМНО (collect->reflect->apply каждые N tick, Флаг 3).

- **Commit 1 — контракт + ADR-067.** `ILiveMetricsCollector` (contracts/i_observability.py)
  — ОТДЕЛЬНАЯ граница от `contracts/i_metrics.py: IMetricsCollector` (системный psutil-порт;
  KROFT one-port-per-boundary, переименование чтобы не дублировать). Канонические имена
  метрик СОВПАДАЮТ с RT-01 rule names (R1/R3).
- **Commit 2 — reference impl (LLM-free, K1).** `LiveMetricsCollector`: хранит num/den,
  вычисляет RATIOS (Флаг 1: success_rate=success/total, delivery=delivered/(delivered+dropped),
  fallback=fallbacks/calls; growth=episodes/ticks окно). `consolidation_confidence` = avg
  utility за скользящее окно (Флаг 2: пустое -> carry-last, нет истории -> 0.5, НЕ
  «нет значения»). `LiveRuntimeMetrics(IRuntimeMetrics)` читает ЖИВЫЕ счётчики + tunable
  (mirrors build_runtime_metrics). `ReferenceRuntimeMetrics` injectable СОХРАНЁН (RT-01 цел).
- **Commit 3 — интеграция.** `build_kernel(live_metrics=)`: wire LiveRuntimeMetrics +
  RuntimeSupervisor (targets memory.confidence_threshold/min_repetitions). Hook-точки в
  tick(): execution success/fail, consolidation growth, record_tick; supervisor.step()
  каждые N=3 tick (Флаг 3, anti-thrash). No-op без collector (поведение ядра не меняется).
- **Commit 4 — тесты K8 (5 passed, capstone).** degraded (choose_red -> low reward) ->
  живая consolidation_confidence < 0.6 -> supervisor АВТОНОМНО поднимает confidence_threshold
  (R3) -> measurably меньше консолидаций. NEGATIVE: здоровые (choose_blue) -> порог не
  ползёт. O1: только SOFT; no-op без collector.
- **Commit 5 — docs.** ADR-067 + issues + CHANGELOG + PROJECT_STATUS.

Capstone (автономная адаптация из живых метрик): без injectable snapshot supervisor сам
поднимает порог при degraded-исходах. Ядро LLM-free; телеметрия для инспекции всей
построенной сложности (федерация, эволюция, LLM-advisor).

**Verification:** `1108 passed, 0 failed`; gate `14 passed`; ad-hoc `TBD`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-LLM-02 (Model Platform: concrete OpenAI-compatible ILlm adapter) — DONE

Завершает «LLM = сменный инструмент» (I-10): concrete adapter поверх pluggable
IHttpTransport, contract-тесты БЕЗ живой модели/сети (fake transport). Bridge через
adapter_for -> ILLMAdvisor -> kernel доказан на реальном-по-форме клиенте; graceful
fallback == результат без LLM. Заодно кормит llm.fallback_rate (Флаг 2 OBS-01).

- **Commit 1 — контракт + adapter.** `IHttpTransport` (contracts/i_http.py): `request() ->
  HttpResponse` + TransportError/TransportTimeout — ОТДЕЛЬНАЯ граница (one-port-per-
  boundary). `OpenAiCompatibleClient(ILlm)` (adapters/openai_compatible.py) поверх
  IHttpTransport; ModelQuery.prompt -> OpenAI /chat/completions; transport error ->
  LLMError / LLMTimeout. `LlmResponse.actual_model` обязателен (ADR-065 double-routing).
  K1: adapters импортируют только contracts + stdlib (НЕТ provider SDK, K6).
- **Commit 2 — bridge readiness.** advisor-обёртки (LLMAdvisorReasoning/Planner) получают
  collector + record_failure(METRIC_LLM_FALLBACK_RATE) на LLMError/LLMTimeout. Bridge
  adapter_for(ILlm) уже готов (LLM-01).
- **Commit 3 — интеграция.** build_kernel(llm_client=, live_metrics=) проводит collector в
  advisor-обёртки. BUG FIX: LiveMetricsCollector.record_failure НЕ инкрементил _fail, ratio
  не считал fallback_rate -> метрика была 0; исправлено (fallback_rate = failures/total).
- **Commit 4 — тесты K8 (8 passed, fake transport).** adapter satisfies ILlm (success ->
  LlmResponse(actual_model)); adapter_for -> LLMAdvice; error/timeout -> LLMError/LLMTimeout
  -> fallback == без LLM; fallback_rate инкрементируется (3/3=1.0). BUG FIX: adapter_for
  перепаковывал LLMTimeout в LLMError — пробрасываем как есть (timeout vs error distinct).
- **Commit 5 — docs.** ADR-068 + issues + CHANGELOG + PROJECT_STATUS.

Capstone (bridge на реальном клиенте): concrete OpenAiCompatibleClient + fake transport ->
adapter_for -> ILLMAdvisor -> kernel; error/timeout -> graceful fallback == no-LLM result;
llm.fallback_rate растёт. Ядро LLM-free; I-10 «LLM = сменный инструмент» доказан кодом.

**Verification:** `1116 passed, 0 failed`; gate `14 passed`; ad-hoc `TBD`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-SEARCH-01 (Knowledge Search / Retrieval) — DONE

Завершена первая платформенная волна применимости: детерминированное ИЗВЛЕЧЕНИЕ
накопленных знаний по запросу (LLM-free, I-09). `ISearchService` (contracts/i_search.py)
+ `SearchHit` (frozen VO) + `SearchScope` (semantic/episodic/normative/graph/all).
`ReferenceSearchService` (kernel/search.py) — STANDALONE read-only сервис поверх
СУЩЕСТВУЮЩИХ источников (ILayeredMemory.get_semantic/episodes/normative + IGraphEngine.nodes()),
БЕЗ дублирования content_index/knowledge graph (K5-разведка: порт не существовал → создан;
индексы уже есть → переиспользованы).

Четыре reviewer-флага встроены (обязательны):
- **Флаг A** — НЕ индексировать при каждом search: PURE-SCAN по источникам, НЕ пишем в
  разделяемый ContentIndex (без side-effect, детерминированно).
- **Флаг B** — ТОТАЛЬНЫЙ порядок ранжирования (confidence desc, relevance desc, id asc):
  стабильный тай-брейкер по id → идентичный результат при повторе (I-09).
- **Флаг C** — search НЕ проводится в build_kernel/kernel.search(): сервис standalone,
  ядро не зависит от search (K6), god-factory (Флаг 1 OBS-01) не усугубляется.
  `build_search_service(memory, graph)` — отдельная фабрика, не в kernel.
- **Флаг D** — `SearchHit.causal: Optional[CausalMark]` (реальный тип, не object);
  граф-ноды без confidence/causal → нейтральный дефолт (0.5) + causal=None, ранжирование
  единообразно между слоями.

- **Commit 1+2 — контракт + impl.** `contracts/i_search.py` (ISearchService/SearchHit/
  SearchScope, K1: contracts+stdlib); `kernel/search.py` (ReferenceSearchService, pure-scan,
  total-order ranking, O1 read-only).
- **Commit 3 — интеграция как standalone сервис.** `build_search_service` (Флаг C).
- **Commit 4 — тесты K8.** `tests/test_knowledge_search.py`: 14 тестов (relevant hits,
  total-order ranking, scope-фильтр, negative empty/no-match/unknown-scope → [],
  детерминизм, O1 read-only, causal real type, factory).
- **Commit 5 — docs.** ADR-069 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

**Verification:** `1118 passed, 0 failed`; gate `14 passed`; ad-hoc `TBD`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-RESEARCH-01 (Research Service) — DONE

Завершена вторая платформенная волна применимости: детерминированный исследовательский
цикл ПОВЕРХ SEARCH-01 (извлечение -> синтез -> опц. SOFT-запись), LLM-free по умолчанию (I-09).
`IResearchService` (contracts/i_research.py) + `ResearchReport`/`ResearchGoal` (frozen VO,
реальные типы: findings: Tuple[SearchHit], causal: Optional[CausalMark]). `ReferenceResearchService`
(kernel/research.py) — STANDALONE read-first сервис поверх СУЩЕСТВУЮЩЕГО ISearchService
(НЕ дублирует порт поиска, K5-разведка: IResearchService не существовал → создан;
ISearchService/ILayeredMemory/ILLMAdvisor уже есть → переиспользованы).

Четыре обязательных ограничения встроены:
- **Флаг C (SEARCH-01)** — НЕ в build_kernel: `build_research_service` отдельная standalone
  фабрика; ядро не зависит от research (K6), god-factory (Флаг 1 OBS-01) не усугубляется.
- **I-09 (determinism)** — LLM-free путь детерминирован: summary = top-finding content
  (search total-order Флага B SEARCH-01), aggregate confidence = mean; повторный goal →
  идентичный report.
- **LLM-01/02 (fallback)** — опц. ILLMAdvisor; при LLMError/LLMTimeout → graceful fallback на
  retrieval-only summary (== результат без LLM); fallback сам детерминирован.
- **O1 (SOFT-only)** — write-back ТОЛЬКО через commit_semantic (SOFT), под opt-in
  `write_back=True`; НЕ трогает HARD/FSM/контракты.

- **Commit 1 — контракт.** `contracts/i_research.py` (IResearchService/ResearchReport/ResearchGoal, K1).
- **Commit 2+3 — impl + integration.** `kernel/research.py` (ReferenceResearchService,
  LLM-free cycle, O1 SOFT write-back; build_research_service standalone фабрика).
- **Commit 4 — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b/4).** `tests/test_research_service.py`:
  13 тестов (report+findings, determinism, aggregate conf, negative, LLM fallback ==
  retrieval-only, O1 SOFT write-back, factory standalone).
- **Commit 5 — docs.** ADR-070 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

**Verification:** `1130 passed, 0 failed`; gate `14 passed`; ad-hoc `TBD`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-PLUGIN-01 (Plugin Registry) — DONE

Завершена третья платформенная волна применимости: детерминированный реестр внешних
capabilities за портом (register/list/invoke), LLM-free (I-09), standalone (Флаг C).
`ICapabilityPlugin` + `IPluginRegistry` (contracts/plugin.py) + `ReferencePluginRegistry`
(kernel/plugin.py) + reference-плагины `SearchPlugin`/`ResearchPlugin`, ОБЁРТКИ над
существующими `ISearchService`/`IResearchService` (К5: переиспользование, НЕ дублирование).

К5-разведка (commit 0) критична: `IPlugin` (CLI/export/crawl, Stage 25) УЖЕ существовал в
`contracts/plugin.py`. Создание второго `IPlugin` в `i_plugin.py` = дублирование границы
(запрещено). Введён отдельный invoke-capable под-порт `ICapabilityPlugin` (one-port-per-
boundary); существующий test_plugins.py (CLI IPlugin) НЕ сломан (10/10 green). `ICapabilityRegistry`
(runtime) — другой реестр (именованные capabilities), НЕ затронут.

Обязательные ограничения встроены:
- **Флаг C (SEARCH/RESEARCH)** — НЕ в build_kernel: `build_plugin_registry` отдельная standalone
  фабрика; ядро не зависит от registry (K6), god-factory (Флаг 1 OBS-01) не усугубляется.
- **I-09 (determinism)** — list() сортирован по id (стабильный порядок); invoke детерминирован.
- **O1 (read-only)** — reference-плагины ТОЛЬКО читают (search/research), НЕ мутируют HARD/FSM/
  контракты; registry НЕ мутирует плагины.
- **K8 (negative)** — unknown-id invoke -> PluginResult(ok=False, error); duplicate register ->
  PluginInvocationError; unregister unknown -> no-op.

- **Commit 1 — контракт (расширение, К5).** `contracts/plugin.py`: ICapabilityPlugin, IPluginRegistry,
  PluginManifest/PluginResult (frozen VO), PluginInvocationError; IPlugin (CLI) не тронут.
- **Commit 2+3 — impl + integration.** `kernel/plugin.py`: ReferencePluginRegistry + SearchPlugin/
  ResearchPlugin (обёртки) + build_plugin_registry (standalone фабрика).
- **Commit 4 — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b).** `tests/test_plugin_registry.py`: 14 тестов
  (register/list/get, invoke->PluginResult, determinism, unregister, duplicate->error, unknown->
  error, O1 read-only, composition, factory).
- **Commit 5 — docs.** ADR-071 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

**Verification:** `1143 passed, 0 failed`; gate `14 passed`; ad-hoc `TBD`; akb-lint PASSED.

---

## 2026-08-04 — God-factory refactor (ТЗ-OBS-01 Флаг 1 debt CLOSED)

Долг закрыт: `kernel/cognitive_kernel.build_kernel` перестал быть god-factory. Композиция
опциональных подсистем (llm_client, live_metrics, bus) вынесена в единый composition root
`KernelBuilder` (`kernel/kernel_builder.py`), параметры — в декларативный `KernelConfig`
(`kernel/kernel_config.py`).

Обязательные свойства рефакторинга:
- **Обратная совместимость**: сигнатура `build_kernel(node_id, clock, llm_client, live_metrics)`
  сохранена (48 существующих вызовов не сломаны) + добавлен опц. `config: KernelConfig`.
  kwargs WIN над config.
- **Не распухает**: новые опц. подсистемы будущих ТЗ = поле `KernelConfig` + ветка в
  `KernelBuilder`, НЕ новый параметр `build_kernel`.
- **Behavioural-equivalence доказана**: полный прогон ДО и ПОСЛЕ = 1157 passed / 0 failed
  (идентично). Latent-баг найден и исправлен: reason/planner ВСЕГДА LLMAdvisor-варианты
  (advisor=None -> pure path, но attach_metrics доступен для live collector) — иначе
  live_metrics-only path падал бы.
- **Флаг 3 (process lesson)**: агрессивная чистка импортов сломала публичный re-export API
  (test_self_evolution_closure импортирует ReferencePlanner/ReferenceWorldModel/... из
  kernel.cognitive_kernel). Восстановлено; долгосрочно — перевести тесты на импорт из
  реальных модулей (kernel.planning и т.д.), снизив связность через cognitive_kernel.
- **K1/K6**: builder импортирует только kernel + contracts (порт ILLMAdvisor, не конкретный
  LLM-клиент). Standalone, НЕ в build_kernel (не усугубляет god-factory).

- **Commit 1** — `kernel/kernel_config.py` + `kernel/kernel_builder.py` (extraction).
- **Commit 2** — `kernel/cognitive_kernel.py`: build_kernel -> thin wrapper (re-exports kept).
- **Commit 3** — тесты K8 эквивалентности (отдельный коммит, Флаг 1b): 9 тестов.
- **Commit 4** — docs (этот раздел + PROJECT_STATUS + AKB debt-closed note).

**Verification:** `1157 passed, 0 failed`; gate `14 passed`; ad-hoc god-factory 8/8; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-IDT-01 (Identity & Trust layer) — DONE

Закрыта дыра FSE-01: знания федератировались БЕЗ проверки доверия. IDT-01 вводит Identity
(агент как постоянный участник) + Trust (trust-score/version/author/rollback) + trust-гейтинг
федерации.

K5-разведка (commit 0) критична: порт Identity/Trust НЕ существовал. `AgentState` (ТЗ-AGENT-001,
lifecycle-FSM) УЖЕ есть — ДРУГАЯ граница, НЕ дублируем. `Provenance`/`CausalMark` (cognitive_domain)
переиспользуются для trust-метаданных. `FederationSoftMemorySync` (FSE-01) УЖЕ есть БЕЗ gating —
расширен опционально (НЕ дублирован).

- **Commit 1** — контракт (К5, НЕ дублирован): `contracts/i_identity.py` — `AgentIdentity` (frozen
  VO), `IIdentityRegistry`, `TrustMeta` (frozen VO: item_id, trust_score, version, author_id,
  rollback_pointer), `ITrustRegistry`, `IActionLog`.
- **Commit 2** — impl: `kernel/identity.py` — `ReferenceIdentityRegistry` / `ReferenceTrustRegistry`
  / `ReferenceActionLog` (in-memory, deterministic, LLM-free). `trust_score_of` агрегирует MAX
  записанный trust_score по author (unknown -> 0.0).
- **Commit 3** — FSE-01 integration (extend, not break, Флаг C): `SoftLayerItem` + `author_id`
  (Optional, обратно совместимо); `FederationSoftMemorySync.__init__` + опц. `trust_registry`
  / `trust_threshold` (после confidence_threshold -> позиционные вызовы FSE-01 целы). Sender
  помечает author_id=origin; receiver отклоняет ВЕСЬ batch, если trust_score_of(sender) < threshold.
  БЕЗ registry -> поведение byte-for-byte pre-IDT-01 (default permissive) -> FSE-01 тесты зелёные.
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_identity_trust.py` — 10 тестов
  (identity/action-log/trust/FSE-gating/rollback/determinism/negative/FSE-без-registry).
- **Commit 5** — docs: ADR-072 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (contracts + stdlib; services→contracts only); O1 (реестры НЕ мутируют HARD/FSM);
I-09 (determinism: MAX-агрегация trust, чистый threshold); Флаг C (standalone, НЕ в build_kernel,
god-factory не усугубляется); K8 (unknown id -> None, low-trust reject, FSE-01 без registry неизменен).

Долги (задокументированы в ADR-072, non-scope): real cryptographic signing (future); per-agent
(не per-node) trust (author_id уже в DTO, но FSE-01 уровня узла author==origin); обмен агентами
(не только знаниями) — future.

**Verification:** `1157 passed, 0 failed` baseline + 10 IDT тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-ORCH-01 (Trust-aware orchestration) — DONE

Построенные слои (Identity/Trust/Plugins) стали ПОВЕДЕНИЕМ: оркестратор маршрутизирует goal к
лучшему исполнителю (agent ИЛИ plugin) по specialization-match * trust, исключает
permission-violating / low-trust, исполняет, логирует в IActionLog и обновляет trust из исхода
(успех +, провал -) — trust ЭВОЛЮЦИОНИРУЕТ, замыкая петлю (фокус ТЗ-ORCH-01).

K5-разведка (commit 0) критична: trust-aware ROUTING НЕ существовал. Переиспользованы (НЕ
дублированы): `IIdentityRegistry`/`ITrustRegistry`/`IActionLog` (IDT-01), `IPluginRegistry`
(PLUGIN-01). `IAgentPlatform` (ТЗ-AGENT-001) — agent-platform, НЕ оркестратор -> НЕ трогаем
(реальное мульти-агент исполнение через сеть — future, NW-01). `ITrustRegistry` расширен
(record_outcome/current_trust/seed) -> orchestrator читает LATEST running-trust (НЕ MAX), что
закрывает Флаг 1 IDT-01 (trust-then-attack: провал реально понижает trust).

- **Commit 1** — IDT-01 follow-up: `ITrustRegistry.record_outcome`/`current_trust`/`seed`
  (contracts/i_identity.py + kernel/identity.py); `trust_score_of` (MAX, FSE-01) НЕ тронут.
- **Commit 2** — контракт (К5, НЕ дублирован): `contracts/i_orchestrator.py` —
  `OrchestrationGoal`/`RoutingDecision`/`TaskOutcome`/`IOrchestrator` (frozen VO, реальные типы).
- **Commit 3** — impl + `build_orchestrator` фабрика (Флаг C, standalone, НЕ в build_kernel):
  `kernel/orchestrator.py` — `ReferenceOrchestrator` (score=spec*trust, exclusion, max+tie-break
  id; dispatch -> log + trust update из исхода).
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_orchestrator.py` — 8 тестов
  (route by spec+trust, permission/low-trust exclusion, trust evolves, negative, determinism).
- **Commit 5** — docs: ADR-073 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (contracts + stdlib; kernel→contracts only); O1 (реестры НЕ мутируют HARD/FSM;
trust-обновления SOFT); I-09 (scoring + тай-брейкер по id детерминированы); Флаг C (standalone,
НЕ в build_kernel); K8 (no eligible -> None, low-trust/permission exclusion).

Долги (задокументированы в ADR-073, non-scope): реальное мульти-агент исполнение через сеть
(NW-01) — reference делегирует агента и логирует исход; RL/сложное планирование — только
детерминированный scoring.

**Verification:** `1157 passed, 0 failed` baseline + 10 IDT + 8 ORCH тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-SKILL-01 (Procedural Memory / Skills) — DONE

Memory Layer ЗАВЕРШЁН: процедурная память. Успешные последовательности действий консолидируются
в Procedure (skill), который orchestrator вспоминает (recall) вместо повторного вывода. Эволюция
стала продуктивной: опыт (repeated success) -> Procedure -> recall.

K5-разведка (commit 0) КРИТИЧНА: ТЗ предписывал `contracts/i_procedural.py` (IProceduralMemory +
Skill VO), НО `IProceduralMemory` УЖЕ есть в `contracts/i_memory.py` (Wave 9/ADR-012) +
`InMemoryProceduralMemory` в `services/memory_platform.py`, а `class Skill` УЖЕ есть в
`contracts/cognitive_domain.py` (Marketplace/TZ-021). Дублирование порта/класса = нарушение K5
one-port-per-boundary. Решение: расширен СУЩЕСТВУЮЩИЙ `IProceduralMemory` (store_skill/
recall_skill_by_capability/list_skills/has_skill) + добавлен `Procedure` VO (frozen, НЕ Skill).
Старые record_procedure/recall_procedure СОХРАНЕНЫ (обратная совместимость, тесты целы).

- **Commit 1** — `contracts/i_memory.py` (Procedure VO + IProceduralMemory extension) +
  `services/memory_platform.py` (impl). K5: существующий порт, НЕ дублирован.
- **Commit 2** — `kernel/procedural.py`: `ProcedureConsolidator` (детерминированный learning из
  repeated success, >= threshold + >= min_rate; idempotent store_skill один раз; steps первого
  успеха) + `build_procedural` фабрика (Флаг C, standalone).
- **Commit 3** — `kernel/orchestrator.py` (ORCH-01): `ReferenceOrchestrator` опц. принимает
  `IProceduralMemory`; `route()` сначала `recall_skill_by_capability` -> `RoutingDecision(
  kind='skill', rationale='skill-recall:<cap>')`, переопределяя обычный routing. Standalone (Флаг C).
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_procedural_memory.py` — 9 тестов
  (store/recall, consolidation из repeated success, idempotent, skill-recall, negative, O1 SOFT, I-09).
- **Commit 5** — docs: ADR-074 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (contracts+stdlib; kernel/services->contracts only); O1 (Procedure SOFT; orchestrator
НЕ мутирует skill); I-09 (консолидация/recall детерминированы, order-independent, idempotent);
Флаг C (standalone, НЕ в build_kernel); K5 (НЕ дублирован IProceduralMemory/Skill/ILayeredMemory/ORCH);
K8 (no skill -> обычный routing; recall None для unknown).

Долги (задокументированы в ADR-074, non-scope): реальное мульти-агент исполнение (NW-01) — agent
outcomes придут оттуда (Флаг 2 ORCH-01: agent-trust монотонно растёт до NW-01); RL/авто-синтез
процедур — только детерминированная консолидация из лога; LLM-backed skill synthesis — future.

**Verification:** `1157 passed, 0 failed` baseline + 10 IDT + 8 ORCH + 9 SKILL тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-FED-ORCH-01 (Federated orchestration) — DONE

Закрывает Флаг 2 ORCH-01: реальный remote-outcome обновляет trust узла (failure РЕАЛЬНО понижает).
ORCH-01 дал оркестрацию, но agent-dispatch был always-success (реальный исход придёт с сетью);
NW-01 дал транспорт + trust-гейтинг (IDT-01). ТЗ-FED-ORCH-01 связал их.

K5-разведка (commit 0) КРИТИЧНА: `INetworkTransport` (NW-01) — broadcast-only, НЕТ
request/response RPC для goal-dispatch. Решение: создан НОВЫЙ порт `IRemoteOrchestrator`
(request/response dispatch) — K5-чисто (транспорт ≠ оркестрация); `INetworkTransport`
переиспользован КАК carrier (send_facts/on_facts несут dict-конверты по correlation-id).
`ITrustRegistry` (IDT-01) переиспользован: trust-gating через `current_trust` (LATEST, НЕ MAX),
обновление через `record_outcome` из реального исхода. `ReferenceOrchestrator` (ORCH-01) расширен.

- **Commit 1+2** — `contracts/i_federated_orchestrator.py` (RemoteGoalRequest/RemoteOutcomeResponse
  frozen VO + IRemoteOrchestrator) + `kernel/federated_orchestrator.py` (ReferenceRemoteOrchestrator:
  trust-gating `current_trust(node) >= threshold`; после реального outcome -> `record_outcome`;
  failure 0.9->0.8).
- **Commit 3** — `kernel/orchestrator.py` (ORCH-01): `ReferenceOrchestrator` опц. принимает
  `IRemoteOrchestrator` + `remote_nodes`; `route()` fallback на доверенный remote при отсутствии
  локального eligible (tie-break по node_id); `dispatch()` kind='remote' -> `dispatch_remote`.
  Standalone (Флаг C), обратная совместимость (remote=None -> локальный routing цел).
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_federated_orchestration.py` —
  9 тестов (real remote outcome; trust evolves from remote failure/success; trust-gating excludes
  low-trust; orchestrator fallback; low-trust-only -> None; determinism; no-remote local intact).
- **Commit 5** — docs: ADR-075 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (contracts+stdlib; kernel/services->contracts only); O1 (trust SOFT; remote НЕ
мутирует HARD/FSM); I-09 (correlation по request_id, tie-break по node_id, FakeTransport
детерминирован); Флаг C (standalone, НЕ в build_kernel); K5 (НЕ дублирован INetworkTransport/
ITrustRegistry/ReferenceOrchestrator; новый порт IRemoteOrchestrator оправдан); K8 (low-trust
исключён, нет remote -> локальный routing цел). GitS Network Layer реализован: узлы обмениваются
исполнением задач (goal -> remote -> outcome), НЕ только знаниями.

Долги (задокументированы в ADR-075, non-scope): multi-hop routing / discovery узлов (только прямой
dispatch на известные); LLM-backed remote исполнение; консенсус между узлами (только trust-gating).

**Verification:** `1157 passed, 0 failed` baseline + 10 IDT + 8 ORCH + 9 SKILL + 9 FED тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-FED-EXEC-01 (Remote execution listener) — DONE

Капстоун без фейков: серверная половина FED-ORCH-01. FED-ORCH-01 дал клиентскую сторону
(dispatch_remote + trust-эволюция), но responder был фейковым (`FakeTransport`). ТЗ-FED-EXEC-01
добавляет сервер: узел-слушатель принимает `RemoteGoalRequest`, исполняет СВОИМ локальным
`ReferenceOrchestrator`/плагином и возвращает РЕАЛЬНЫЙ `TaskOutcome`. Два узла обмениваются
исполнением без фейков; trust обновляется из реально вычисленного исхода. Завершает GitS Network
Layer (Tachikoma: автономные сервисные агенты на узлах).

K5-разведка (commit 0) КРИТИЧНА: `INetworkTransport` (NW-01) — broadcast-only carrier; FED-ORCH-01
wire-helpers были ПРИВАТНЫ в `kernel/federated_orchestrator.py` -> централизованы в
`contracts/i_federated_orchestrator.py` (commit 1): `REQ_MARKER`/`RESP_MARKER` +
`encode_goal_request`/`decode_goal_request`/`encode_outcome_response`/`decode_outcome_response`/
`is_goal_request`/`is_outcome_response` — single-source-of-truth; client отрефакторен на них
(behaviour-preserving, доказано 9/9 FED-ORCH-01 тестами). НОВЫЙ порт `IRemoteExecutionListener`
(server, НЕ дублирует client — one-port-per-boundary).

- **Commit 1** — контракт: централизован wire-формат + `IRemoteExecutionListener` (start/stop;
  on_facts, фильтр по node_id, локальный dispatch, send ответа). `ReferenceOrchestrator` (ORCH-01)
  переиспользуется для исполнения.
- **Commit 2** — `kernel/federated_executor.py`: `ReferenceRemoteExecutionListener` (server) поверх
  `INetworkTransport` (carrier) + `IOrchestrator`; `build_remote_execution_listener` (Флаг C).
- **Commit 3** — `build_federated_node` + `FederatedNode` (Флаг C, standalone, НЕ в build_kernel):
  узел = client + server, делят ОДИН orchestrator + trust + transport; два in-process узла
  диспетчеризуют друг на друга (SyncTransport in тестах; real TCP NW-01 опц, как FSE-01).
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_federated_execution.py` — 6
  тестов (two-node real execution success/failure; trust evolves from real outcome, failure 0.9->0.8;
  trust-gating excludes low-trust; determinism; negative request-not-for-this-node ignored;
  O1 server no remote trust mutation). НАЙДЕН+ИСПРАВЛЕН реальный баг: client+server на одном transport
  перезаписывали on_facts-слот -> fan-out (node_id -> list[handler]).
- **Commit 5** — docs: ADR-076 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (contracts+stdlib; kernel→contracts only); O1 (trust SOFT; server НЕ мутирует
remote trust); I-09 (correlation request_id, fan-out, SyncTransport детерминирован); Флаг C
(standalone, НЕ в build_kernel); K5 (НЕ дублирован INetworkTransport/IRemoteOrchestrator/
ReferenceOrchestrator; НОВЫЙ серверный порт; wire single-source-of-truth); K8 (чужой запрос игнор,
low-trust исключён). GitS Network Layer ЗАВЕРШЁН. Закрывает Флаг 2 ORCH-01 на сетевом уровне
(failure 0.9->0.8).

Долги (задокументированы в ADR-076, non-scope): multi-hop routing / discovery; LLM-backed remote
exec; консенсус между узлами (только trust-gating).

**Verification:** `1202 passed, 0 failed` baseline + 9 FED + 6 FED-EXEC тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-LLM-LIVE-01 (Real HTTP transport + local-model + graceful fallback) — DONE

Capstone «интеллекта»: LLM становится РЕАЛЬНО подключаемым. K5-разведка (commit 0): `IHttpTransport`
(contracts/i_http.py) УЖЕ есть; `OpenAiCompatibleClient` (adapters/openai_compatible.py, LLM-02) зависит
ТОЛЬКО от порта (K1/K6: НЕТ requests/httpx/urllib в домене), маппит `TransportTimeout→LLMTimeout` /
`TransportError→LLMError`; `ILLMAdvisor`+`adapter_for` (LLM-01) НЕ дублированы; fallback (LLMError/
LLMTimeout → kernel retrieval-only) УЖЕ доказан `test_llm_advisor_fallback.py`. ЕДИНСТВЕННЫЙ реальный gap
= `HttpTransport(IHttpTransport)` (stdlib urllib, в adapters/). `model_platform.py`/`embedding.py` бьют
urllib НАПРЯМУЮ (legacy MVP) — НЕ переиспользуются, НЕ дублируются.

- **Commit 1** — контракт: НОВЫЙ порт НЕ нужен (K5 one-port-per-boundary). `i_http.py` docstring уточнён
  (реальная реализация = adapters/http_transport.py).
- **Commit 2** — `adapters/http_transport.py`: `HttpTransport(IHttpTransport)` на stdlib `urllib.request`
  (НЕТ SDK — K6). Маппинг: socket.timeout/urllib-timeout → TransportTimeout; URLError/HTTPError/
  ConnectionError/OSError/ValueError → TransportError. Возвращает HttpResponse(status, body, headers).
- **Commit 3** — `composition/llm_client_factory.py`: `build_llm_client(base_url, model, api_key, timeout)`
  собирает HttpTransport + OpenAiCompatibleClient в готовый ILlm (Флаг C, НЕ в build_kernel);
  `detect_local_ollama(host)` best-effort probe. K3/K6: единственная точка сборки (composition.*).
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_llm_live_transport.py` — 5 тестов
  против in-process http.server (НЕТ живой модели): real HTTP advise → LLMAdvice; HttpTransport
  имплементирует порт; server DOWN/TIMEOUT → LLMError/LLMTimeout → kernel fallback == retrieval-only;
  K6 domain-без-SDK (AST).
- **Commit 5** — docs: ADR-079 + AKB + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K5/K6 (domain без SDK; HttpTransport в adapters/; build_llm_client в composition/); K8
(AST-проверка отсутствия SDK в домене); O1 (LLM — советник, fallback защищает, ядро LLM-free);
I-09 (детерминизм: in-process HTTP-сервер); Флаг C (standalone, НЕ в build_kernel). LLM-01/02 тесты НЕ
сломаны. Долги (ADR-079 non-scope): мульти-провайдер роутинг (OmniRoute); RL/fine-tuning; обязательная
живая модель в CI (тесты на in-process сервере, Ollama опционален).

**Verification:** `1221 passed, 0 failed` baseline + 5 LLM-LIVE тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-FED-TCP-01 (Federated execution over real TCP NW-01) — DONE

Валидация Флага 1 FED-EXEC-01 на практике: два узла поверх РЕАЛЬНОГО TCP-транспорта
`NetworkTransport` (adapters/network_transport.py, NW-01 localhost TCP) обмениваются
исполнением; trust обновляется из РЕАЛЬНОГО исхода, пришедшего по сокету. Завершает Network
Layer реальным транспортом.

K5-разведка (commit 0): `NetworkTransport(INetworkTransport)` — реальный TCP (wraps TcpEventBus);
`connect`/`ensure_connected`(barrier, НЕ sleep-luck)/`send_facts`/`on_facts`/`disconnect`. FSE-01
real-TCP паттерн: уникальные порты, `_wire`, teardown `disconnect()`, poll/retry. **ВАЖНО:** real
`NetworkTransport.on_facts` fan-out (append) -> фикс `321fc21` (единый delegate) корректен в ОБОИХ
случаях.

- **Commit 1** — контракт: НОВЫЙ порт НЕ нужен (K5). `build_federated_node` docstring уточнён
  (принимает real TCP; kernel НЕ импортирует adapters — wiring в tests/).
- **Commit 2** — reference impl: `tests/fed_tcp_helpers.py` (build_tcp_federated_node +
  make_tcp_federated_pair + ensure_pair_connected + teardown_tcp_pair) — в tests/ (K1/K6:
  kernel/adapters НЕ cross-import). **НАЙДЕН+ИСПРАВЛЕН реальный баг:** `dispatch_remote` ждал ответ
  синхронно -> на real TCP async false-negative 'no remote response'. Фикс: `_wait_for_outcome
  (request_id, timeout)` poll-with-timeout barrier (детерминизм по request_id) + `response_timeout`
  SOFT-tunable (O1). SyncTransport НЕ сломан (FED-ORCH/EXEC зелёные).
- **Commit 3** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_federated_tcp_execution.py` —
  6 тестов (real outcome по сокету + trust success+/failure-; gating low-trust excluded; clean
  teardown; determinism correlation request_id; negative server ignores non-addressed).
- **Commit 4** — docs: ADR-078 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (cross-layer wiring в tests/, kernel/adapters НЕ cross-import); O1 (trust SOFT;
server НЕ мутирует remote trust); I-09 (correlation request_id + ensure_connected barrier, НЕ
sleep-luck); Флаг C (standalone, НЕ в build_kernel); K5 (НЕ дублирован INetworkTransport/
IRemoteOrchestrator/build_federated_node); K8 (server фильтрует по node_id; low-trust excluded).
Network Layer ЗАВЕРШЁН реальным транспортом. Долги (ADR-078 non-scope): multi-hop routing/
discovery; консенсус; LLM-backed remote exec; распределённый TCP по разным хостам (только localhost).

**Verification:** `1215 passed, 0 failed` baseline + 6 FED-TCP тестов; gate `14 passed`; akb-lint PASSED.

---

## 2026-08-04 — ТЗ-SKILL-EVOLVE-01 (Closed-loop skill lifecycle) — DONE

Замыкает Флаги 1–2 SKILL-01. SKILL-01 дал процедурную память, но цикл навыка был открыт: Procedure
пишется один раз, confidence не эволюционирует, исходы dispatch не кормят skill обратно, recall
безусловен. ТЗ-SKILL-EVOLVE-01 замыкает петлю (опыт → навык → recall → исход → эволюция навыка),
по образцу trust-эволюции ORCH-01.

K5-разведка (commit 0): `IProceduralMemory` (Wave 9/ADR-012) УЖЕ есть со `store_skill`/
`recall_skill_by_capability` + `Procedure` frozen VO; `ITrustRegistry.record_outcome` (IDT-01) —
образец паттерна эволюции. РЕШЕНИЕ: расширить СУЩЕСТВУЮЩИЙ порт (НЕ новый, K5 one-port-per-boundary).

- **Commit 1** — contract: `IProceduralMemory` расширен (НЕ дублируется): `record_skill_outcome`
  (confidence эволюционирует success+/failure-, frozen→новая версия через store_skill,
  idempotent), `invalidate_skill` (удаление при confidence<floor), `recall_skill_by_capability
  (capability, min_confidence=0.0)` (обратно-совместимый gate, закрывает Флаг 2). Старые методы
  СОХРАНЕНЫ.
- **Commit 2** — impl: `InMemoryProceduralMemory` (replace для confidence, min_confidence gate,
  invalidate del) + `SkillEvolution` (on_skill_outcome → record_skill_outcome + invalidate при
  floor, по образцу ITrustRegistry.record_outcome) + `build_skill_evolution` (Флаг C).
- **Commit 3** — ORCH-01 integration: `ReferenceOrchestrator` опц. `skill_recall_min_confidence`;
  `route()` confidence-gated recall (Флаг 2 ЗАКРЫТ: низко-уверенный skill НЕ вытесняет агента/
  плагин); `dispatch()` для `kind='skill'` исполняет локально и кормит РЕАЛЬНЫЙ исход в
  `record_skill_outcome` (Флаг 1 ЗАКРЫТ: петля замкнута); repeated failure → invalidate →
  обычный routing. Standalone (Флаг C), НЕ в build_kernel.
- **Commit 4** — тесты K8 (ОТДЕЛЬНЫЙ коммит, Флаг 1b): `tests/test_skill_evolution.py` — 7 тестов
  (confidence evolves; missing→None; repeated failure→invalidate→normal routing; gated recall
  excludes low-confidence; orchestrator closed loop feeds outcome; determinism; O1 skills SOFT).
- **Commit 5** — docs: ADR-077 + AKB (adrs/issues) + CHANGELOG + PROJECT_STATUS.

Встроены: K1/K6 (contracts+stdlib; kernel/services→contracts only); O1 (skills SOFT; HARD/FSM
нетронуты); I-09 (determinism: gate + confidence-эволюция + инвалидация); Флаг C (standalone, НЕ в
build_kernel); K5 (НЕ дублирован IProceduralMemory/Procedure/ReferenceOrchestrator — расширен); K8
(low-confidence skill НЕ вспоминается; инвалидированный → обычный routing). Петля навыка замкнута.

Флаг 1 FED-EXEC-01 ТАКЖЕ ЗАКРЫТ в этом сеансе (отдельный коммит `321fc21`): `build_federated_node`
регистрирует ОДИН делегирующий handler (transport-agnostic fan-out), чтобы real-TCP NW-01 при
двойной подписке (client+server) НЕ перезаписывал слот. Доказано на single-slot transport.

Долги (ADR-077 non-scope): RL/авто-синтез процедур; LLM-backed skill synthesis; реальное
мульти-агент exec для навыков, маршрутизированных к агенту (Флаг 2 FED-EXEC-01: агентский «real
outcome» придёт только с полноценным мульти-агентным исполнением — задокументировано, не блок).

**Verification:** `1208 passed, 0 failed` baseline + 7 SKILL-EVOLVE тестов; gate `14 passed`; akb-lint PASSED.

---

## Baseline — v1.0 (ТЗ-002 D2)

V1/V2/V3 CLOSED, No High Architectural Debt. Metrics: `768 passed / 0 failed /
0 open violations`.

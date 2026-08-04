---
title: "KROFT_OS — Project Status"
version: "1.0"
date: "2026-08-02"
status: "active"
lang: ru
purpose: >
  Краткий статус архитектурного долга и готовности подсистем.
  Дополняет PROJECT_CONTEXT_MAP.md (паспорт) и ARCHITECTURE_MAP.md (handoff).
  Single source для "где мы находимся" по архитектурным нарушениям.
---

# KROFT_OS — Project Status

## 0. TL;DR

**Архитектурный долг уровня HIGH: ЗАКРЫТ.** Все основные слои (kernel, runtime, services, adapters, infrastructure, policies) зависят ТОЛЬКО от `contracts`. Последнее известное нарушение (V3: adapters→policies) устранено в Phase C / WP-01.

**Статус платформы:** архитектурно стабильна (Clean/Hexagonal соблюдён), готова к функциональному развитию (Supervisor & Recovery, Distributed Runtime, Marketplace).

**Git-режим:** единый репозиторий (Variant A). Remote `origin` = github.com/nikershovru-star/Kroft_os (K5 push разрешён пользователем 2026-08-02).

---

## 1. Архитектурный долг (Architectural Debt)

### История нарушений

| ID | Нарушение | Слой → Слой | Закон | Статус | Закрыто |
|----|-----------|-------------|-------|--------|---------|
| **V1** | kernel импортирует `infrastructure.DependencyContainer` | kernel → infrastructure | K1 | ✅ CLOSED | Phase B.4 (commit 1bd9140) |
| **V2** | kernel импортирует `infrastructure.SnapshotStore` | kernel → infrastructure | K1 | ✅ CLOSED | Phase B.3 (IStateRepository port) |
| **V3** | `adapters/router.py` импортирует `policies.budget_policy.estimate_cost` | adapters → policies | K6 | ✅ CLOSED | Phase C.1 (commit 3a899c6, ADR-030) |
| **V4** | `services/policy_engine.py` импортирует `contracts.model_registry.ModelRegistry` | services → contracts (порт) | K6 (minor) | ⚠ ACCEPTED | model_registry — это порт, не нарушение K6 в строгом смысле |
| **Deprecated** | `Kernel(container=...)` legacy-параметр | kernel | K1/K3 (щель) | ✅ WP-07 (container-path оставлен как K3-compliant Composition Root factory, статус deprecated снят) | TZ-003 WP-07 |

### Текущий статус долга

- **HIGH architectural debt:** **0** (нет).
- **LOW/accepted debt:** 1 (V4, не критично, model_registry — порт).
- **Deprecated API:** **0** (legacy `Kernel(container=...)` de-deprecated in WP-07; container path is now the canonical Composition Root factory, K3-compliant).
- **Open violations:** **0** (arch-gate 14 passed).

> **No High Architectural Debt** — все критические нарушения закрыты.

---

## 2. Готовность подсистем

| Подсистема | Статус | Примечание |
|------------|--------|-----------|
| Kernel (lifecycle FSM) | ✅ done | UNINITIALIZED→INITIALIZED→RUNNING→STOPPED |
| Runtime (context, registry) | ✅ done | CapabilityRegistry, RuntimeContext |
| Contracts (27 портов) | ✅ done | чистые Protocol-интерфейсы |
| Services (Agent/Knowledge/...) | ✅ done (32) | зависят только от contracts |
| Adapters | ✅ done | НЕТ импорта policies (V3 closed) |
| Infrastructure | ✅ done | DependencyContainer, SnapshotStore, ... |
| Policies | ✅ done | PolicyRegistry + PolicyEngine (Phase C.2) |
| Composition Root | ✅ done | `composition/` (7 модулей, build_system) |
| Architecture Gate | ✅ done (WP-02) | 8 positive + 6 negative |
| CLI | ✅ done | main.py + commands + repl |
| Plugins | ⏸ empty | зарезервировано |

---

## 3. Метрики (реальный прогон 2026-08-02)

- **Tests:** `1053 passed, 19 skipped, 1 xpassed, 0 failed` (реальный прогон 2026-08-03; +ТЗ-CAUSAL-01: +9 тестов Lamport; +ТЗ-RE-01: +8 тестов Reasoning; +ТЗ-WM-01: +10 тестов World Model; +ТЗ-PL-01: +9 тестов Planner +3 value-aware WM; +ТЗ-ME-01: +10 тестов Memory Evolution; +ТЗ-RF-01: +11 тестов Reflection; WP14-RACE xfail'd)
- **Arch-gate:** `14 passed` (8 positive + 6 negative)
- **ADR:** 60 (ADR-001..060; ADR-055 accepted + Lamport amendment; ADR-056 accepted — Reasoning Engine; ADR-057 accepted — World Model; ADR-058 accepted — Autonomous Planner; ADR-059 accepted — Memory Evolution; ADR-060 accepted — Reflection Engine; ADR-007 — двойной файл, логически один)
- **Laws:** 8 (K1–K8)
- **Forbidden patterns:** 6 (F1–F6)
- **Open violations:** **0**
- **AKB YAML:** 16 файлов (laws, adrs, rfcs, history, issues, patterns/*, standards/*, glossary, evidence_levels, org_memory, tech_catalog, pattern_library, import_matrix, gate_coverage)

---

## 4. Следующие этапы (roadmap)

| Волна | WP (TZ-001/TZ-002) | Статус |
|-------|---------------------|--------|
| Wave 0 | WP-01 (V3), WP-02 (gate), WP-03 (docs) | ✅ WP-01, ✅ WP-02, ✅ WP-03 |
| Wave 1 | WP-04 (repo), WP-05 (CI), WP-06 (sync), WP-07 (deprecated), WP-08 (ADR lifecycle) | ✅ WP-04, ✅ WP-05, ✅ WP-06, ✅ WP-07, ✅ WP-08 |
| Wave 2 | WP-09 (KG v2 ✅ TZ-KNOW-001), WP-10 (Supervisor/Recovery ⏸ design RFC-010/ADR-038), WP-11 (self-analysis ✅ TZ-AGENT-001) | WP-10 design DONE, code ждёт K5 |
| TZ-EXECUTION-001 | WP-01 (Sandbox port+adapter), WP-02 (ToolRegistry+DesktopAdapter integration), WP-03 (tests +12) | ✅ DONE |
| Wave 3 | WP-12/13/14 DONE | ✅ COMPLETE |
| TZ-015 | Distributed Runtime Implementation (9 comps) | 🔧 CODE STARTED — ports+services scaffolded (gate C causal), in-process federation DONE; real network (TcpEventBus/partition) deferred (WP14-RACE infra) |
| TZ-016 | Autonomous Planner (8 comps) | 🔬 design RFC-016/ADR-045 DONE, code deferred |
| TZ-017 | Long-Term Memory Evolution (7 comps) | 🔬 design RFC-017/ADR-046 DONE, code deferred |
| TZ-018 | World Model (7 comps) | 🔬 design RFC-018/ADR-047 DONE, code deferred |
| TZ-019 | Agent Society (8 comps) | 🔬 design RFC-019/ADR-048 DONE, code deferred |
| TZ-020 | Self Improvement (8 comps) | 🔬 design RFC-020/ADR-049 DONE, code deferred |
| TZ-021 | AI Marketplace (8 comps) | 🔬 design RFC-021/ADR-050 DONE, code deferred |
| TZ-022 | Federated Knowledge Network (8 comps) | 🔬 design RFC-022/ADR-051 DONE, code deferred |
| TZ-023 | Cognitive Operating System (8 comps) | 🔬 design RFC-023/ADR-052 DONE, code deferred |
| **v2.0 Roadmap** | TZ-015..023 unified (ADR-053) | 🔬 ALL DESIGNS DONE (9×8/8 PASS, gate 14, akb-lint PASSED) |
| **ADR-054** | Cognitive Kernel Constitution (CONSTITUTION, 20 invariants I-01..I-20) | ✅ ACCEPTED — primary invariant, all TZ subordinate |
| **ADR-055** | ConfidenceScore Contract (unified cross-entity) | ✅ ACCEPTED (derived from I-12; aggregation rule added) |
| Compatibility Matrix | ADR-044..053 vs ADR-054 | ✅ DONE — 9/10 compatible, 4 critical clarifications |

### 4.1 Нумерационный reconciliation (Флаг 4, 2026-08-02)

**Source of Truth выбран явно: KROFT_OS ADR-053 + PROJECT_STATUS (v2.0 roadmap).** Любая
внешняя/устаревшая карта (напр. v1-таблица из стартового промпта, где `TZ-015 = Reasoning
Engine (W2)`) — НЕ SoT, должна считаться archived и заменена на ADR-053.

**Mapping (внутренний ADR/RFC-трекер ↔ карта W-волн):**
| Внутренний номер | Что реализует | На карте W-волн (ADR-053) |
|------------------|---------------|---------------------------|
| TZ-015 / ADR-044 / RFC-015 | Distributed Runtime (CRDT/Elector/Bus + Shared Context + causal-merge) | **W3**: Shared Context (TZ-023) + Federation Layer (TZ-024) + Network Layer (TZ-028) |
| Reasoning Engine (компонент) | WorldModel-backed reasoning в фазе Deliberate | **W2**: Deliberate = Reasoning (WorldModel ADR-047 / TZ-018) → Planning (TZ-016) → Decision (I-03) |

**Открытый пробел W2 (честно):** dedicated **Reasoning Engine как отдельный КОМПОНЕНТ**
(Planner/Solver/Inference Engine) НЕ выделен — в FSM покрыт фазой `Deliberate`
(Reasoning→Planning→Decision в общем виде), но параметризуемого движка (Intent/Attention/
WorldState-управляемого) как самостоятельного модуля нет. → W2 статус (~60%) СКОРРЕКТИРОВАН
вниз: фаза есть, компонента-движка нет. Это НЕ блокирует code-фазу, но должно быть в трекере
как явный gap, а не «планируется» без уточнения.


**Integration slice (path 3, 2026-08-02):** ядро × федерация связаны in-process (2 kernel + 2 SharedContextService, in-memory канал). Доказано: federated-факт (CausalMark A,lamport=10) достигает узла B и МЕНЯЕТ Decision@B через WorldState — KROFT_OS когнитивная ОС, не distributed store с LLM. CausalMark.__lt__ исправлен на lamport-primary (был node-name-primary — неверный merge); далее ТЗ-CAUSAL-01 повысил CausalMark до Lamport clock с receive-обновлением (закрыт дефект «talkative node wins»).

**ТЗ-CAUSAL-01 (2026-08-02, DONE — code):** CausalMark → Lamport logical clock. `merge_remote` и `InMemoryWorldState.update` делают `receive` при получении удалённого факта (clock = max+1); локальные события (tick/emit) делают `tick()`; stored marks сохраняют remote origin для конвергентности; idempotent replay. Commits 65a3ee2 (contract) + 3724248 (tests). Ad-hoc 13/13 PASS; 19 causal-тестов PASS; full 1002/0; gate 14/14; issues `CAUSAL-SEQ-LIMIT` CLOSED. ADR-055 amended (§6 Lamport contract, status accepted).

**Следствие для статус-дашборда:** W3 (Shared Context + causal-merge) РЕАЛЬНО частично сделан
(in-process) — карта/PROJECT_STATUS это отражают (TZ-015 = CODE STARTED, не deferred).
Реальная сеть (TcpEventBus/partition/reconnect) и dedicated Reasoning Engine остаются OPEN.

### Функциональные этапы (после стабилизации)
- Phase D — Configuration & Secrets
- Phase E — MCP Gateway
- Phase F — Supervisor & Recovery
- Phase G — Distributed Runtime

---


## 5. Stage Audit (2026-08-02)

- **Stage 22** — НЕ пропущен. Упоминается в CHANGELOG («без --auth сервер ведёт себя как Stage 22»); это был HTTP server / auth stage, влился в последующие.
- **Stage 47 / 48** — ДЕЙСТВИТЕЛЬНО ОТСУТСТВУЮТ в CHANGELOG (Stage 46 v5.9.0 → Stage 49 v5.12.0; версии v5.10.0/v5.11.0 пропущены) и в README. **Решение: intentionally skipped (не технический долг).**
  - *Audit evidence (2026-08-02):* Graph visualization — Stage 23 дал export DOT/JSON/GEXF, НЕТ interactive renderer; real-time collaboration — НЕ реализовано; plugin marketplace — Stage 25/40 дали loader, НЕТ marketplace/dep-management; LLM-based agent — НЕ реализовано (Hermes v2 = Wave 3).
  - *Гипотезы содержимого:* Stage 47 ≈ Graph Visualization / Interactive Renderer (gap после analytics Stage 46); Stage 48 ≈ Real-time Collaboration / Multi-user ИЛИ Plugin Marketplace.
  - *Почему skipped:* не блокируют core functionality; покрываются roadmap Wave 3 (ADR-025 multimodal, Distributed Runtime Phase G); могут быть отдельными ТЗ позже.
  - *Статус:* documented as skipped placeholder (graph-viz + real-time-collab / plugin-marketplace).
- **ADR-025** (PHASE 6 Multimodal) — status `proposed`, K5 decision **defer to Wave 3** (no IMultimodalParser port; heavy deps need optional adapters per K8; not blocking).

> **v1.0 changelog:** создан в рамках TZ-002 (D2). Зафиксирован V1/V2/V3 CLOSED, No High Architectural Debt, метрики 768 passed / 0 failed / 0 open violations.

> **ТЗ-RE-01 (2026-08-02, DONE — code):** Reasoning Engine как parametric Deliberate-компонент (IReasoningEngine + ReasoningStep + ReferenceReasoningEngine, LLM-free), world-aware Decision (IDecisionEngine.select получает WorldState+Intent, bind()-хак удалён), единый NodeLamportClock на узел (инжект в kernel+world+federation; node_origin=node_id), wire-ключ "seq"→"lamport". 6 атомарных коммитов (47d96bd, 4ac6ce5, 0f86b9f, 1a66633, cd525df, docs/ADR-056). Full suite 1010 passed, gate 14/14, akb-lint PASSED. ADR-056 accepted; issues RE-01-GAP-CLOSED.

> **ТЗ-WM-01 (2026-08-02, DONE — code):** World Model как предиктивный советник поверх WorldState (ADR-047). Контракт IWorldModel (predict/simulate/evaluate) + frozen PredictedState; ReferenceWorldModel (LLM-free, confidence падает с horizon, no-fact=low); интеграция в Reasoning (confidence = predicted utility). flag A: default clock из world.node_id (без "kernel"), sentinel-origin normalize в publish. 6 атомарных коммитов (b0523d6, f26eb7e, 07d7730, 66043a4, f33c5fc, docs/ADR-057). Full suite 1020 passed, gate 14/14, akb-lint PASSED. ADR-057 accepted; issues WM-01-GAP-CLOSED.

> **ТЗ-PL-01 (2026-08-03, DONE — code):** Autonomous Planner как выделенный компонент фазы Deliberate (ADR-045/054). Контракт IPlanner.plan(goal, steps, world, budget, intent) -> List[Plan] ранжированный по predicted value-aware utility; ReferencePlanner (LLM-free) прогоняет каждый candidate через WorldModel.simulate (lookahead) и evaluate(values) — hard violation -> utility 0 (veto), soft utility re-ranks; Planner РАНЖИРУЕТ, Decision ВЫБИРАЕТ (I-03/I-09). Флаг 2 закрыт: evaluate стал value-aware (values живой параметр). 6 атомарных коммитов (21b1da1, a0373f7, 9c460e8, 539a015, ec984f3, docs/ADR-058). Full suite 1032 passed, gate 14/14, akb-lint PASSED. ADR-058 accepted + ADR-057 amended (value-aware evaluate, transition=stub честно); issues PL-01-GAP-CLOSED.

> **ТЗ-ME-01 (2026-08-03, DONE — code):** Long-Term Memory Evolution (механизм Self-Evolving, ADR-046). Контракт IMemoryEvolution (consolidate/forget/supersede) + SemanticFact + PolicyLifecycle; ILayeredMemory расширен (semantic layer + lifecycle). ReferenceMemoryEvolution (LLM-free): повторяющийся high-conf опыт -> SemanticFact (агрегированная ConfidenceScore + CausalMark), forgetting low-conf, supersede. Интеграция в Learn-фазу kernel с SELF-EVOLVING GUARD (O1): hard_violations ДО commit, HARD-слой неизменен. 5 атомарных коммитов (dce8d96, fe13fbd, d9adde6, bb7b20b, docs/ADR-059). Full suite 1042 passed, gate 14/14, akb-lint PASSED. ADR-059 accepted; issues ME-01-GAP-CLOSED / PL-01-GAP-CLOSED.

> **ТЗ-RF-01 (2026-08-03, DONE — code):** Reflection Engine (замыкает когнитивный цикл, ADR-060 / TZ-COG-005). Контракт IReflectionEngine.reflect -> ReflectionReport (PROPOSALS, не пишет память) + ExecutionOutcome (ФЛАГ 1 feedback proxy) + ProvenanceType.REFLECTION. ReferenceReflectionEngine (LLM-free): OUTCOME-BASED — успешный опыт -> consolidation, неуспешный -> deprecation (не по intent-тексту). Интеграция: kernel записывает ExecutionOutcome + Reflection-фаза ДО Learn (analytic -> executive), с O1 guard. ФЛАГ 2 закрыт: soft_policies из consolidate коммитятся в normative с O1 guard. 6 атомарных коммитов (29e1448, a0806f0, 6454bf7, 909618f, 02a5e26, docs/ADR-060). Full suite 1053 passed, gate 14/14, akb-lint PASSED. ADR-060 accepted; issue RF-01-GAP-CLOSED.

> **ТЗ-RT-01 (2026-08-03, DONE — code):** Runtime / System Reflection (adaptive runtime contour, ADR-062). Раунд 2: вторая петля наблюдает ОПЕРАЦИОННЫЕ метрики (доставка фактов, рост памяти, connect-латентность от NW-01) и адаптивно тюнингует SOFT runtime-параметры под O1 guard. Контракты IRuntimeMetrics/IRuntimeReflection/ITuningApplier + RuntimeMetric/TuningProposal (frozen VOs; конструктор запрещает layer=HARD). ReferenceRuntimeReflection (детерминированные правила R1-R3), ReferenceTuningApplier (O1: отклоняет НЕ-SOFT/unknown), RuntimeSupervisor.step() collect→reflect→apply. Тюнингуемые цели: ReferenceMemoryEvolution (min_repetitions/confidence_threshold), NetworkTransport (ensure_connected_timeout), SimpleResourceManager (budgets.tokens). Разделение с RF-01: runtime reflection НЕ пишет semantic/policy контент. 6 атомарных коммитов (19fbd9f, 3badd8a, b71aed2, e587dc3, 5d0a7c9, docs/ADR-062). Full suite 1063+ passed, gate 14/14, akb-lint PASSED, ad-hoc 17/17. ADR-062 accepted; issue RT-01 closed.


> **ТЗ-EX-01 (2026-08-03, DONE — code):** Execution Layer + Real Outcome-Feedback (замена outcome-proxy, ADR-063). Система ИСПОЛНЯЕТ выбранное решение в среде и снимает НАСТОЯЩИЙ результат. Контракты IExecutor/IExecutionEnvironment/IActionAdapter + ExecutionResult (сырой ответ среды). ReferenceExecutor/ReferenceExecutionEnvironment (deterministic rule-map: choose_blue->success/0.9, choose_red->fail/0.1, unknown->fail/0.0). Интеграция: kernel Execute-фаза при executor строит РЕАЛЬНЫЙ ExecutionOutcome из ExecutionResult; без executor — proxy fallback (backward compat). Разделение Result (сырой) / Outcome (для Reflection) соблюдено. Закрывает RF-01 ФЛАГ 2 (outcome-proxy): repeated real failures -> RF-01 deprecation (эволюция не vacuous). 5 атомарных коммитов (c45ceb1, 824011e, 6e849d0, 403cb11, docs/ADR-063). Full suite 1077+ passed, gate 14/14, akb-lint PASSED. ADR-063 accepted; issue EX-01 closed.


> **ТЗ-SE-01 (2026-08-04, DONE — code):** Self-Evolution Behavioral Closure (замыкание петли, ФЛАГ 3 EX-01, ADR-064). Deliberation читает эволюционировавший SOFT-слой через новый порт `ISoftPolicySource`: `PolicyAwareValueSystem` (prefer/avoid в score) + `KnowledgeAwareReasoning` (recall semantic facts как candidates). `build_kernel` wire-ит оба поверх `MemorySoftPolicySource(memory)`; Learn-фаза генерит SOFT `avoid:<pattern>` policy из repeated failure (O1 layer=='soft'). Капстоун: repeated SUCCESS → consolidation → следующий tick ВЫБИРАЕТ learned; repeated FAILURE → deprecation → ИЗБЕГАЕТ. NEGATIVE: без wiring эволюция НЕ меняет решение. 5 атомарных коммитов (2bb0331, 386a508, 9bd91f4, 5f53337, docs/ADR-064). Full suite 1086+ passed, gate 14/14, akb-lint PASSED. ADR-064 accepted; issue SE-01 closed.


> **ТЗ-LLM-01 (2026-08-04, DONE — code):** LLM-as-advisor plug-in + graceful fallback (валидация contract-boundary I-10, kernel purity, ADR-065). Advisor втыкается через порт `ILLMAdvisor` (мостит существующий Model Platform `ILlm` через `adapter_for`, порт НЕ дублирован). `LLMAdvisorReasoning`/`LLMAdvisorPlanner` ре-ранжируют кандидатов через advice; при `LLMError`/`LLMTimeout` -> graceful fallback на чистый reference (== результат без LLM). `build_kernel(llm_client=None)` неизменен. Капстоун: `build_kernel()` == `build_kernel(MockLLMClient(fail=True))` по `selected_plan.steps` — kernel LLM-free ПО СУТИ, не по декларации. 5 атомарных коммитов (7d32578, 2bd95c0, b98b63f, 7659be7, docs/ADR-065). Full suite GREEN, gate 14/14, akb-lint PASSED. ADR-065 accepted; issue LLM-01 closed.

**ТЗ-FSE-01 (2026-08-04, DONE — code):** Federated Self-Evolution — коллективное обучение. Выученный SOFT-слой (semantic facts + soft policies) федерируется по сети и меняет поведение каждого узла (кульминация «локально и в сети», ТЗ-NW-01 + ТЗ-SE-01). `INetworkTransport` расширен вторым каналом (`send_soft_layer`/`on_soft_layer`, топик `cog.soft`); `FederationSoftMemorySync` (services/distributed_runtime.py) — sender гейтит по confidence + НЕ шлёт HARD (O1), receiver мержит с double confidence-гейтом + dedup + provenance. `attach_soft_memory_sync` + publish после Learn-фазы. ADR-066 ЯВНО фиксирует что федерировать (semantic=ДА; soft=ДА с гейтом; HARD=НИКОГДА). Капстоун: A учит avoid:X (repeated FAILURE) -> B (без опыта) ИЗБЕГАЕТ X по реальному NetworkTransport. 5 атомарных коммитов (cbb7f5f, 411be1c, 97014a4, 51411dd, docs/ADR-066). Full suite GREEN, gate 14/14, akb-lint PASSED, ad-hoc 10/10.

**ТЗ-OBS-01 (2026-08-04, DONE — code):** Observability — живые метрики -> автономная runtime-адаптация (закрывает долг RT-01). `ILiveMetricsCollector` (contracts/i_observability.py, отдельная граница от системного `i_metrics.IMetricsCollector`) + `LiveMetricsCollector`/`LiveRuntimeMetrics` (kernel/observability.py): счётчики как RATIOS (Флаг 1) + скользящее окно (Флаг 2: consolidation_confidence из окна исходов, не «нет значения»). `build_kernel(live_metrics=)` wire-ит `RuntimeSupervisor`, который АВТОНОМНО тюнит SOFT-параметры каждые N=3 tick (Флаг 3, anti-thrash); hooks no-op без collector. Capstone: degraded-исходы -> живая consolidation_confidence < 0.6 -> supervisor поднимает confidence_threshold (R3) -> measurably меньше консолидаций, БЕЗ injectable snapshot. `ReferenceRuntimeMetrics` injectable сохранён (RT-01 тесты целы). 5 атомарных коммитов (99a552c, 475782c, d770828, 9e7dc62, docs/ADR-067). Full suite GREEN, gate 14/14, akb-lint PASSED.

**ТЗ-LLM-02 (2026-08-04, DONE — code):** Model Platform — concrete OpenAI-compatible `ILlm` adapter + transport port (завершение I-10 «LLM = сменный инструмент»). `IHttpTransport` (contracts/i_http.py, отдельная граница) + `OpenAiCompatibleClient(ILlm)` (adapters/openai_compatible.py, поверх IHttpTransport, НЕТ provider SDK — K6). `adapter_for(ILlm) -> ILLMAdvisor` уже готов (LLM-01); уточнён: `LLMTimeout`/`LLMError` пробрасываются как есть. Hook `llm.fallback_rate` в `LLMAdvisorReasoning`/`LLMAdvisorPlanner` (Флаг 2 OBS-01) через `build_kernel(live_metrics=)`. Contract-тесты с fake transport (БЕЗ живой модели/сети) доказывают bridge + graceful fallback == no-LLM result. BUG FIX: `LiveMetricsCollector.record_failure` не инкрементировал `_fail` (fallback_rate был 0) — исправлено; `adapter_for` перепаковывал `LLMTimeout` в `LLMError` — пробрасываем как есть. 5 атомарных коммитов (9181625, a8a3f55, a5bf359, 1f36f89, docs/ADR-068). Full suite GREEN, gate 14/14, akb-lint PASSED.

**ТЗ-SEARCH-01 (2026-08-04, DONE — code):** Knowledge Search / Retrieval — первая платформенная волна применимости (извлечение накопленных знаний по запросу, LLM-free, I-09). `ISearchService` (contracts/i_search.py) + `SearchHit` (frozen VO, causal: Optional[CausalMark]) + `SearchScope`. `ReferenceSearchService` (kernel/search.py) — STANDALONE read-only сервис поверх СУЩЕСТВУЮЩИХ источников (ILayeredMemory.get_semantic/episodes/normative + IGraphEngine.nodes()), БЕЗ дублирования content_index/knowledge graph (K5-разведка: порт не существовал → создан; индексы переиспользованы). Четыре reviewer-флага встроены: Флаг A (pure-scan, НЕ пишем в shared index), Флаг B (тотальный порядок ranking confidence desc, relevance desc, id asc — детерминизм I-09), Флаг C (standalone, НЕ в build_kernel, не усугубляет god-factory), Флаг D (causal реальный тип; graph-ноды → дефолт 0.5 + causal=None). 5 атомарных коммитов (81abd46, d798c50, a016e60, docs/ADR-069). Full suite GREEN, gate 14/14, akb-lint PASSED.

**ТЗ-RESEARCH-01 (2026-08-04, DONE — code):** Research Service — вторая платформенная волна применимости (исследовательский цикл поверх SEARCH-01: извлечение -> синтез -> опц. SOFT-запись), LLM-free по умолчанию (I-09). `IResearchService` (contracts/i_research.py) + `ResearchReport`/`ResearchGoal` (frozen VO, реальные типы). `ReferenceResearchService` (kernel/research.py) — STANDALONE read-first сервис поверх СУЩЕСТВУЮЩЕГО ISearchService (НЕ дублирует порт поиска; K5-разведка: IResearchService не существовал → создан; ISearchService/ILayeredMemory/ILLMAdvisor переиспользованы). Встроены: Флаг C (standalone build_research_service, НЕ в build_kernel, не усугубляет god-factory), I-09 (детерминизм: summary=top-finding, agg conf=mean, повторный goal идентичен), LLM-01/02 (опц. ILLMAdvisor, fallback == retrieval-only при LLMError/LLMTimeout), O1 (write-back ТОЛЬКО SOFT через commit_semantic, opt-in write_back). Тесты отдельным коммитом (Флаг 1b/4): 13 K8 тестов. 5 атомарных коммитов (427c493, 5bbaff9, b7fd4e7, docs/ADR-070). Full suite GREEN, gate 14/14, akb-lint PASSED.

**ТЗ-PLUGIN-01 (2026-08-04, DONE — code):** Plugin Registry — третья платформенная волна применимости (детерминированный реестр внешних capabilities за портом, LLM-free I-09, standalone Флаг C). `ICapabilityPlugin`+`IPluginRegistry` (contracts/plugin.py) + `ReferencePluginRegistry` (kernel/plugin.py) + `SearchPlugin`/`ResearchPlugin` — ОБЁРТКИ над существующими `ISearchService`/`IResearchService` (К5: переиспользование, НЕ дублирование). К5-разведка: `IPlugin` (CLI/export, Stage 25) уже существовал → введён отдельный invoke-capable под-порт `ICapabilityPlugin` (one-port-per-boundary), существующий test_plugins.py НЕ сломан (10/10). Встроены: Флаг C (standalone build_plugin_registry, НЕ в build_kernel, не усугубляет god-factory), I-09 (list сортирован по id, invoke детерминирован), O1 (reference-плагины read-only w.r.t. HARD/FSM), K8 (unknown-id invoke→PluginResult(ok=False), duplicate→PluginInvocationError, unregister unknown→no-op). Тесты отдельным коммитом (Флаг 1b): 14 K8 тестов. 5 атомарных коммитов (6bd2fb1, fe2cf43, 0958dae, docs/ADR-071). Full suite GREEN, gate 14/14, akb-lint PASSED.

**God-factory refactor (ТЗ-OBS-01 Флаг 1, 2026-08-04, DONE — code):** Долг закрыт. `build_kernel` перестал быть god-factory: композиция вынесена в `KernelBuilder` (`kernel/kernel_builder.py`), параметры — в `KernelConfig` (`kernel/kernel_config.py`). Обратная совместимость сохранена (48 вызовов не сломаны) + опц. `config`. Behavioural-equivalence доказана (1157/0 ДО и ПОСЛЕ). Latent-баг исправлен (reason/planner всегда LLMAdvisor-варианты). Урок Флага 3: re-exports — стабильная поверхность, не чистить по внутреннему неиспользованию. 4 атомарных коммита (a3c61c3, <commit2>, 7a8bfd7, docs). Full suite 1157/0, gate 14/14, akb-lint PASSED.

**ТЗ-IDT-01 (2026-08-04, DONE — code):** Identity & Trust layer — четвёртая платформенная волна (identity + trust + trust-gейтинг федерации, закрывает дыру FSE-01). K5-разведка (commit 0): порт НЕ существовал; `AgentState` (ТЗ-AGENT-001, lifecycle-FSM) УЖЕ есть — ДРУГАЯ граница, НЕ дублируем; `Provenance`/`CausalMark` переиспользуются; `FederationSoftMemorySync` (FSE-01) расширен опционально. `contracts/i_identity.py` (`AgentIdentity`/`IIdentityRegistry`/`TrustMeta`/`ITrustRegistry`/`IActionLog`) + `kernel/identity.py` (`ReferenceIdentityRegistry`/`ReferenceTrustRegistry`/`ReferenceActionLog`, in-memory deterministic LLM-free) + FSE-01 integration (`SoftLayerItem.author_id`; receiver отклоняет low-trust sender; БЕЗ registry — default permissive, FSE-01 тесты целы). Встроены: K1/K6 (contracts+stdlib; services→contracts only), O1 (реестры НЕ мутируют HARD/FSM), I-09 (determinism: MAX-агрегация trust), Флаг C (standalone, НЕ в build_kernel), K8 (unknown id→None, low-trust reject, FSE-01 без registry неизменен). Тесты отдельным коммитом (Флаг 1b/4): 10 K8 тестов. 5 атомарных коммитов (b674efb, 32dffb6, e7ec0a5, 03b92cd, docs/ADR-072). Full suite GREEN, gate 14/14, akb-lint PASSED. Долги (ADR-072 non-scope): real signing/per-agent trust/агент-обмен — future.

**ТЗ-ORCH-01 (2026-08-04, DONE — code):** Trust-aware orchestration — пятая платформенная волна (поведение поверх Identity/Trust/Plugins, «Section 9» визии). K5-разведка (commit 0): trust-aware ROUTING НЕ существовал; переиспользованы IIdentityRegistry/ITrustRegistry/IActionLog (IDT-01) + IPluginRegistry (PLUGIN-01); IAgentPlatform (AGENT-001) НЕ дублирован (мульти-агент exec через сеть — future NW-01). `contracts/i_orchestrator.py` (`OrchestrationGoal`/`RoutingDecision`/`TaskOutcome`/`IOrchestrator`) + `kernel/orchestrator.py` (`ReferenceOrchestrator` + `build_orchestrator` фабрика, standalone Флаг C) + IDT-01 follow-up: `ITrustRegistry.record_outcome`/`current_trust`/`seed` (читает LATEST running-trust, НЕ MAX — закрывает Флаг 1 IDT-01 trust-then-attack). ReferenceOrchestrator: score=spec_match*trust, exclusion permission/low-trust, max+tie-break id; dispatch логирует в IActionLog + обновляет trust из исхода (success+/failure-) — trust ЭВОЛЮЦИОНИРУЕТ, петля замкнута. Встроены: K1/K6 (contracts+stdlib; kernel→contracts only), O1 (HARD/FSM не тронуты; trust-обновления SOFT), I-09 (determinism: scoring+tie-break), Флаг C (standalone, НЕ в build_kernel), K8 (no eligible→None, low-trust/permission exclusion, determinism). Тесты отдельным коммитом (Флаг 1b): 8 K8 тестов (agent trust 0.9→1.0, plugin 0.5→0.6, failure lowers). 5 атомарных коммитов (6e06dcb IDT-follow, 152fe47, 487bd4b, f6a4324, docs/ADR-073). Full suite GREEN, gate 14/14, akb-lint PASSED. Долги (ADR-073 non-scope): реальное мульти-агент exec через сеть / RL-планирование — future.

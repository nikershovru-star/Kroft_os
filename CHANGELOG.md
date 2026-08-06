# CHANGELOG

All notable changes to KROFT_OS are documented here, grouped by ТЗ (Technical Specification).
Format: each ТЗ is one section; commits are atomic (see `git log`).

## ТЗ-LIVE-01 — runnable launch + persistence + optional local LLM (ADR-087, 2026-08-05) — DONE
- **K5:** переиспользованы `InMemoryLayeredMemory`, `build_kernel`/`KernelConfig`/`KernelBuilder`,
  `ReferenceExecutor`, `ReferenceTrustRegistry`, `InMemoryProceduralMemory`, `ProcedureConsolidator`,
  `detect_local_ollama`/`build_llm_client`. Создан ровно один новый модуль `kernel/persistence.py`.
- **persistence** (`kernel/persistence.py`): `JsonMemoryStore` (stdlib json, sort_keys, детерминированный
  roundtrip) + `KernelState` (episodes/semantic/normative + skills + trust). Явная VO<->dict сериализация
  (ConfidenceScore/Provenance/CausalMark/Enums), НЕ `dataclasses.asdict`.
- **inject store** (`KernelConfig.memory` + `KernelBuilder`): ядро строится поверх загруженного стора и
  RESUME самоэволюцию между перезапусками. Backward-compat (None -> fresh). `procedural` НЕ добавлен в
  kernel (K3/K6: kernel не импортирует services; навыки живут в orchestrator/run_evolution).
- **run_evolution.py** (Флаг C, standalone): build_kernel(+ опц. Ollama advisor, skip-if-unavailable) ->
  load/replay состояния -> N тиков демо-потока (deterministic; choose_red fail -> ядро учит soft
  avoid-политику) -> печать эволюции (policies/skills/trust) -> save.
- **K8 tests** (`tests/test_live_persistence.py`): roundtrip идентичен; эволюция через 2 перезапуска
  (6->10 эпизодов, soft-политика переживает restart); O1 HARD intact + immutable; детерминизм без LLM;
  запуск без Ollama.
- **O1/I-09:** load не мутирует HARD; без LLM запуск детерминирован (эволюция идентична). Флаг 1b: тесты
  отдельным коммитом.

## ТЗ-NET-ROUTE-01 — node discovery + multi-hop routing (ADR-086, 2026-08-05) — DONE
- **K5:** `INodeDiscovery`+`GossipNodeDiscovery`, `IClusterRegistry`+`CrdtClusterRegistry`, `INetworkTransport` УЖЕ есть (TZ-015/ADR-044) → reuse. Новый порт `IRoutingTable` (next_hop) создан (не существовал).
- **contract** (`contracts/i_distributed_runtime.py`, `contracts/i_federated_orchestrator.py`): `IRoutingTable` + `RoutingHeader(target,ttl)`; `RemoteGoalRequest`/`RemoteOutcomeResponse` + `route`; encode/decode несут route.
- **impl** (`services/distributed_runtime.py`, `kernel/federated_orchestrator.py`, `kernel/federated_executor.py`): `ReferenceRoutingTable` (distance-vector-lite, deterministic, НЕ ре-сигнует forwarded envelope); `_maybe_forward` (форвард не-локального envelope с сохранённой подписью, per-node seen-set + progress-only next_hop = loop-safety); сервер ставит `route.target=req.author_id` (response маршрут НАЗАД).
- **integration**: `routing_table`/`direct_peers` в `build_remote_orchestrator` + `build_federated_node`.
- **tests** (`tests/test_net_routing.py`, 5 K8): discovery membership; A→C via B multi-hop; trust-gating; tampered/replayed/unsigned rejected; next_hop deterministic.
- **docs**: ADR-086 + AKB (85→86) + CHANGELOG + PROJECT_STATUS.
- **Constraints**: K1/K5/K6/K8/O1/I-09; Флаг C/1b. verify-before-trust + replay-guard на каждом hop сохранены.

## ТЗ-CAPSTONE-01 — end-to-end self-evolving federated cognitive OS (ADR-085, 2026-08-05) — DONE

The integration culmination of the vision: two authenticated, self-evolving federated nodes where node A's
self-evolution (experience → reflection → soft policy) is shipped to node B over a verified + replay-guarded
channel, and B changes its behavior from A's knowledge. No new ports/layers — reuses the entire existing
substrate (K5).

- **`composition/capstone.py`** (Флаг C, standalone, NOT in build_kernel):
  - `build_capstone_mesh(transport_a, transport_b, *, shared_key, use_real_llm, ...)` → `CapstoneMesh`:
    two `build_kernel` nodes, each wired to a `FederationSoftMemorySync` (FSE-01) over the supplied
    transports, sharing ONE `HmacSigner` (shared key) + per-node `ReplayGuard`. Real LLM is best-effort
    optional (detected via `detect_local_ollama`, else LLM-free → deterministic).
  - `run_capstone_self_evolution(mesh, ...)`: drives node A's self-evolution loop (forced failures on
    `choose_red` → `avoid:decided:choose_red` soft policy), ships the SOFT layer to B (signed + per-item
    monotonic seq), B verifies before merge and switches its next decision to the safe alternative. Returns
    a result dict for assertions.
- **Deterministic without LLM** (I-09): reference planner/executor are deterministic; the avoid policy is a
  pure function of observed failures. Real LLM only augments the advisor.
- **4 K8 tests** (`tests/test_capstone_self_evolution.py`, in-process loopback transport, no sockets):
  end-to-end loop closes locally AND propagates to B; tampered/replayed/unsigned exchange rejected;
  replayed soft layer not merged into B; deterministic without LLM.

### Constraints honored
K1/K5/K6 (composition.* → everything; reuses build_kernel, FederationSoftMemorySync, HmacSigner,
ReplayGuard, build_llm_client; no new ports), K8 (verify-before-trust + replay-guard preserved at the
FSE-01 boundary), O1 (self-evolution SOFT; HARD/FSM untouched), I-09 (deterministic without LLM), Флаг C
(standalone factories).

### Non-scope (post-MVP, documented in ADR-085)
Asymmetric crypto (Ed25519/ECDSA/RSA), key rotation/PKI, multi-hop routing/discovery/consensus, multimodal.

---

## ТЗ-CRYPTO-HARDEN-01 — hardening the crypto layer (ADR-084, 2026-08-05) — DONE

Closes the serious MVP gaps flagged by the external audit of ТЗ-CRYPTO-01 (ADR-082).

- **replay-protection** (most serious gap): `ReplayGuard` — per-origin monotonic seq window built on
  the `CausalMark.lamport` clock already carried in FED-01 + FSE-01 wire envelopes. A message with
  `seq <= last-seen` for its origin is rejected (replay / stale duplicate). A captured valid signed
  outcome can no longer be replayed to manipulate trust.
- **canonical_version**: int encoded into the envelope body; `verify_envelope` rejects a version mismatch
  (future format-skew defense). Excluded from canonical bytes so verification stays reproducible.
- **max payload size**: `MAX_ENVELOPE_BYTES` (256 KiB). `canonical_bytes` enforces the limit BEFORE
  sign/verify — oversized messages are rejected without spending CPU on HMAC.
- **unicode NFC**: `canonical_bytes` normalizes every str value via `unicodedata.normalize("NFC", s)`
  (recursive) so equivalent Unicode forms (composed/decomposed, Kelvin sign vs K) produce identical
  canonical bytes — closing a signature-forgery-via-equivalent-string vector.
- **ISigner / IVerifier split**: `ISignatureProvider` now inherits `ISigner` + `IVerifier`; a sign-only
  or verify-only object works at the boundary (minimal audit surface). `HmacSigner` implements both.

### Constraints honored
K1/K6 (stdlib hmac/hashlib/unicodedata; no external SDK in domain), K5 (no duplicated ports; reuses
`CausalMark.lamport` as replay key), K8 (reject replay/oversized/version-mismatch/unsigned/tampered),
O1 (sign/verify/replay never mutate HARD/FSM; trust SOFT via `record_outcome` only from verified +
non-replayed outcomes), I-09 (NFC + sort_keys determinism; correlation by request_id), Флаг C (standalone
factories, not in `build_kernel`).

### Backward-compat
`signature_provider=None` / `replay_guard=None` ⇒ legacy behavior preserved (32 existing CRYPTO-01 +
FED/FSE-01 tests still pass without a provider).

### Non-scope (post-MVP, documented in ADR-084)
Asymmetric crypto (Ed25519/ECDSA/RSA), key rotation/PKI, envelope Header/Payload split, cross-lang float
serialization, multi-hop routing / discovery / consensus.

### Verification
- `tests/test_crypto_harden.py`: 12 K8 passed.
- Existing CRYPTO-01 + FED/FSE-01: 32 passed (backward-compat).
- Full suite 0 failed; arch-gate 14 passed; akb-lint PASSED.

---

## ТЗ-CRYPTO-01 — authenticated origin for cross-node exchange (ADR-082, 2026-08-05) — DONE

Established the crypto substrate: `ISignatureProvider` (new port) + `HmacSigner` (stdlib HMAC-SHA256,
pre-shared per-node key). Sign outgoing facts/outcomes; verify origin + integrity BEFORE merge/trust.
Trust evolves ONLY from verified outcomes. See ADR-082 for detail. Superseded in hardening by ADR-084.

## ТЗ-LIVE-01 extended — living core: background autosave + SIGINT + live mode (ADR-088, 2026-08-05) — DONE
- **K5:** переиспользованы JsonMemoryStore, build_kernel, detect_local_ollama/build_llm_client,
  ProcedureConsolidator, ReferenceExecutor, ReferenceTrustRegistry, InMemoryProceduralMemory.
  НОВЫХ портов/классов НЕ создано (расширение entry-point run_evolution.py).
- **run_evolution.py (extended):** --state-dir (default ./kroft_state) -> <dir>/kernel_state.json
  (mkdir при старте); --llm {auto,none} (auto = detect_local_ollama -> build_llm_client, иначе
  LLM-free; none = форс LLM-free); --ticks 0 = LIVE/forever (блок до SIGINT), N = N тиков + exit/save.
- **background autosave** (stdlib threading.Timer, --autosave-sec default 30; 0 выкл): периодический
  save защищает эволюцию при долгой работе; stop_autosave() отменяет таймер.
- **graceful SIGINT:** signal handler -> stop_autosave(); save(); sys.exit(0).
- **--bg-consolidate** (off by default, deterministic): задел для фонового consolidation/reflection.
- **K8 tests** (tests/kernel/test_live_core.py, Флаг 1b): save->load roundtrip; эволюция через 2
  перезапуска (4->8 эпизодов, soft-политика переживает restart); autosave пишет файл; SIGINT
  graceful save; --llm none детерминирован.
- **K1/K6:** composition-root (cross-layer imports) + stdlib threading/signal; НЕ тянет V3
  runtime/kernel_runtime.py. I-09: LLM-free детерминирован. O1: autosave/load НЕ мутируют HARD.
- Note: ТЗ указывал ADR-081-live, но ADR-081 уже занят в repo (K5 baseline stale) -> ADR-088.

## ТЗ-OMNI-01 — OmniRouter: мульти-провайдерный роутинг с автовыбором и fallback (ADR-089, 2026-08-05) — DONE
- **K5:** переиспользованы IHttpTransport/HttpTransport, OpenAiCompatibleClient, build_llm_client/
  detect_local_ollama, ILLMAdvisor/adapter_for. НЕ дублирован adapters/router.py (Wave 5 PolicyEngine-
  роутер, другой слой). НОВЫХ портов НЕ создано (IModelRouter расширяет ILlm, KROFT one-port-per-boundary).
- **contract (contracts/i_model_router.py):** IModelRouter(ILlm) + ProviderSpec (frozen VO: name,
  base_url, api_key_env, priority, model). providers property + route(query)->ILlm.
- **impl (composition/omni_router.py):** OmniRouter(IModelRouter) — упорядоченный список
  OpenAiCompatibleClient по priority (стабильная сортировка, I-09); complete()/stream() перебирают
  по priority, fallback на LLMError/LLMTimeout; все сбои -> LLMError (retrieval-only, LLM-01).
  build_omni_router: локальный Ollama первым (detect_local_ollama, priority -100); облачные только
  при наличии api_key_env (иначе пропускаются).
- **integration:** build_llm_client(providers=...) возвращает OmniRouter (backward-compat: без
  providers — прежний одиночный клиент). Роутер сам ILlm -> adapter_for/ядро принимают без изменений.
- **K8 tests** (tests/llm/test_omni_router.py, Флаг 1b): первый здоровый выбирается; fallback при
  сбое; все сбои -> LLMError (retrieval-only); детерминизм (priority); K6 (нет SDK в домене, сеть
  через IHttpTransport); пустой роутер (нет ключей/модели) бросает LLMError, не crash.
- **K1/K6:** OmniRouter в composition/ (импортирует adapters — разрешено import_matrix); домен без
  SDK; сеть через IHttpTransport (stdlib urllib). I-09: детерминизм. O1: роутер — советник, fallback
  защищает (LLM-01), ядро LLM-free по конструкции.

## ТЗ-AGENT-LOOP-01 — Agent Loop: итеративный goal-driven цикл поверх ядра (ADR-090, 2026-08-05) — DONE
- **K5:** IAgentPlatform.run (ADR-014) — single-shot mission (нет budget, нет inter-step feedback);
  IAgentExecutor.execute (ADR-080) — один tick; ReferenceAgentExecutor — один tick. НИ ОДИН НЕ
  итеративный loop -> IAgentLoop НОВЫЙ шов (НЕ дублирует IAgentPlatform/IAgentExecutor/ILlm/ILLMAdvisor).
  Переиспользованы build_kernel, CognitiveKernel.tick, ReferenceExecutor, ReferenceAgentExecutor,
  IAgentExecutor/TaskOutcome/OrchestrationGoal.
- **contract (contracts/i_agent_loop.py):** IAgentLoop (run(goal, budget) -> AgentLoopResult) +
  AgentLoopResult (frozen VO: success, steps_taken, final_outcome, memory_delta).
- **impl (kernel/agent_loop.py, K6: kernel->kernel):** AgentLoop итерирует build_kernel + kernel.tick
  с observation-feedback (intent.text = goal + prior observations -> planner ре-планирует); stop на
  budget ИЛИ отсутствии плана (цель достигнута); LLM-free (I-09 детерминизм); memory_delta = observations
  + world-fact count (публичный kernel.snapshot(), без private); опц. injected kernel (тесты/resume);
  all-fail -> AgentLoopResult(success=False, error), не crash.
- **integration (kernel/agent_executor.py):** LoopAgentExecutor(IAgentExecutor) обёртывает AgentLoop
  за портом IAgentExecutor (orchestrator dispatch принимает без изменений); маппит AgentLoopResult ->
  TaskOutcome; failure -> TaskOutcome(success=False). build_loop_agent_executor. ReferenceAgentExecutor
  (single-tick) НЕ тронут (backward-compat).
- **K8 tests** (tests/agent_orchestration/test_agent_loop.py, Флаг 1b): цикл итерирует до budget;
  budget-limit (budget=1 -> 1 шаг); observation кормит репланирование (feedback trail растёт);
  память обновляется между шагами (episodes накапливаются); детерминизм (I-09); all-fail graceful;
  LoopAgentExecutor -> TaskOutcome; existing AGENT-EXEC тесты целы (40 passed).
- **K1/K6/O1/I-09:** kernel->kernel (K6); LLM-free детерминизм (I-09); failure -> graceful result (O1).

## ТЗ-KNOWLEDGE-ENGINE-01 — Knowledge Engine: инжестия документов -> граф (ADR-091, 2026-08-05) — DONE
- **K5:** проверено, что contracts/i_knowledge.py УЖЕ имеет IEntityExtractor/IKnowledgeGraph +
  Entity/Relation/Hypothesis/Fact/IngestReport; knowledge_graph УЖЕ имеет IGraphEngine + Node/Edge.
  IKnowledgeEngine (doc -> extraction -> graph update) и KnowledgeExtraction НЕ существовали ->
  НОВЫЙ шов (НЕ дублирует i_knowledge.py). KnowledgeExtraction переиспользует Entity/Relation/Fact.
- **contract (contracts/i_knowledge_engine.py):** IKnowledgeEngine (ingest(doc_id, text) ->
  KnowledgeExtraction) + KnowledgeExtraction (frozen VO: entities, relations, facts).
- **impl (services/knowledge_engine.py, K6: services->contracts; graph+content_index+extractor
  ИНЪЕКТИРУЮТСЯ):** LLM-free эвристика (# headers + [[wikilink]]); relations -> REFERENCES +
  BACKLINKS edges; facts из relations; идемпотент (get_node check + idempotent add_edge); опц.
  LLM-advisor (IEntityExtractor) non-blocking. enum расширен: NodeType.NOTE, EdgeType.BACKLINKS.
- **integration (composition/knowledge_engine_factory.py, Флаг C):** build_default_engine +
  ingest_file (stdlib read, БЕЗ SDK) — Obsidian-источник = явный ingest (live-watcher post-MVP).
- **K8 tests** (tests/knowledge_graph/test_knowledge_engine.py, Флаг 1b): ingest -> граф растёт
  (nodes/edges); отношения из wikilinks; backlinks (reverse edges); детерминизм (I-09); LLM-free
  работает; дубликат-инжест идемпотентен; малформированный doc -> пустая extraction (O1);
  optional LLM-extractor обогащает; existing knowledge_graph/graph тесты целы (246 passed).
- **K1/K6/O1/I-09:** services->contracts (K6); LLM-free детерминизм (I-09); malformed -> graceful (O1).

## ТЗ-EVOLUTION-01 — Skill Evolver: self-improving skills (ADR-092, 2026-08-05) — DONE
- **K5:** проверено, что IExecutionSandbox/SubprocessSandbox (ADR-039), Procedure (frozen VO),
  IProceduralMemory/InMemoryProceduralMemory (store_skill/recall/record_skill_outcome),
  PolicyLifecycle.SUPERSEDED — ВСЁ УЖЕ есть. НЕТ ISkillEvolver/ISkillEvaluator/SkillUsageStats/
  SkillVariant/EvalResult -> создан НОВЫЙ шов (НЕ дублирует IExecutionSandbox/Procedure/PolicyLifecycle).
  Procedure расширен version+lifecycle (K5, НЕ дубль).
- **contract (contracts/i_skill_evolver.py):** ISkillEvolver (propose_improvement -> SkillVariant) +
  ISkillEvaluator (test_in_sandbox -> EvalResult) + VOs (SkillUsageStats, SkillVariant, EvalResult).
  Procedure расширен version:int=1 + lifecycle:PolicyLifecycle=ACTIVE (contracts/i_memory.py).
- **impl (services/skill_evolution.py, K6: services->contracts; sandbox+memory инъектируются):**
  LLM-free эвристика (min_uses + success_threshold; дроп longest step), test_in_sandbox через
  SubprocessSandbox (step = изолированная команда, score = доля exit-0), better -> update
  (version+1/ACTIVE + old SUPERSEDED в self._history), not-better -> старый сохранён. Опц. LLM-advisor
  (non-blocking). Детерминизм (I-09). O1: sandbox failure -> score 0, не crash, не мутирует HARD/FSM.
- **integration (composition/skill_evolution_factory.py, Флаг C):** build_default_skill_evolver
  (SubprocessSandbox + InMemoryProceduralMemory). НЕ в build_kernel (opt-in).
- **K8 tests** (tests/skills/test_skill_evolution_sandbox.py, Флаг 1b): usage>=N + low efficiency ->
  предложение; usage<N / high efficiency -> None; sandbox-тест (изолирован, O1); better -> update
  (version+1, old SUPERSEDED); not-better -> старый сохранён; детерминизм; Procedure version+lifecycle.
  Existing SKILL/SKILL-EVOLVE тесты целы (16 passed).
- **K1/K6/O1/I-09:** services->contracts (K6); LLM-free детерминизм (I-09); sandbox failure graceful (O1).

## ТЗ-MARKETPLACE-01 — Marketplace: package/sign/publish/install с trust-гейтингом (ADR-093, 2026-08-05) — DONE
- **K5:** проверено, что contracts/i_signature.py УЖЕ имеет ISignatureProvider + attach_signature/
  check_signature (HMAC, stdlib) — переиспользуем (НЕ дублируем). HmacSigner только в kernel/crypto.py
  (K6: services НЕ импортирует kernel) -> создан adapters/hmac_signer.py (адаптер-слой, К5 services->adapters
  OK, НЕ дубль). contracts/i_identity.py УЖЕ имеет ITrustRegistry (trust_score_of) — переиспользуем для
  trust-гейта. Procedure (version/lifecycle из EVOLUTION-01) + PluginManifest (PLUGIN-01) — переиспользуем
  как payload. SkillPackage + ISkillRepository — НОВЫЕ швы (НЕ дублируют порты).
- **contract (contracts/i_marketplace.py):** SkillPackage (frozen VO: id/name/version/author/capabilities/
  payload_type/payload/signature) + ISkillRepository (publish/verify/install/list).
- **impl (adapters/hmac_signer.py + services/skill_marketplace.py, K6: services->contracts+adapters):**
  HmacSigner (адаптер, ISignatureProvider). SkillPackager.package(Procedure/Plugin -> signed SkillPackage
  via attach_signature). SkillRepository publish/verify/install: install верифицирует подпись (check_signature)
  + trust-гейт (trust_score_of(author) >= threshold); untrusted/tampered -> None (O1, не мутирует store);
  version supersede (old SUPERSEDED). Детерминизм (I-09, HMAC canonical_bytes).
- **integration (composition/skill_marketplace_factory.py, Флаг C):** build_default_marketplace (HmacSigner
  + repo). НЕ в build_kernel (opt-in).
- **K8 tests** (tests/marketplace/test_marketplace.py, Флаг 1b): package+sign+publish; install verifies
  signature (roundtrip на другом store); untrusted author -> rejected; tampered payload -> rejected; version
  supersede (SUPERSEDED); determinism; plugin payload packs+installs. Existing PLUGIN/EVOLUTION/IDT тесты
  целы (49 passed).
- **K1/K6/O1/I-09:** stdlib hmac (K1); services->contracts+adapters (K6); untrusted/tampered -> safe deny (O1);
  HMAC детерминизм (I-09). Флаг C/1b.

## ТЗ-FED-REPL-01 — Federation replication of signed SkillPackages (ADR-094, 2026-08-05) — DONE (Этап 6 завершён)
- **K5:** contracts/i_network_transport.py УЖЕ имеет INetworkTransport.send_soft_layer/on_soft_layer (NW-01) —
  переиспользуем для передачи SkillPackage как wire-dict (НЕ новый transport-канал). services/distributed_runtime.py
  FederationSoftMemorySync (FSE-01) — ПАТТЕРН (publish via send_soft_layer + on_soft_layer handler + verify + trust-gate);
  следуем ЭТОМУ ЖЕ shape (НЕ дублируем). contracts/i_marketplace.py УЖЕ имеет SkillPackage + ISkillRepository
  (install = verify + trust gate + version supersede) — переиспользуем на принимающем узле (второй install-путь
  НЕ создаём). ISignatureProvider (i_signature) + ITrustRegistry (i_identity) переиспользуются внутри
  ISkillRepository.install. ISkillDistributor — НОВЫЙ шов (НЕ дублирует порты).
- **contract (contracts/i_skill_distributor.py):** ISkillDistributor — publish_remote(pkg, transport) (ship via
  transport.send_soft_layer([asdict(pkg)], node_id)) + on_remote_package(pkg_dict, trust_registry, threshold)
  (rebuild SkillPackage -> SkillRepository.install).
- **impl (services/skill_distributor.py, K6: services->contracts only):** SkillDistributor следует FSE-01 shape —
  on_soft_layer(self._handle_inbound) в конструкторе/bind. on_remote_package перестраивает SkillPackage и
  делегирует SkillRepository.install (verify + trust-gate + version supersede). Deterministic (I-09).
- **integration (composition/skill_distributor_factory.py, Флаг C):** build_default_skill_distributor (SkillRepository
  + transport + trust) — НЕ в build_kernel.
- **bug-fix (MARKETPLACE-01 install):** version supersede ранее искал old_pkg в _packages (только publish заполняет);
  federation-installs приходят БЕЗ _packages -> old НЕ попадал в superseded. Исправлено: supersede добавляет prev
  (уже установленный payload), который ВСЕГДА присутствует. (amended into C2 before push.)
- **K8 tests** (tests/federation/test_federation_replication.py, Флаг 1b): package A->B via INetworkTransport, B
  verifies + installs; untrusted author -> rejected; tampered payload -> rejected; version supersede между узлами;
  determinism. Existing FED/MARKETPLACE/IDT тесты целы.
- **K1/K5/K6/O1/I-09:** stdlib hmac (K1); services->contracts (K6, transport/repository/trust injected); untrusted/
  tampered -> safe deny (O1); HMAC детерминизм (I-09). Флаг C/1b.

## ТЗ-CAPSTONE-02 — Distributed skill-evolution capstone: end-to-end self-evolution (ADR-095, 2026-08-05) — DONE
- **K5:** PURE COMPOSITION — НИЧЕГО нового не создаётся (капстоун). Переиспользованы SkillEvolver (EVOLUTION-01),
  SkillPackager/SkillRepository (MARKETPLACE-01), SkillDistributor (FED-REPL-01), ITrustRegistry (IDT-01),
  ISignatureProvider/HmacSigner (CRYPTO-01), SubprocessSandbox (ADR-039), InMemoryProceduralMemory, INetworkTransport
  (NW-01). НЕТ новых портов/контрактов.
- **composition/capstone_distributed.py (Флаг C, НЕ в build_kernel):** LoopbackTransport (INetworkTransport,
  in-process, shared bus) + DistributedNode (оборачивает evolver+repo+distributor+trust, injected sandbox/memory) +
  build_distributed_capstone() (2 узла A,B, shared signer+trust+bus). DistributedNode.evolve_and_publish (sender:
  evolve -> package -> publish_remote) + use_skill (receiver: выполняет установленный Procedure через sandbox ->
  success_rate = поведение B).
- **composition/capstone_scenario.py (Флаг C):** run_capstone_scenario() — A: low-eff skill -> evolve -> package ->
  publish_remote -> B: install -> use_skill (behavior changes). Deterministic (I-09).
- **K8 tests** (tests/capstone/test_distributed_capstone.py, Флаг 1b): end-to-end A улучшает -> B получает ->
  поведение B меняется (None -> 1.0); untrusted author -> rejected (O1); tampered payload -> rejected (O1);
  version supersede между узлами; determinism. Existing EVOLUTION/MARKETPLACE/FED-REPL тесты целы (28 passed).
- **K1/K5/K6/O1/I-09:** stdlib hmac (K1); composition-only, ZERO new ports (K5); services stay axis-clean, composition
  imports services+adapters+kernel (K6); untrusted/tampered -> safe deny (O1); LLM-free evolver + HMAC детерминизм (I-09).
  Флаг C/1b. Поведение B РЕАЛЬНО меняется (не просто install).

## ТЗ-AUTHOR-KEYS-01 — Per-author HMAC keys: author bound to its key (ADR-096, 2026-08-05) — DONE
- **K5:** ISignatureProvider/HmacSigner (CRYPTO-01) УЖЕ есть — переиспользуем (НЕ дублируем). SkillPackager
  УЖЕ принимает signer (per-author HmacSigner) — НЕ меняем сигнатуру. SkillRepository.verify расширен: если
  автор зарегистрирован в IAuthorKeyRegistry -> verify через get_signer(author) (HmacSigner(author_key)); ИНАЧЕ
  fallback на общий _signer (backward-compat с MARKETPLACE/FED-REPL/CAPSTONE shared-key сценариями). IAuthorKeyRegistry
  + AuthorKey — НОВЫЙ шов (НЕ дублирует ISignatureProvider).
- **contract (contracts/i_author_keys.py):** AuthorKey (frozen VO: author/key) + IAuthorKeyRegistry
  (register_key/get_key/get_signer/has).
- **impl (services/skill_marketplace.py, K6: services->contracts only):** SkillRepository.__init__ принимает
  author_key_registry; verify предпочитает registry.get_signer(pkg.author) когда автор зарегистрирован, иначе
  fallback на общий signer. install -> verify (unchanged). build_skill_repository расширен параметром.
- **integration (composition/author_keys_factory.py, Флаг C):** AuthorKeyRegistry (in-memory) +
  build_author_key_registry (seeding author->key); get_signer строит HmacSigner(key) из adapters. НЕ в build_kernel.
- **K8 tests** (tests/security/test_author_keys.py, Флаг 1b): sign author key + verify (per-author); wrong registered
  key -> rejected (forged); unregistered author -> fallback shared (backward-compat); author-bound (alice key verifies
  via alice registry, NOT shared-only); backward-compat shared key no-registry; determinism. Existing MARKETPLACE/
  FED-REPL/CAPSTONE tests intact (26 passed) — shared-key scenarios keep working.
- **K1/K5/K6/O1/I-09:** stdlib hmac (K1); IAuthorKeyRegistry НЕ дублирует ISignatureProvider (K5); services->contracts
  only (K6, concrete HmacSigner в composition); wrong/forged/unregistered key -> safe deny (O1); HMAC детерминизм (I-09).
  Флаг C/1b. Closes Флаг 3 (MARKETPLACE/FED-REPL/CAPSTONE) pragmatically; Ed25519/PKI, key rotation/revocation,
  key distribution — post-MVP.

## ТЗ-DESKTOP-01 — Observability dashboard: read-only kernel-state snapshot (ADR-097, 2026-08-05) — DONE
- **K5:** OBS-01 (ILiveMetricsCollector/RuntimeSupervisor) отвечает на «как хорошо система работает?»
  (operational RATIO metrics) — НЕ дублируем. Dashboard отвечает на «какое ТЕКУЩЕЕ СТРУКТУРНОЕ состояние?»
  (memory/agents/trust/models/tasks/FSM) — отдельный boundary (one-port-per-boundary). DashboardSnapshotter
  — ЧИСТЫЙ aggregator/renderer: принимает READ-ONLY providers (callables), собирает frozen DashboardSnapshot;
  НЕ импортирует kernel/identity/services => структурно read-only (не мутирует ядро). Composition связывает
  providers с реальными компонентами через их публичные аксессоры (K5: reuse, НЕ дублирует state-аксессоры).
- **contract (contracts/i_dashboard.py):** DashboardSnapshot (frozen VO: node_id, kernel_state, memory_counts,
  agents, trust, models, tasks, captured_at) + IDashboard (snapshot/render_text/render_json).
- **impl (services/desktop_dashboard.py, K6: services->contracts only):** DashboardSnapshotter — PURE
  aggregator/renderer. snapshot() вызывает providers (read-only) -> frozen VO. render_text/render_json
  детерминированы (json sort_keys). НЕ импортирует kernel/identity/services (только callables).
- **integration (composition/desktop_dashboard_factory.py, Флаг C):** build_default_dashboard(kernel,
  memory_platform, trust_registry, identity_registry, task_store, model_registry, ...) — строит providers
  из реальных компонентов через публичные аксессоры (duck-typed _mem_counts: layered get_episodes/get_semantic/
  get_normative ИЛИ procedural list_skills; _trust_authors: authors() ИЛИ _by_author). НЕ в build_kernel.
  READ-ONLY: snapshotter пишет в frozen VO, НЕ мутирует ядро/HARD/FSM (O1-safe). Missing component -> empty.
- **K8 tests** (tests/desktop/test_dashboard.py, Флаг 1b): snapshot отражает memory/agents/trust/tasks/
  kernel-state; read-only (НЕ мутирует kernel/trust/memory — verified); determinism (frozen VO + stable JSON);
  missing components graceful; IDashboard contract. Existing desktop tests intact (13 passed: 5 dashboard + 8 desktop).
- **K1/K5/K6/O1/I-09:** stdlib only (K1); DashboardSnapshotter НЕ дублирует OBS-01, reuse state-аксессоров (K5);
  services->contracts only (K6); read-only (O1-safe, structurally cannot mutate); frozen VO + json sort_keys
  determinism (I-09); Флаг C (НЕ в build_kernel). Замыкает ВСЕ 7 capability-этапов + 2 капстоуна. Non-scope
  (post-MVP): pyautogui-GUI, Ed25519/PKI/key-distribution, live-refresh loop.

## ТЗ-KEYDIST-01 — Key distribution + rotation/revocation for per-author HMAC keys (ADR-098, 2026-08-05) — DONE
- **K5:** IAuthorKeyRegistry/ISignatureProvider (CRYPTO-01) УЖЕ есть — переиспользуем (НЕ дублируем). canonical_bytes/
  check_signature (i_signature) переиспользуются для bootstrap-подписи KeyRecord. KeyRecord + IKeyDistribution — НОВЫЙ шов.
- **contract (contracts/i_key_distribution.py):** KeyRecord (frozen VO: author, key, version, signed_by, signature, revoked)
  + IKeyDistribution (publish_key/fetch_key/is_revoked/revoke/get_signer).
- **impl (composition/key_distribution_service.py, Флаг C):** KeyDistributionService — bootstrap trust-anchor (pre-shared HMAC-ключ,
  MVP допущение) HMAC-подписывает key-records через HmacSigner(bootstrap_key) + canonical_bytes/check_signature (reuse i_signature);
  fetch_key верифицирует bootstrap-подпись (tampered -> None, O1); rotation (version > existing, ValueError иначе); revoke
  (fetch/get_signer -> None, is_revoked True). get_signer возвращает HmacSigner(rec.key).
- **integration (services/skill_marketplace.py, K6: services->contracts only):** SkillRepository + key_distribution параметр;
  verify приоритет: valid+не-revoked distributed key -> author_key_registry -> shared signer (backward-compat с MARKETPLACE/
  FED-REPL/CAPSTONE). build_skill_repository расширен.
- **K8 tests** (tests/security/test_key_distribution.py, Флаг 1b): publish/fetch с bootstrap-подписью; tampered -> rejected;
  rotation supersedes (non-increasing -> ValueError); revoked -> rejected; SkillRepository verify via distribution (revoked -> reject);
  backward-compat локальный registry без distribution; determinism; existing AUTHOR-KEYS/MARKETPLACE/FED-REPL целы (21 passed).
- **K1/K5/K6/O1/I-09:** stdlib hmac (K1); IKeyDistribution НЕ дублирует IAuthorKeyRegistry/ISignatureProvider (K5); services->contracts
  only (K6); tampered/revoked/unknown -> safe deny (O1); HMAC детерминизм (I-09); Флаг C (НЕ в build_kernel). Закрывает security-долг
  AUTHOR-KEYS-01 (Флаг 2: key distribution). Ed25519/PKI, реальный bootstrap, OCSP-like revocation — post-MVP.

## ТЗ-DAILY-01 — Daily-use pipeline: live vault data + interactive contour (ADR-101, 2026-08-06) — DONE
- **K5:** Замена demo-seed ЖИВЫМИ данными. ObsidianVaultReader (stdlib pathlib, НОВЫЙ узкий шов) читает
  *.md; KnowledgeEngine.ingest (ТЗ-KNOWLEDGE-ENGINE-01, ADR-091, ПЕРЕИСПОЛЬЗОВАН) наполняет граф ->
  dashboard memory_notes = реальное число заметок vault (graceful: нет vault -> 0). TaskStore
  (services/task_store.py, НОВЫЙ — существовавшего НЕ было) = реальные queued задачи. run_kroft:
  --vault <path> + --interactive (query -> kernel FSM tick -> ReferenceSearchService (ТЗ-SEARCH-01)
  отвечает из живого графа). agents/models/marketplace остаются demo для наглядности.
- **K1/K5/K6/K8/O1/I-09:** stdlib read vault; reuse KnowledgeEngine/ContentIndex/ReferenceSearchService;
  services->contracts; graceful degradation; детерминизм. Флаг 2 (light): dashboard читает приватные
  _installed/_peers/_state (duck-typed OK, перевести на публичные когда появятся).
- **Тесты:** tests/desktop/test_run_kroft.py (13: 8 RUN-01 + 5 DAILY) PASS; ad-hoc реальный vault ->
  memory_notes=16139 (живые). akb-lint 99->100 ADR.

## ТЗ-RUN-01 ext — KROFT Desktop control panel (ADR-100, 2026-08-06) — DONE
- **K5:** Расширение DESKTOP-01 (ADR-097), НЕ новый порт. DashboardSnapshot (frozen VO) расширен
  полями marketplace_skills / federation_nodes / memory_notes / trust_score / logs. DashboardSnapshotter
  принимает duck-typed провiders; build_default_dashboard (composition) подключает РЕАЛЬНЫЕ компоненты
  через публичные аксессоры (IdentityRegistry.list, ModelRegistry.catalog, SkillRepository._installed,
  SkillDistributor._peers, InMemoryGraphEngine.nodes, ReferenceTrustRegistry.current_trust, logs ring buffer).
- **run_kroft.py:** создаёт и сидит demo-компоненты (6 agents, qwen3.5/llama3, 52 skills, 245 notes,
  trust 0.97) → панель "KROFT Desktop" показывает ЖИВЫЕ цифры (Kernel/Agents/Tasks/Models/Marketplace/
  Federation/Memory/Trust/Logs). K6: services→contracts only. O1/I-09: read-only, детерминизм.
- **Тесты:** tests/desktop/test_dashboard.py (8) + test_run_kroft.py (8) — PASS. akb-lint 98→99 ADR.
## ТЗ-RUN-01 — Bootable KROFT_OS: single entry point lifting the whole stack (ADR-099, 2026-08-05) — DONE

- **K5:** PURE COMPOSITION over existing components — NO new contract/port. Reuses build_kernel (kernel/cognitive_kernel.py,
  CognitiveKernel with FSM tick), SkillEvolver (EVOLUTION-01), InMemoryLayeredMemory + InMemoryProceduralMemory,
  build_default_dashboard (DESKTOP-01), build_llm_client/OmniRouter (OMNI-01), SkillDistributor + SkillRepository +
  ReferenceTrustRegistry (FED-REPL-01). Does NOT duplicate run_evolution.py (that script owns persistence/autosave/live-loop;
  run_kroft is the higher-level boot-everything + dashboard + demo aggregator).
- **entry (composition/run_kroft.py, Флаг C):** KroftConfig (dataclass) + KroftApp. Boot kernel + optional LLM
  (none/auto/mock) + evolution (SkillEvolver) + optional federation (SkillDistributor via LoopbackTransport) + dashboard
  (build_default_dashboard). run_demo(ticks) loops: kernel.tick(Intent) + evolve demo skill + render read-only dashboard
  snapshot. CLI: python composition/run_kroft.py [--node-id X] [--llm none|auto|mock] [--federation] [--ticks N] [--no-demo].
- **graceful degradation (K5):** LLM and federation OPTIONAL; without them the app boots and runs a deterministic,
  LLM-free evolution demo (I-09). No network/external model required for the default run. Evolution via SkillEvolver
  heuristic (deterministic). Dashboard read-only (DESKTOP-01, O1-safe).
- **K8 tests** (tests/desktop/test_run_kroft.py, Флаг 1b): boot без LLM (determinism); boot с mock LLM; dashboard рендерит
  state; эволюция прогрессирует (demo skill v1->v2); graceful degradation (нет LLM/федерации); federation boot optional.
- **K1/K5/K6/O1/I-09:** stdlib + contracts (composition imports everything, K6-clean for services it reuses); determinism
  (I-09); read-only dashboard (O1/DESKTOP-01). Culmination of the capability+security ТЗ series — ALL 7 capability
  stages + 2 capstones + security core (AUTHOR-KEYS-01 + KEYDIST-01) CLOSED.

## Agents v0.1 (Research Agent First) — Agent Behaviour Layer (ADR-102, 2026-08-06) — DONE
- **K5 GO:** Не новый Agent Framework. K5-разведка: инфраструктура агентов УЖЕ полна (IAgent/IAgentLoop/
  IAgentExecutor/IAgentPlatform, ReferenceAgentExecutor, AgentPlatform, Orchestrator.dispatch по
  capability x trust, KnowledgeEngine + ReferenceSearchService). НОВЫЙ порт/слой НЕ создан.
- **Этап 0 (K5):** зафиксировано — Orchestrator выбирает агента по `goal.capability in agent.specialization`,
  скоринг = trust; agent-путь зовёт подключённый IAgentExecutor. specialization = str (research/architecture/
  coding/writing/finance/sales), совпадает с AgentIdentity.specialization.
- **Этап 1 (ADR):** ADR-102 «Agent Behaviour Layer» — поведение = реализация IAgentPlatform/IAgentExecutor,
  инъецирующая доменные сервисы; НЕ новый уровень архитектуры.
- **Этап 2 (Research Agent):** services/research_agent.py — ResearchAgent(IAgentPlatform) реально зовёт
  ReferenceSearchService по живому графу vault (НЕ fixed answer), LLM опционален (graceful, I-09);
  ResearchAgentExecutor(IAgentExecutor) монтирует агента в Orchestrator.dispatch.
- **Этап 3 (интеграция):** run_kroft строит Orchestrator + вешает ResearchAgentExecutor; interactive_query
  маршрутизирует research-интенты через dispatch (Goal -> Orchestrator -> ResearchAgent ->
  KnowledgeEngine/ReferenceSearchService -> AgentResult). Dashboard показывает agent.research как active.
- **Этап 4 (тесты):** tests/agent/test_research_agent.py (6 K8): surface/dispatch/research-cycle/graceful/
  optional-LLM/backward-compat. Arch-gate 17 passed (K5/K6: services импортирует только contracts).
  akb-lint 100->101 ADR.
- **K1/K5/K6/K8/O1/I-09:** stdlib + contracts; 0 новых портов; 0 новых слоёв; read-only orchestrator;
  детерминизм. Следующие агенты (Architect/Programmer/Writer/Finance/Sales) = тот же паттерн, ядро НЕ меняется.

## Agents v0.1 cont. — Architect Agent + MultiAgentExecutor (ADR-102, 2026-08-06) — DONE
- **Продолжение** Agents v0.1 (Research Agent First) без изменения ядра. Тот же паттерн.
- **MultiAgentExecutor (новый шов, НЕ порт):** `services/multi_agent_executor.py::MultiAgentExecutor(IAgentExecutor)`
  — map `capability -> executor`, делегирует `Orchestrator.dispatch` к нужному агенту. Необходим, т.к.
  `build_orchestrator` принимает ровно один `agent_executor`; K6-clean (services→contracts only).
- **Architect Agent:** `services/architect_agent.py::ArchitectAgent(IAgentPlatform)` + `ArchitectAgentExecutor`
  (фокус на архитектуру/ADR), `self.capability="architecture"`. Тот же шаблон что ResearchAgent.
- **Интеграция:** `run_kroft` строит `Orchestrator(agent_executor=MultiAgentExecutor([research_exec, architect_exec]))`;
  `interactive_query` роутит `architecture` через `dispatch` (наравне с `research`), остальное — legacy path.
- **Тесты:** tests/agent/test_architect_agent.py (5 K8): real-search / routing / scope / unknown-capability / graceful.
  Смежные: research-agent + arch-gate 28 passed; run_kroft --no-demo стартует. K1/K5/K6/K8/O1/I-09.
- **Следующие (Programmer/Writer/Planner/Finance):** добавляются тем же швом — новый `services/<x>_agent.py`
  + `<X>AgentExecutor` + регистрация в `MultiAgentExecutor`. Ядро НЕ меняется.

## Agents v0.1 cont. — Programmer Agent (ADR-102, 2026-08-06) — DONE
- **Продолжение** Agents v0.1 без изменения ядра. Тот же паттерн что Architect/Research.
- **Programmer Agent:** `services/programmer_agent.py::ProgrammerAgent(IAgentPlatform)` + `ProgrammerAgentExecutor`
  (`capability="coding"`, фокус на code/implementation). `run_kroft` регистрирует в `MultiAgentExecutor`.
- `interactive_query` роутит coding-интенты (code/function/implement/class/bug/refactor/python) через `dispatch`.
- **Тесты:** tests/agent/test_programmer_agent.py (4 K8): real-search / routing / scope / graceful. K1/K5/K6/K8/O1/I-09.

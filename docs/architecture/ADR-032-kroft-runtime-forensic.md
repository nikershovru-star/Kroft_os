# ADR-032 — KROFT Runtime + Universal Agent Interface + Local Federation (Forensic Baseline)

**Статус:** READ-ONLY forensic (ТЗ ГЛОБАЛЬНОЕ STEP 0–9). Код НЕ писался.
**Дата:** 2026-08-16
**HEAD:** `3f67934`
**Мандат:** KROFT = самостоятельный Runtime; Hermes/Codex/Claude = внешние клиенты
через Universal Agent Interface. НЕ встраивать Hermes в KROFT.

---

## STEP 0 — BASELINE (зафиксировано)

- HEAD `3f67934`. Branch `master`. Ahead of origin (накоплено из прошлых сессий).
- Uncommitted: sibling changes (`run_kroft.py M`, `kernel/search.py M`,
  `contracts/i_orchestrator.py M`, `contracts/i_workflow.py M`,
  `adapters/openai_compatible.py M`, `composition/llm_client_factory.py M`,
  services/* M) + untracked (`contracts/text_processing.py`,
  `adapters/deepseek_adapter.py`, `adapters/web_search_adapter.py`,
  `services/kroft_node_manager.py`, `tests/test_kroft_node_manager.py`,
  `tests/test_kroft_net_isolation.py`, `composition/_KROFT_MEMORIES/`,
  `docs/architecture/N0-local-network-forensic-isolation.md`).
- **КРИТИЧНО:** `run_kroft.py:355` импортирует `contracts.text_processing`
  (untracked sibling-файл). Без него `KroftApp` НЕ грузится (ModuleNotFoundError).
  Это sibling-diff, НЕ моё — ТЗ §35: НЕ трогать unrelated modified files.
- `KROFT_KNOWLEDGE_FOUNDATION/_snapshot.json` (~750MB) — НЕ в `.gitignore`,
  НЕ коммитить (правило пользователя).

## STEP 1 — RUNTIME FORENSIC

Существует ДВА boot-path (уже известно из прошлых аудитов):
1. `main.py` + `composition/container_builder.py:build_container` — DI-контейнер,
   регистрирует GraphQueryEngine/ContentIndex/SemanticIndex/KROFT_OSServer/AgentService.
   **УЖЕ грузит foundation snapshot** (container_builder.py:213-249)!
2. `composition/run_kroft.py:KroftApp` — альтернативный boot, сам собирает всё вручную.
   Тоже грузит foundation (`_restore_graph_and_index` + `load_semantic_vectors`).

**GAP A (foundation snapshot невидим для CLI/runtime):** ЧАСТИЧНО ЗАКРЫТ —
оба пути грузят `_snapshot.json`. Но `main.py` требует `kroft_os.yaml` config
+ DI-контейнер; `KroftApp` — свой dataclass `KroftConfig`. Единого Runtime-слоя
(daemon lifecycle: start/serve/stop/recover/health) НЕТ — `cmd_serve` просто
крутит `while True: sleep(1)`.

## STEP 2 — AGENT INTERFACE FORENSIC

- `contracts/agent.py:IAgent` — `execute(command) -> {plan, results}`.
  Это внутренний agent KROFT (Stage 33), НЕ универсальный внешний контракт.
- **НЕТ** `IKroftAgentInterface` (status/search/query/resolve/audit/observe/
  memory/knowledge). GAP E (по ТЗ) подтверждён.
- `KROFT_OSServer` (http_server.py) уже предоставляет `/api/agent/execute`,
  `/api/search`, `/api/hybrid`, `/api/semantic`, `/api/graph` — НО завязан на
  `main.py` DI-контейнер, не на единый Runtime-контракт.

## STEP 3 — CLI / SERVER FORENSIC

- `main.py` + `cli/commands.py` УЖЕ имеют: `status`, `search`, `query` (backlinks/
  path/orphans/tags/stats), `semantic`, `hybrid`, `agent`, `serve`, `export`,
  `repl`, `crawl`, `schedule`, `desktop`, `watch`, `stop`, `init`.
- `cli/commands.py` НЕ импортирует adapters напрямую (резолвит из container) —
  K1/K6-чисто. Но каждая команда САМА строит Kernel/container (per-command
  spin-up, no daemon) — это НЕ клиент Runtime (ТЗ §6: CLI должен стать
  клиентом Runtime, а не альтернативной реализацией ядра).
- `cmd_serve` (cli/commands.py:445) уже поднимает `KROFT_OSServer` (HTTP).
- **Вывод:** HTTP API (KROFT_OSServer) УЖЕ существует (ТЗ §5: НЕ создавать
  заново, reuse/adapt). CLI commands УЖЕ существуют, но надо переделать в
  клиенты Runtime.

## STEP 4 — FEDERATION FORENSIC (подтверждает ADR-030 + N0)

УЖЕ есть (prove-by-code):
- `adapters/tcp_event_bus.py:TcpEventBus` (TCP pub/sub, port/host parametric)
- `kernel/federated_orchestrator.py:ReferenceRemoteOrchestrator` (trust-gate,
  multi-hop routing, replay-guard)
- `contracts/i_signature.py` (sign/verify) + `kernel/crypto.py:ReplayGuard`
- `adapters/crdt_graph.py:CrdtGraphEngine` (LWW + PN-counter merge)
- `contracts/i_identity.py` (ReferenceIdentityRegistry / ReferenceTrustRegistry)
- `docs/architecture/N0-local-network-forensic-isolation.md` — УЖЕ доказал
  multi-instance isolation в одном процессе (A≠B storage/identity/network/kernel).

НЕТ (GAP F/G/H):
- `KnowledgeEnvelope` VO (knowledge_id/content/origin/resolution/confidence/
  provenance/trust/scope/ttl/sender/signature)
- origin-aware acceptance (`can_accept` из ADR-028 Этап 4 НЕ вызывается из
  federation-path)
- quarantine (reject → сохранять, не молча дропать)
- trust-level policy (TRUST 0..5 поверх `current_trust`)

## STEP 5 — PERSISTENCE / BOOT FORENSIC

- `composition/knowledge_persistence.py:KnowledgeSnapshotStore` — 9 слоёв
  (graph/index/trust/procedural/episodes/semantic/normative/vectors +
  abstraction_sidecar из ADR-028 Этап 2). `save()`/`load()` + `load_semantic_vectors()`.
- Boot sequence в `KroftApp.__init__`: memory → procedural → llm → router →
  live_metrics → embedding → content_index → kernel(build_kernel) → identity →
  models → skill_repo → graph → engine → vault_reader → snapshot_restore →
  semantic_index → trust → agents → agent_runtime. Порядок УЖЕ определён в коде.
- GAP B (build_container MockEmbedding): ЧАСТИЧНО ЗАКРЫТ — `build_container`
  (container_builder.py:92-97) пробует `OllamaEmbeddingAdapter(bge-m3)`, fallback
  Mock. Но `KroftApp` default `embedding="none"` (lexical-only). GAP C/D
  (ReferenceSearchService / cognitive_kernel lexical-only) — подтверждён из
  прошлых аудитов; не чинить в этом ТЗ автоматически (ТЗ §37: классифицировать).

## STEP 6 — MULTI-INSTANCE FEASIBILITY

- `N0-local-network-forensic-isolation.md` УЖЕ доказал: 2 инстанса в одном
  процессе с разными storage/identity/network/kernel — изолированы.
- `KroftConfig.node_id` уже parametric. `KroftApp` принимает `knowledge_snapshot`
  (per-instance path). `TcpEventBus` принимает `port`/`host`.
- **GAP:** нет ещё config-формата вида `api.host/port` + `storage.root` +
  `federation.enabled` как единый node-config (ТЗ §10). `ConfigLoader`
  (infrastructure/config_loader.py) читает `kroft_os.yaml`, но НЕ знает про
  per-node api/storage. Нужен адаптивный config (reuse ConfigLoader, расширить
  схему, не новый loader).
- `services/kroft_node_manager.py` (untracked sibling!) — возможно, уже начат
  node-manager. НАДО проверить перед реализацией (ТЗ §34: REUSE, не дублировать).

## STEP 7 — GAP MATRIX (итоговая таблица)

| Capability | Уже есть | Где | Можно reuse | GAP | Изменения |
|---|---|---|---|---|---|
| Runtime (daemon lifecycle) | partial | `cmd_serve` while-loop; `KroftApp` | `KroftApp` + `KROFT_OSServer` | daemon start/stop/recover/health | НОВЫЙ `runtime/` слой (тонкая обёртка) |
| CLI | ✅ | `cli/commands.py` | commands | CLI ≠ клиент Runtime | Переделать команды в клиенты HTTP/Runtime |
| Agent API (universal) | partial | `IAgent`, `KROFT_OSServer` `/api/agent/*` | `IAgent` + server routes | `IKroftAgentInterface` (status/search/query/resolve/audit/observe/memory/knowledge) | НОВЫЙ port `contracts/i_kroft_agent_interface.py` |
| Hermes bridge | ✅ (H0) | `bridges/kroft_bridge.py` | bridge | не знает о Runtime/serve | адаптировать bridge на HTTP/Runtime |
| Multi-instance | partial | `N0` доказал isolation; `KroftConfig.node_id` | `KroftApp` + `TcpEventBus.port` | per-node config (api/storage) | расширить ConfigLoader схему |
| Federation | ✅ | `federated_orchestrator`+`tcp_event_bus`+`crdt` | ВСЁ | knowledge-exchange path | ADAPT (не новая федерация) |
| KnowledgeEnvelope | ❌ | — | доменные типы есть | VO | НОВЫЙ `contracts/knowledge_envelope.py` |
| Trust | ✅ | `ReferenceTrustRegistry.current_trust` | registry | TRUST 0..5 policy | ADAPT (policy поверх current_trust) |
| Provenance | partial | `abstraction_sidecar` (ADR-028 Э2) | sidecar | transport при exchange | ADAPT (в envelope) |
| LOD | ✅ | `ResolutionLevel`+`ReferenceKnowledgeResolution` (ADR-028 Э1) | сервис | НЕ в federation path | ADAPT (в envelope) |
| Quarantine | ❌ | — | — | reject→store | НОВЫЙ механизм (storage quarantine) |
| Persistence | ✅ | `KnowledgeSnapshotStore` (9 слоёв) | store | per-node path | reuse (param) |
| HTTP API | ✅ | `KROFT_OSServer` | server | routes для resolve/audit/observe/memory/knowledge | ADAPT (добавить routes) |
| MCP | ❌ | — | — | (ТЗ §25: только если подходит) | НЕ делать (HTTP+CLI достаточно) |

## STEP 8 — TARGET ARCHITECTURE (кратко)

```
KROFT RUNTIME (runtime/kroft_runtime.py — НОВЫЙ тонкий слой)
   ├── load KroftConfig (node_id/api/storage/federation)
   ├── boot CognitiveKernel + Knowledge + Memory + SemanticIndex + Identity + Trust
   ├── start KROFT_OSServer (HTTP, reuse adapters/http_server.py)
   ├── start federation (TcpEventBus + ReferenceRemoteOrchestrator, reuse)
   ├── expose IKroftAgentInterface (НОВЫЙ port)
   └── health-check / stop / recover

CLI (cli/commands.py) → HTTP client → KROFT_RUNTIME → CognitiveKernel
Hermes (bridges/kroft_bridge.py) → HTTP/Runtime → KROFT_RUNTIME
Codex/Claude → HTTP API (universal) → KROFT_RUNTIME
```

## STEP 9 — MINIMAL IMPLEMENTATION PLAN (фазы, ждут GO)

- **PHASE 1 (Runtime):** `runtime/kroft_runtime.py` — тонкая обёртка над
  `KroftApp` + `KROFT_OSServer` + federation. start/stop/health. Reuse, не новое ядро.
- **PHASE 2 (Universal Interface):** `contracts/i_kroft_agent_interface.py`
  (IKroftAgentInterface) + реализация делегирует в существующие
  search/query/resolve/audit. Reuse ADR-028 ResolutionLevel.
- **PHASE 3 (Hermes):** адаптировать `bridges/kroft_bridge.py` на HTTP Runtime
  (или оставить in-process, но добавить server-path).
- **PHASE 4 (Multi-instance):** расширить ConfigLoader схему (api/storage/
  federation per node); `kroft serve --node kroft-01 --config nodes/kroft-01.yaml`.
- **PHASE 5 (Local Network):** `TcpEventBus` + `ReferenceRemoteOrchestrator`
  поверх существующего; discovery через seed_nodes.
- **PHASE 6 (KnowledgeEnvelope):** `contracts/knowledge_envelope.py` VO
  (reuse SemanticFact/Provenance/ResolutionLevel/KnowledgeOrigin).
- **PHASE 7 (Trust/Provenance/LOD/Quarantine):** envelope verify (signature/
  replay/trust/origin) + can_accept (ADR-028 Э4) + quarantine storage.
- **PHASE 8/9/10:** multi-node integration + load test (RTX 3060 / 32GB RAM).

**НОВЫЕ файлы (план):** `runtime/kroft_runtime.py`,
`contracts/i_kroft_agent_interface.py`, `contracts/knowledge_envelope.py`,
адаптация `cli/commands.py` + `adapters/http_server.py` (routes) + `bridges/`.
**ИЗМЕНЕНИЯ:** `infrastructure/config_loader.py` (schema), `kernel/federated_
orchestrator.py` (call can_accept), `composition/run_kroft.py` (wire runtime).

**ТЕСТЫ:** `tests/runtime/`, `tests/federation/test_knowledge_envelope.py`,
`tests/integration/test_multi_node.py`.

---

## STOP — ждём GO

По ТЗ §36/§41 код НЕ пишется до явного GO. Фазы выше — план, не имплементация.
Найденные sibling-файлы (`services/kroft_node_manager.py`, `contracts/text_processing.py`)
НУЖНО проверить перед PHASE 4 (возможно, дублируют план — ТЗ §34 REUSE).

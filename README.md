# KnowledgeOS v5

Autonomous Knowledge Operating System — hexagonal-core bootstrap.

## Architecture (Clean / Hexagonal)

```
contracts/        Ports (abstract interfaces): IService, IFileSystem,
                  IEventBus, ICapabilityRegistry, IGraphBuilder. stdlib only.
infrastructure/   Composition Root: DependencyContainer. Implements ports:
                  InMemoryEventBus, InMemoryGraphBuilder. -> contracts + stdlib.
kernel/           Microkernel: lifecycle FSM (UNINITIALIZED -> INITIALIZED
                  -> RUNNING -> STOPPED). Depends on contracts, infrastructure,
                  runtime. NEVER on adapters.
runtime/          RuntimeContext (state) + CapabilityRegistry.
adapters/         Concrete port implementations (LocalFileSystemAdapter).
services/         Application layer: VaultStreamCrawler (first IService).
                  -> contracts + stdlib ONLY. NEVER adapters/infrastructure.
tests/            TDD suite (pytest) + architecture gate.
```

Dependency axis (enforced by tests/test_architecture.py):
`contracts -> stdlib`; `infrastructure -> contracts`;
`adapters -> contracts`; `runtime -> contracts`;
`kernel -> contracts,infrastructure,runtime` (NEVER adapters);
`services -> contracts` (NEVER adapters/infrastructure).

## Lifecycle

```python
from infrastructure import DependencyContainer
from kernel import Kernel
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter

c = DependencyContainer()
c.register_instance("ICapabilityRegistry", CapabilityRegistry())
c.register_instance("IFileSystem", LocalFileSystemAdapter("./data"))
k = Kernel(c)
k.initialize()   # -> INITIALIZED (resolves core capabilities)
k.start()        # -> RUNNING
k.stop()         # -> STOPPED
```

## Stage 10 — VaultStreamCrawler (first application IService)

`services/vault_stream_crawler.py` → `VaultStreamCrawler` implements
`contracts.IService`. It walks a vault via the `IFileSystem` port, finds
`.md` files (recursively), extracts `[[wiki-links]]` and `#tags` with regex,
builds an in-memory knowledge graph via the `IGraphBuilder` port, and publishes
`crawl.started` / `crawl.finished` events through `IEventBus`.

The crawler proves the hexagonal stack end-to-end:
**application service → ports → adapters** with zero direct coupling:
`VaultStreamCrawler` depends only on `contracts.*` + stdlib; the real
`LocalFileSystemAdapter` and `InMemoryGraphBuilder` are injected through the DI
Container (see `tests/test_services.py::test_e2e_full_assembly`).

New port: `contracts.IGraphBuilder` (add_node / add_edge / get_graph /
get_neighbors / clear). Implemented by `infrastructure.InMemoryGraphBuilder`
(thread/async-safe via `threading.Lock`, `get_graph()` returns a deep copy).

### HONEST LIMITATIONS (Stage 10)
- **Regex-only markdown parsing:** `[[link]]` and `#tag` via simple regex.
  No YAML frontmatter parsing, no code-fence awareness (links inside fenced
  code blocks are extracted too), no nested/transclusion handling.
- **Markdown only:** only `.md` files are crawled. No `.canvas`, `.pdf`,
  images, or other Obsidian artifacts.
- **In-memory graph:** `InMemoryGraphBuilder` holds the whole graph in RAM.
  No persistence, no incremental update — re-crawl rebuilds from scratch.
- **Single vault:** one root path per crawl. No multi-vault federation.
- **No content indexing:** the crawler stores node labels + extracted tags in
  metadata but does NOT index full file text for search.
- **No dedup of wiki-link targets:** a `[[MissingNote]]` with no backing file
  becomes a node with no inbound graph edge from the filesystem (recorded as a
  dangling reference) — graph still contains the node, edges only exist where
  a source file was actually crawled.

## STAGE 11 — Graph Query Engine (second application IService)

`services/graph_query_engine.py` → `GraphQueryEngine` implements
`contracts.IGraphQuery`. It is a PURE READ-ONLY engine: every query pulls a
fresh deep-copy snapshot via `IGraphBuilder.get_graph()` and never mutates the
graph (safe to run while VaultStreamCrawler is still writing).

New port: `contracts.IGraphQuery` (inherits IService) — `backlinks`,
`forward_links`, `nodes_by_tag`, `orphan_nodes`, `path` (BFS shortest path
with `max_depth` guard), `cluster_by_tag`, `stats`.

### Service-to-service via shared port (hexagonal proof)
`VaultStreamCrawler` WRITES to a shared `IGraphBuilder`; `GraphQueryEngine`
READS from the SAME instance. The two services never import each other — they
are coupled only through ports. `tests/test_graph_query_e2e.py` proves the
crawler can build a graph and the query engine answers correctly against it,
while `tests/test_architecture.py::test_services_do_not_cross_import` enforces
that no service module imports another service module.

### HONEST LIMITATIONS (Stage 11)
- **In-memory graph only:** no persistence — on restart the graph is empty.
  The query engine has nothing to query until a crawler rebuilds it.
- **Structural, not semantic:** queries are link/tag topology only. No LLM,
  no embeddings, no fuzzy/semantic search. `path()` matches exact node IDs.
- **Exact-match path:** BFS over exact `from`/`to` IDs. A dangling wiki-link
  target (`[[MissingNote]]`) is a real node only if the crawler added it as a
  node; otherwise `path()` to it returns None.
- **No pagination:** `nodes_by_tag` / `cluster_by_tag` return full lists.
- **No caching:** every query re-scans the snapshot (O(n) or O(edges) for most
  operations; `path()` is O(V+E) BFS).
- **No transactions:** the crawler may mutate the live graph mid-query; the
  engine operates on a point-in-time snapshot, so results reflect the graph
  state at query start (no partial-update visibility).
- **orphan_nodes semantics:** a node is an "orphan" only if it has ZERO edges
  (in-degree 0 AND out-degree 0). A node that links out but is never linked to
  (e.g. the vault "hub") is NOT counted as orphan. (Documented divergence from
  the prose "no back-links" definition — the Stage-11 test suite defines the
  contract as zero-degree.)

## STAGE 12 — Graph Persistence & Recovery

`IGraphBuilder` gained `snapshot(fs, path)` / `restore(fs, path)` (Stage 12).
`InMemoryGraphBuilder` persists the whole graph as a single JSON file via the
`IFileSystem` port. The **Kernel lifecycle now recovers the graph on
`initialize()` and persists it on `stop()`** — closing the "in-memory only,
lost on restart" limitation. On successful restore, the kernel emits a
`GraphRestored` event; on snapshot, a `GraphSnapshotted` event (both via the
wired `IEventBus`).

Also fixed (Stage 12, cross-platform): `VaultStreamCrawler` now normalizes path
separators to `/` for all node ids and edge endpoints, so the graph is
identical on Windows (`vault\A.md`) and POSIX (`vault/A.md`) — backlinks/
queries match regardless of OS.

### HONEST LIMITATIONS (Stage 12)
- **JSON snapshot, not binary:** human-readable but slow on large graphs
  (full re-serialize / re-parse every cycle).
- **No incremental save:** always a FULL snapshot (O(n + m) nodes + edges).
- **No snapshot versioning:** a single file (`data/graph_snapshot.json`) is
  overwritten on every Kernel stop — the previous state is lost.
- **No periodic autosave:** persistence happens ONLY on `Kernel.stop()`. A
  crash between starts leaves the last good snapshot (or none).
- **Corrupt JSON → silent fallback:** `restore()` returns False on missing or
  unparseable files and leaves the graph EMPTY (no exception, no recovery).
- **No compression:** raw JSON text on disk.
- **No schema migration:** a snapshot written by an older graph schema will
  fail to restore (returns False) if fields are incompatible.

## STAGE 13 — CLI Entrypoint (продукт, а не библиотека)

Новый слой `cli/` + корневой `main.py` превращают ядро в запускаемый продукт:
`python main.py <command>`. Каждая команда сама собирает DI-контейнер и гонит
lifecycle ядра `init -> start -> stop`.

### Команды

```bash
python main.py init   --vault PATH          # создать <vault>/ и <vault>/data/
python main.py crawl  --vault PATH          # просканировать Vault, построить граф, вывести stats
python main.py query  --vault PATH --backlinks ID   # узлы, ссылающиеся на ID
python main.py query  --vault PATH --path FROM TO   # кратчайший путь (BFS)
python main.py query  --vault PATH --orphans         # изолированные узлы
python main.py query  --vault PATH --tags TAG        # узлы с тегом
python main.py status --vault PATH          # состояние ядра + размер графа
python main.py stop   --vault PATH          # graceful (нет демона — honest no-op / pid-file cleanup)
```

### NODE-ID contract (важно для query)

`LocalFileSystemAdapter(base=vault_path)` отдаёт список файлов **относительно
корня vault**, поэтому node-id в графе — `A.md`, `sub/B.md` (без префикса пути
к vault). Wiki-ссылки резолвятся относительно vault root. **В `query` передаются
голые id** (`C.md`), а не `vault/C.md`.

### Пример

```bash
python main.py init --vault ./my-vault
# положить A.md ("hub [[B.md]] [[C.md]]"), B.md, C.md в ./my-vault
python main.py crawl --vault ./my-vault
# -> {"files_scanned": 3, "nodes": 3, "edges": 2}
python main.py query --vault ./my-vault --backlinks "C.md"
# -> ["A.md"]
python main.py status --vault ./my-vault
# -> {"state": "INITIALIZED", "graph_nodes": 3, "graph_edges": 2}
```

### HONEST LIMITATIONS (Stage 13)
- **Нет демон-режима:** каждая команда заново поднимает Kernel (init→start→stop).
  Между вызовами состояние держится только в snapshot-файле (`data/graph_snapshot.json`
  внутри vault, пишется при `stop()`/`crawl`-завершении).
- **Нет конфиг-файла:** все параметры — только через CLI args (`--vault`).
- **Нет логирования в файл:** только stdout/stderr (`json.dumps` результатов).
- **Нет интерактивного REPL:** только batch-команды.
- **Нет обработки SIGINT:** `main.py` не ловит KeyboardInterrupt — прерывание
  может оставить граф без свежего snapshot (сохраняется последний успешный).
- **PID-файл не создаётся:** нет защиты от double-run; `stop` — honest no-op,
  если нет pid-файла.
- **Snapshot — vault-relative:** `data/graph_snapshot.json` пишется через
  `IFileSystem` (base=vault), поэтому восстановление cwd-независимо, но
  требует того же `--vault` при перезапуске.

## Test gates

```
pytest tests/            # unit + e2e + arch gate (109 tests, all green)
python -c "import contracts, infrastructure, kernel, runtime, adapters, services, cli"
python main.py --help   # exit 0
```

## HONEST LIMITATIONS (Stage 7.8)

- **No real concurrency:** FSM and container are GIL-atomic for single
  operations but ship NO explicit lock (except GraphBuilder's lock). Not
  proven safe under load.
- **FileSystemAdapter:** local disk only. No S3 / SSH / network backends.
- **DI Container:** manual registration. No module auto-scanning.
- **No persistence for kernel state:** Kernel starts from a clean slate on
  every restart (wired capabilities live only in memory). EventBus history is
  the only thing persisted (Stage 9, JSONL).

## ЭТАП 9 — EventBus Persistence (JSONL via IFileSystem)

`InMemoryEventBus(store=IFileSystem, base_path="events")` appends every
published event to a human-readable JSONL file:
`{base_path}/{topic}/{YYYY-MM-DD}.jsonl`. `get_history(topic)` merges the
on-disk log with the in-memory buffer (survives a Kernel restart). `clear_history()`
removes the `base_path/` tree. `IFileSystem` port gained `append()` and `delete()`.

### HONEST LIMITATIONS (Stage 9)
- **JSONL, not SQLite:** human-readable, but not indexed/queryable.
- **Append-only, no rotation:** topic files grow unbounded.
- **History read = full scan** of all topic files (O(n), not O(1)).
- **No transactional guarantee:** a crash between publish and write loses that event.
- **No compression/retention:** raw text, forever.
- **Merge dedup is content-based:** a disk-replicated event and the in-memory
  mirror of the SAME event (identical JSON content) collapse to one; two
  distinct events that happen to share a sub-microsecond timestamp do NOT
  collapse (keyed by full record content, `json.dumps(..., sort_keys=True)`).

- **Ports are independent ABCs:** IFileSystem / IEventBus / ICapabilityRegistry
  do NOT inherit IService (IService is the base for service components only).
  `IGraphBuilder` (Stage 10) DOES inherit IService per its spec.

## ETAП 8 — IEventBus (in-memory async)

`infrastructure/eventbus.py` → `InMemoryEventBus` implements `contracts.IEventBus`.
Wired into Kernel lifecycle via DI Container (kernel resolves `IEventBus` in
`initialize()`; emits `kernel.started` / `kernel.stopped` in `start()` / `stop()`).

### HONEST LIMITATIONS (Stage 8)
- **In-memory only (unless store is given):** without `store=`, the event log
  is lost on Kernel restart. With `store=`, JSONL persistence applies (Stage 9).
- **No distributed event bus:** single process, not a cluster.
- **At-most-once delivery:** if a handler raises, the event is lost for that
  handler (but isolated — other handlers still run).
- **No backpressure:** unlimited subscriber queues.
- **Error isolation:** errors are logged to stdout (print), not to a structured log.
- **Async model:** sync handlers run via `asyncio.to_thread`; `publish_sync` wraps
  async handlers by best-effort (creates/borrows an event loop).

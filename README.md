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

## Test gates

```
pytest tests/            # unit + e2e + arch gate (69 tests, all green)
python -c "import contracts, infrastructure, kernel, runtime, adapters, services"
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

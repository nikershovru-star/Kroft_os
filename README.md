# KnowledgeOS v5

Autonomous Knowledge Operating System — hexagonal-core bootstrap.

## Architecture (Clean / Hexagonal)

```
contracts/        Ports (abstract interfaces): IService, IFileSystem,
                  IEventBus, ICapabilityRegistry. stdlib only.
infrastructure/   Composition Root: DependencyContainer.
kernel/           Microkernel: lifecycle FSM (UNINITIALIZED -> INITIALIZED
                  -> RUNNING -> STOPPED). Depends on contracts, infrastructure,
                  runtime. NEVER on adapters.
runtime/          RuntimeContext (state) + CapabilityRegistry.
adapters/         Concrete port implementations (LocalFileSystemAdapter).
tests/            TDD suite (pytest) + architecture gate.
```

Dependency axis (enforced by tests/test_architecture.py):
`adapters -> contracts`; `kernel -> contracts,infrastructure,runtime`;
`runtime -> contracts`; `infrastructure -> contracts`; `contracts -> stdlib`.

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

## Test gates

```
pytest tests/            # unit + e2e + arch gate (>20 tests, all green)
python -c "import contracts, infrastructure, kernel, runtime, adapters"
```

## HONEST LIMITATIONS (Stage 7.8)

- **No real concurrency:** FSM and container are GIL-atomic for single
  operations but ship NO explicit lock. Not proven safe under load.
- **FileSystemAdapter:** local disk only. No S3 / SSH / network backends.
- **DI Container:** manual registration. No module auto-scanning.
- **EventBus:** port defined (contracts.IEventBus) but NOT implemented yet.
  No event-sourcing runtime in this stage.
- **No persistence:** Kernel starts from a clean slate on every restart.
  Wired capabilities live only in memory.
- **Async model:** sync handlers run via `asyncio.to_thread`; `publish_sync` wraps
  async handlers by best-effort (creates/borrows an event loop).

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

- **Ports are independent ABCs:** IFileSystem / IEventBus / ICapabilityRegistry
  do NOT inherit IService (IService is the base for service components only).
  The spec item "all ports inherit IService" was interpreted as "all ports are
  abstract base contracts" — see tests/test_contracts.py design note.

## ETAП 8 — IEventBus (in-memory async)

`infrastructure/eventbus.py` → `InMemoryEventBus` implements `contracts.IEventBus`.
Wired into Kernel lifecycle via DI Container (kernel resolves `IEventBus` in
`initialize()`; emits `kernel.started` / `kernel.stopped` in `start()` / `stop()`).

### HONEST LIMITATIONS (Stage 8)
- **In-memory only:** the event log is lost on Kernel restart. The optional
  `store: IFileSystem` parameter is accepted for DI symmetry but persistence is
  NOT implemented in this stage.
- **No distributed event bus:** single process, not a cluster.
- **At-most-once delivery:** if a handler raises, the event is lost for that
  handler (but isolated — other handlers still run).
- **No backpressure:** unlimited subscriber queues.
- **Error isolation:** errors are logged to stdout (print), not to a structured log.
- **Async model:** sync handlers run via `asyncio.to_thread`; `publish_sync` wraps
  async handlers by best-effort (creates/borrows an event loop).

- **Ports are independent ABCs:** IFileSystem / IEventBus / ICapabilityRegistry
  do NOT inherit IService (IService is the base for service components only).
  The spec item "all ports inherit IService" was interpreted as "all ports are
  abstract base contracts" — see tests/test_contracts.py design note.

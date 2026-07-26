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
- **Ports are independent ABCs:** IFileSystem / IEventBus / ICapabilityRegistry
  do NOT inherit IService (IService is the base for service components only).
  The spec item "all ports inherit IService" was interpreted as "all ports are
  abstract base contracts" — see tests/test_contracts.py design note.

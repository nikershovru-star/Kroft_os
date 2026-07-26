# Changelog

## v5.0.0 (Stages 1-7)
- Hexagonal bootstrap: contracts, infrastructure (DI), kernel FSM, runtime, adapters
- TDD suite: 37 tests across 6 files, all green
- Architecture dependency-axis gate (static AST)
- HONEST LIMITATIONS documented in README.md

## v5.0.0 (Stage 8)
- IEventBus in-memory async implementation (InMemoryEventBus)
- Kernel lifecycle integration: emits kernel.started / kernel.stopped
- 13 new tests (eventbus unit + integration), full suite now 50 green
- HONEST LIMITATIONS documented (in-memory, at-most-once, no persistence)

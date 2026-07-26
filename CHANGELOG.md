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

## v5.0.0 (Stage 9)
- EventBus JSONL persistence via IFileSystem (append-only, daily files)
- IFileSystem port extended: append() + delete(); LocalFileSystemAdapter impl
- get_history(topic) merges disk + memory (survives restart)
- 8 new persistence tests; full suite now 58 green
- HONEST LIMITATIONS: JSONL-not-SQLite, no rotation, O(n) scan, no txn

## v5.0.0 (Stage 10)
- NEW application layer `services/`: first IService — `VaultStreamCrawler`.
- NEW port `contracts.IGraphBuilder` (inherits IService) + impl
  `infrastructure.InMemoryGraphBuilder` (lock-safe, deep-copy get_graph).
- VaultStreamCrawler: recursive .md walk via IFileSystem, regex extraction of
  `[[wiki-links]]` + `#tags`, in-memory graph build, emits crawl.started /
  crawl.finished via IEventBus. Hexagonal E2E proven (service -> ports -> adapters).
- 10 new service tests; full suite now 69 green. Arch Gate 2/2 green.
- HONEST LIMITATIONS: regex-only markdown, .md only, in-memory graph, no
  incremental, single vault, no content indexing.
- EventBus merge dedup hardened: keyed by full record content (not topic+timestamp)
  to avoid collapsing distinct sub-microsecond events (fixes intermittent
  test_history_merge_memory_and_disk).

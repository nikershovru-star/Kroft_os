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

## v5.0.0 (Stage 11)
- NEW application service `services.GraphQueryEngine` (2nd IService) implementing
  `contracts.IGraphQuery` (backlinks / forward_links / nodes_by_tag / orphan_nodes
  / path[BFS] / cluster_by_tag / stats). Pure read-only, snapshot-on-read.
- NEW port `contracts.IGraphQuery` (inherits IService).
- Service-to-service proof: VaultStreamCrawler WRITES + GraphQueryEngine READS the
  same shared IGraphBuilder (no direct cross-service imports). E2E test + new arch
  gate `test_services_do_not_cross_import` enforce the contract.
- 14 new tests (10 unit + 4 e2e); full suite now 85 green. Arch Gate 3/3 green.
- HONEST LIMITATIONS: in-memory graph only, structural (not semantic) queries,
  exact-match BFS path, no pagination, no caching, no transactions, orphan = zero-degree.

## v5.0.0 (Stage 12)
- IGraphBuilder gained `snapshot(fs, path)` / `restore(fs, path)` (full JSON
  persistence via IFileSystem). InMemoryGraphBuilder impl (thread-safe, lock).
- Kernel lifecycle integration: graph RESTORED on initialize() (emits
  GraphRestored on success), SNAPSHOTTED on stop() (emits GraphSnapshotted).
  Closes the "in-memory only — lost on restart" limitation.
- Crawler path-normalization fix (cross-platform): node ids / edge endpoints use
  `/` separators on every OS, so backlinks/queries match on Windows too.
- 12 new tests (8 persistence + 4 e2e); full suite now 97 green. Arch Gate 3/3.
- HONEST LIMITATIONS: JSON not binary, full (no incremental), single file
  (no versioning), stop-only autosave, corrupt JSON silent fallback, no
  compression, no schema migration.

## v5.0.0 (Stage 13)
- NEW `cli/` application layer (product entrypoint) + root `main.py`.
  `python main.py <command>` is now the runnable interface to the kernel:
  `init` / `crawl` / `query` / `status` / `stop`.
- `cli/parser.py`: argparse with subcommands init, crawl, query, status, stop.
  query variants: `--backlinks ID`, `--path FROM TO`, `--orphans`, `--tags TAG`.
- `cli/commands.py`: each command owns its Kernel lifecycle (build DI container
  -> initialize -> start -> run -> stop). Composition root lives ONLY in
  `main.build_container` (wires LocalFileSystemAdapter + InMemoryEventBus +
  InMemoryGraphBuilder + CapabilityRegistry + VaultStreamCrawler +
  GraphQueryEngine). Adapters are NEVER imported by cli/commands.py (enforced
  by test_cli_arch_no_adapters_import).
- NODE-ID CONTRACT (fixed during Stage 13): with LocalFileSystemAdapter
  (base=vault_path), node-ids are RELATIVE TO THE VAULT ROOT (e.g. "A.md",
  "sub/B.md"); wiki-links resolve relative to vault root. Query args use bare
  ids ("C.md"), NOT "vault/C.md".
- 12 new tests (8 unit + 4 e2e); full suite now 109 green. Arch Gate 4/4
  (cli allowed: {contracts, infrastructure, kernel, services}).
- HONEST LIMITATIONS (Stage 13): see README "HONEST LIMITATIONS (Stage 13)".

## v5.0.0 (Stage 14)
- Periodic Autosave & Watchdog: Kernel gains `autosave_interval_sec`. On
  start() (if interval > 0 AND IGraphBuilder + IFileSystem wired) launches a
  background daemon-thread asyncio loop running `_autosave_loop()` that calls
  `graph.snapshot()` every N seconds and emits `GraphAutosaved {timestamp}`.
- `Kernel.stop()` is now IDEMPOTENT (re-call on STOPPED/UNINITIALIZED is a
  safe no-op) — required so the atexit hook cannot raise on a kernel already
  torn down.
- atexit hook in cli/commands.py: `atexit.register(lambda: k.stop())` after
  k.start() guarantees a final snapshot on graceful exit (sys.exit /
  KeyboardInterrupt / SIGTERM).
- CLI: `--autosave SECONDS` added to `crawl` and `status` (default 60; 0 off).
  Passed into Kernel via main.build_container wiring.
- No new ports / no new layer (kernel + cli + main only). Arch gate unchanged.
- 6 new tests (test_autosave.py); full suite now 115 green. Arch Gate 4/4.
- HONEST LIMITATIONS (Stage 14): graph-snapshot only (not full Kernel state);
  wall-clock injectable interval (not exact real-time); atexit does NOT catch
  SIGKILL; no backoff on write failure (silent skip); still full JSON snapshot
  (no differential); watchdog is a daemon thread (no final tick on hard kill).

## v5.0.0 (Stage 15)
- Config File & Profiles: closed Stage-13 limitation "no config file -- all
  params via CLI args". New `infrastructure/config_loader.py` (ConfigLoader)
  reads `knowledgeos.yaml` (preferred) or `.json` (fallback) from the vault
  root via the IFileSystem port.
- `ConfigLoader.load(vault_path, fs)` -> dict; missing/broken file -> {} (never
  raises). `merge_with_cli(cli_args, config)` -> dict with priority
  CLI arg (if not None) > config > hardcoded default for `autosave_interval`
  (60.0) and `vault`. Unknown top-level keys -> warnings.warn (not an error).
- YAML via optional `pyyaml`; if absent, JSON fallback. ConfigLoader depends
  only on contracts.IFileSystem + stdlib (json, warnings, typing) -> passes
  the arch gate (infrastructure layer, no adapters/services deps).
- CLI: `--vault` and `--autosave` made optional (default None). Every command
  resolves IFileSystem from the container, loads config, merges with CLI args.
  `init` writes a knowledgeos.yaml template (vault, autosave_interval, features).
  `crawl`/`status`/`query` pass `effective["autosave_interval"]` into Kernel.
  Config stays at CLI level (Kernel receives resolved params, not the loader).
- 10 new tests (test_config_loader.py x6, test_cli_config.py x4); full suite
  now 125 green. Arch Gate 4/4.
- HONEST LIMITATIONS (Stage 15): pyyaml optional (JSON fallback); no schema
  validation (unknown keys warned, ignored); no hot-reload (read once per
  command); no env-var override (CLI + YAML only); `vault` in YAML is relative
  to the YAML location; flat config, no sections/profiles.

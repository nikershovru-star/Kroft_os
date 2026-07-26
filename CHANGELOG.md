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

## v5.0.0 (Stage 16)
- Interactive REPL: closed Stage-13 limitation "no interactive REPL -- only
  batch commands". NEW `cli/repl.py` -> `KnowledgeOSRepl`: a long-running,
  line-oriented REPL loop. The Kernel (and the DI container + shared graph)
  is created ONCE by `cmd_repl` and lives for the ENTIRE session -- it is NOT
  rebuilt per command (proven by tests/test_repl.py::test_repl_kernel_lifecycle).
- Commands: `crawl` (VaultStreamCrawler.crawl + stats), `query backlinks ID`
  / `query path FROM TO` / `query orphans` / `query tags TAG` (GraphQueryEngine,
  JSON), `status` (Kernel state + graph size), `save` (force snapshot),
  `exit`/`quit` (graceful shutdown), `help`.
- NEW `Kernel.save()` public method (Stage 16): best-effort `graph.snapshot()`
  + `GraphSnapshotted` emit WHILE RUNNING (does not change lifecycle state, so
  the REPL keeps serving). Backward-compatible (thin wrapper over the existing
  `_try_snapshot_graph` used by stop()).
- Graceful KeyboardInterrupt (Ctrl+C): caught at the prompt AND during a
  command -> `_handle_sigint()` does save + stop, then exits cleanly (no lost
  data). `run()` also guarantees `Kernel.stop()` on every exit path.
- readline history (optional import): in-memory only -- no history file is
  ever read/written, so command history does NOT persist across sessions.
- CLI: `main.py repl --vault PATH` subcommand added (parser + cmd_repl +
  main dispatch). `--vault` optional (falls back to knowledgeos.yaml).
- 8 new tests (tests/test_repl.py): crawl / query-backlinks / status / save /
  help / unknown-command / keyboard-interrupt / kernel-lifecycle. Full suite
  now 133 green. Arch Gate green (cli allowed: {contracts, infrastructure,
  kernel, services}; intra-package cli->cli import is NOT a cross-layer
  violation -- gate updated to skip same-package imports).
- HONEST LIMITATIONS (Stage 16): see README "HONEST LIMITATIONS (Stage 16)".

## v5.0.0 (Stage 17)
- Incremental Crawl: closed Stage-10 limitation "no incremental crawl --
  always full rescan". NEW `services/incremental_tracker.py` ->
  `CrawlStateTracker(fs, state_path=".crawl_state.json")`: tracks per-file
  mtimes in a JSON state file (via the IFileSystem port), detects
  changed/new/deleted `.md` files and updates the graph DIFFERENTIALLY --
  no full rescan, no `graph.clear()`.
  - `load_state()` -> {} on missing/corrupt JSON (never raises);
    `save_state(mtimes)`; `get_changed_files(vault)` -> (changed_or_new,
    deleted); `apply_to_graph(graph, deleted)` -> remove_node per file.
- NEW port method `IGraphBuilder.remove_node(node_id) -> bool` (abstract);
  `InMemoryGraphBuilder` implementation drops the node and every edge where
  it is `from` or `to` (True if the node existed). O(edges) linear scan --
  honest limitation. snapshot/restore untouched (test_graph_persistence
  still green); test_contracts asserts remove_node in __abstractmethods__.
- `VaultStreamCrawler(..., tracker=None)`: new optional param (duck-typed
  Optional[Any] -- the services cross-import gate forbids importing the
  sibling service; wiring happens in the DI composition root).
  - tracker set: `crawl()` scans ONLY changed files; deleted files ->
    remove_node; second crawl with zero changes -> instant
    `{"status": "up_to_date", "files_scanned": 0, ...}`; fresh mtimes saved
    after every non-up_to_date crawl. Incoming edges from unchanged
    neighbors are preserved across a changed-file rescan (collision caught
    in smoke: remove_node would otherwise drop edges nobody rescans).
  - tracker=None: ZERO REGRESSION -- Stage-10 behavior (clear + full
    rescan), no state file (test_zero_regression_without_tracker).
- DI: `main.build_container` registers `CrawlStateTracker` and injects it
  into `VaultStreamCrawler` -- both batch `crawl` and the REPL `crawl`
  command are incremental now (second crawl in a row -> up_to_date).
- 8 new tests (tests/test_incremental.py): empty/corrupt state, new file,
  modified file (os.utime-forced mtime bump), deleted file, unchanged
  ignored, up_to_date fast path, incremental merge (graph correctness incl.
  edges + refreshed tag meta + differential delete), zero regression.
  Full suite now 141 green; Arch Gate green (tracker in services/, imports
  contracts + stdlib only).
- HONEST LIMITATIONS (Stage 17): see README "HONEST LIMITATIONS (Stage 17)"
  (mtime not content-hash; no rename detection; visible state file in vault
  root; no concurrent-crawl protection; symlink mtime blind spot;
  remove_node O(edges)).

## v5.0.0 (Stage 18)
- Content Indexing & Full-Text Search: closed Stage-10 limitation "no
  content indexing -- full file text is not searchable". NEW
  `services/content_index.py` -> `ContentIndex`: in-memory inverted index
  (word -> set[node_id] posting lists) + reverse map (node_id ->
  Counter(word)) for O(doc-terms) removal and match-frequency sorting.
  - Tokenization: regex \w+, lowercased, min 2 chars. No stemming, no
    stop-words (honest limitations).
  - `index_file(node_id, text)`: REPLACE semantics (old terms dropped
    first) -- reindex never leaves stale postings.
  - `search(query)`: AND-logic posting-list intersection; sorted by total
    match frequency desc, then node_id (deterministic). Empty query or any
    missing term -> [].
  - `remove_file(node_id)`: prunes empty posting lists (stats stay honest).
  - `get_stats()`: {"terms": N, "documents": M}.
- `VaultStreamCrawler(..., index=None)`: new optional duck-typed param.
  Full crawl indexes every scanned file; incremental path: changed ->
  remove_file + reindex, deleted -> remove_file. index=None -> ZERO
  REGRESSION (Stage-17 behavior, nothing indexed).
- `GraphQueryEngine(..., index=None)`: new `search(query)` method -- proxy
  to ContentIndex.search(); [] when no index wired (zero regression).
- DI: `ContentIndex` singleton in `main.build_container`; crawler WRITES,
  query engine READS the same instance (same convention as IGraphBuilder).
- CLI: NEW `main.py search QUERY --vault PATH` subcommand; REPL: NEW
  `search QUERY` command (+ help entry).
- NEW `ensure_index(container, vault)` in cli/repl.py -- integration
  collision caught: the index is RAM-only and the incremental tracker's
  up_to_date fast path skips scanning entirely, so a fresh process would
  search an empty index. cmd_search/cmd_repl rebuild an empty index by
  re-reading .md files via container ports (graph + crawl state untouched).
- 8 new tests (tests/test_content_index.py): index adds terms / AND logic /
  case-insensitive / remove clears / no match / stats / incremental
  reindex (stale terms gone, deleted files leave index) / zero regression
  without index. Full suite now 149 green; Arch Gate green (content_index
  in services/, stdlib-only imports).
- HONEST LIMITATIONS (Stage 18): see README "HONEST LIMITATIONS (Stage 18)"
  (\w+ only, no stemming; no stop-words; no phrase search; no TF-IDF; RAM
  only -- rebuilt per process; no fuzzy match).

## v5.0.0 (Stage 19)
- `contracts.ISnapshotable` (Protocol, runtime_checkable): `snapshot() -> dict`
  / `restore(data) -> None`. Lets the Kernel decide "does this service
  implement snapshot?" without importing the concrete class.
- `services.ContentIndex` now implements `ISnapshotable`: `snapshot()` returns a
  plain-dict (lists, not sets — JSON-safe); `restore()` does a full state
  replacement O(terms + doc_terms). Single new import: `contracts.snapshotable`
  (axis-clean: services -> contracts + stdlib only).
- `infrastructure.SnapshotStore`: atomic (tmp + rename via `IFileSystem.rename`)
  JSON read/write of an arbitrary plain-dict payload. Does NOT know the schema
  — the Kernel builds the composite dict.
- `contracts.IFileSystem` gains `rename(src, dst)` (os.replace semantics,
  atomic on POSIX+Win); implemented in `LocalFileSystemAdapter` and both test
  MockFS ports. Graph `snapshot()` now also writes atomically (tmp + rename).
- `Kernel` persists the index: `save()` / `stop()` / autosave call
  `_try_snapshot_index()` -> `SnapshotStore.save({"version": 2, "index": ...})`
  at `data/index_snapshot.json`. Graph still persisted separately by
  `IGraphBuilder` (no composite file — preserves Stage-12 graph tests).
- `Kernel.initialize()` restores the index from the snapshot via
  `_try_restore_index()` using `runtime_checkable ISnapshotable` — the kernel
  never imports `ContentIndex`. Cold CLI/REPL start is now O(1) (no vault
  re-read); the Stage-18 `ensure_index()` RAM-rebuild was REMOVED.
- Backward compatible: a v1 snapshot (no `index` key) loads with an empty
  index; `GraphQueryEngine(..., index=None)` still returns [] for search.
- 9 new tests (tests/test_index_persistence.py): snapshot round-trip / atomic
  write / store load / ISnapshotable contract / Kernel restores index from v2
  snapshot / Kernel saves v2 snapshot / v1 backward-compat / remove-after-restore
  / engine-without-index regression. Full suite now 158 green; Arch Gate green.
- HONEST LIMITATIONS (Stage 19): see README "HONEST LIMITATIONS (Stage 19)"
  (snapshot not crash-atomic vs FS; no delta-snapshot — whole JSON rewritten on
  each save; index snapshot separate from graph snapshot file).

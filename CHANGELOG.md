# Changelog
## v5.0.0 (Stage 34)
- Multi-Step Agent Plans: `find X and open the best` -> sequential tool execution.
- Cyrillic support: `найди`, `открой`, `сделай скриншот`, `экспортируй граф в dot`, etc.
- Fail-fast execution: error in step N stops the chain, returns partial plan.
- Backward-compatible single-step JSON format preserved (flat {ok,command,tool,result}).
- 9 new tests (`test_agent.py` 16->actually 17 incl. working fail-fast test); suite 279 -> 288 passed.
- HONEST LIMITATIONS: fail-fast only (no rollback); regex not NLP; mixed-language limited.

## v5.0.0 (Stage 33)
- Hermes Agent: `AgentService` -- rule-based natural language intent router.
- `ToolRegistry` -- unified tool registration (search, open, analytics, export, desktop).
- CLI `agent "COMMAND" [--dry-run]`, REPL `agent`, HTTP `POST /api/agent/execute`.
- Web UI: Agent input + Execute/Dry Run buttons.
- 8 tests (`test_agent.py`); suite 271 -> 279 passed.
- HONEST LIMITATIONS: regex/English-only; no LLM; single-tool calls; dry_run via json body.

## v5.0.0 (Stage 32)
- Desktop Orchestrator: `DesktopOrchestrator` bridges `GraphQueryEngine` + `DesktopService`.
- `open_note(query, top_k=1)` -- hybrid-search then open top result in OS default app.
- `list_notes(query, top_k=5)` -- return ranked candidates without opening.
- CLI `desktop open_note QUERY` / `desktop list_notes QUERY`, REPL, HTTP POST
  `/api/desktop/open_note` + `/api/desktop/list_notes`.
- Web UI: Open Note / List Notes input + buttons.
- 6 tests (`test_desktop_orchestrator.py`); suite 265 -> 271 passed.
- HONEST LIMITATIONS: os.path.join may double-prefix absolute nid (fallback to nid);
  real open needs interactive session + PyAutoGUIAdapter; no preview before open.

## v5.0.0 (Stage 31)
- Desktop Automation: `IDesktop` port + `MockDesktopAdapter` (default, no-op) +
  `PyAutoGUIAdapter` (opt-in, lazy import pyautogui/PIL).
- `DesktopService` -- high-level orchestration (click, type, screenshot, cursor, open).
  Unwired `IDesktop` -> RuntimeError (no silent fail).
- CLI `desktop ACTION [ARGS]`, REPL `desktop`, HTTP `POST /api/desktop/click`,
  `POST /api/desktop/type`, `GET /api/desktop/screenshot` (raw PNG), `GET /api/desktop/cursor`.
- Web UI: Desktop control buttons (Click, Screenshot, Cursor).
- 8 tests (`test_desktop.py`); suite 257 -> 263 passed.
- HONEST LIMITATIONS: PyAutoGUI needs `pip install pyautogui pillow` + interactive
  session; open_app is platform-specific; screenshots are raw PNG; no sandbox.

## v5.0.0 (Stage 30)
- Hybrid Search: RRF fusion (k=60) of lexical (ContentIndex) + semantic (SemanticIndex).
- `GraphQueryEngine.hybrid_search(query, top_k=10)` -- zero regression (degrades to
  lexical-only / semantic-only / empty when engines are unwired).
- CLI `hybrid QUERY [--top-k N]`, REPL `hybrid`, HTTP `GET /api/hybrid?q=&top_k=`.
- Web UI: search-mode select now Lexical / Semantic / Hybrid.
- 8 tests (`test_hybrid_search.py`); suite 249 -> 257 passed.
- HONEST LIMITATIONS: RRF uses ranks not absolute scores; Mock embedding is not
  real semantics (OpenAI/sentence-transformers out of arch gate changes only candidates).


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

## v5.0.0 (Stage 20)
- `ContentIndex.suggest(prefix, limit)` — prefix autocomplete via `bisect`
  over a maintained sorted term list. O(log V + k), V = vocabulary size.
- `ContentIndex.fuzzy_search(query, cutoff=0.6)` — fuzzy AND-search via
  `difflib.get_close_matches`. Each query token is expanded to up to 3 close
  indexed terms; generalized AND-intersection across token groups. Results
  ranked by total matched-term frequency (same tiebreaker as exact search).
- `GraphQueryEngine.fuzzy_search(query)` — proxy to index; [] when no index.
- CLI: `search QUERY --fuzzy` enables fuzzy matching.
- REPL: new `fuzzy QUERY` verb; Tab autocomplete for commands and indexed
  terms (via `readline`, graceful fallback on Windows without pyreadline3).
- 11 new tests (tests/test_fuzzy_search.py, incl. snapshot round-trip).
  Full suite now 181 green. Arch Gate green (services/ = contracts + stdlib).
- HONEST LIMITATIONS (Stage 20): see README "HONEST LIMITATIONS (Stage 20)"
  (fuzzy + DSL filters not combined; readline needs pyreadline3 on Windows;
  no relevance ranking of fuzzy matches, only term frequency).

## v5.0.0 (Stage 21)
- `GraphQueryEngine.search()` now supports a mini-DSL combining full-text
  AND-search with structural graph filters — all in one query string.
  - `_parse_query()` splits `key:value` filters from text tokens (filters are
    stripped BEFORE tokenization, since `\w+` would otherwise split `tag:todo`).
  - Filters: `tag:X` (node.meta.tags contains X, case-insensitive),
    `from:X` (node is an outgoing edge target of X), `to:X` (node has an
    incoming edge from X — backlinks), `is:orphan` (zero-degree node).
  - Syntax: `[filter:value ...] [text tokens ...]` — every condition ANDed.
  - Text tokens forwarded to `ContentIndex.search()` (frequency sort preserved);
    structural filters applied as a post-filter retaining index order.
  - Filter-only queries (no text tokens) scan ALL graph nodes, so `is:orphan`
    works even with `index=None` (collision-safe: Stage-18 behavior of
    `search("text")` returning [] with no index is preserved).
- Zero regression: plain text queries behave exactly as Stage 18; unknown
  filter keys are silently ignored. No new CLI commands, no new services,
  no new package imports (only `re` + `typing.Tuple` in graph_query_engine.py).
- 9 new tests (tests/test_query_language.py): pure-text regression / tag
  filter / from filter / to filter / is:orphan / multiple filters / filter-only
  / excludes-all / case-insensitive tag / unknown-filter ignored / empty query
  / filter-only-without-index. Full suite now 170 green; Arch Gate green.
- HONEST LIMITATIONS (Stage 21): see README "HONEST LIMITATIONS (Stage 21)"
  (AND-only — no OR/NOT/parens; filters are exact-match; no phrase search;
  filter-only scan is O(nodes), not O(1)).

## v5.0.0 (Stage 23)
- Graph Export: `adapters/exporters/` — DOT (Graphviz), JSON, GEXF (Gephi).
  Each exporter takes the `{"nodes": [...], "edges": [...]}` graph dict
  (shape of `IGraphBuilder.get_graph()`) and returns a `str`. `adapters/` is
  the ONLY place that touches external serialization formats; exporters use
  stdlib only (no third-party graph libs).
  - `export_dot()` -> Graphviz `digraph` (quotes in labels/relations escaped).
  - `export_json()` -> pretty-printed JSON (UTF-8 safe, `ensure_ascii=False`).
  - `export_gexf()` -> GEXF 1.3 XML (namespaced, `defaultedgetype="directed"`,
    edges get sequential 0-based ids; pretty-printed via `minidom`).
- CLI: `export --format {dot,json,gexf} [--output FILE]` — `python main.py
  export --format dot` prints to stdout; `--output FILE` writes to disk.
  Output paths inside the vault go through the `IFileSystem` port; absolute
  paths OUTSIDE the vault are written directly (honest limitation — bypasses
  the FS adapter's traversal guard). `export` restores the graph from
  `data/graph_snapshot.json` before serializing (cold start works).
- REPL: new `export FORMAT [OUTPUT]` verb (same semantics).
- Arch-clean integration: `cli/` does NOT import `adapters` directly. The three
  exporter functions are registered in the DI container by `main.build_container`
  (the composition root, the only place adapters are referenced) and resolved by
  `cli/commands.py` / `cli/repl.py` via `container.resolve("export_<fmt>")`.
- 6 new tests (tests/test_exporters.py): dot basic + empty / json round-trip +
  no-mutation / gexf valid XML / gexf sequential edge ids. Full suite now 187
  green; Arch Gate green.
- HONEST LIMITATIONS (Stage 23): exporters handle only the generic graph dict
  (no Obsidian-specific attributes beyond id/label/meta/relation are serialized);
  GEXF exports `directed` edges only (the kernel graph is directed); export does
  not stream — the whole graph is held in memory (fine for vault-scale graphs);
  absolute `--output` outside the vault escapes the FS-adapter traversal guard.

## v5.0.0 (Stage 27)
- Watch Mode: `python main.py watch --vault ./vault` follows `.md` files and
  auto-recrawls the vault on every change (closes the Stage-10 limitation
  "no incremental crawl — always full rescan" at the process level).
  - `adapters/file_watcher.py` — `FileWatcher`: polling fallback (`os.walk` +
    `os.stat` every `--interval`, default 2.0s, on a daemon thread) ALWAYS
    available; optional `watchdog` observer used only if installed AND
    `--no-watchdog` not passed. The watcher is duck-typed against a
    `callback` -- it knows nothing about crawlers/kernel.
  - `services/watch_service.py` — `WatchService` (IService): wires the
    watcher callback to `crawler.crawl()`. The crawler + watcher are INJECTED
    (duck-typed); the module imports ONLY `contracts` + stdlib (arch-clean).
    An optional Kernel reference (also injected, duck-typed) persists a graph
    snapshot after each recrawl so a crash loses at most one interval.
  - Thread-safety: `VaultStreamCrawler.crawl()` is a coroutine, and the watcher
    may fire from a background thread (polling daemon or watchdog). So
    `WatchService.trigger()` runs it in a FRESH event loop
    (`asyncio.new_event_loop().run_until_complete`) -- thread-isolated and
    loop-safe, unlike `asyncio.run` which binds to the caller's context.
- CLI: `watch --interval SEC [--no-watchdog]` -- blocking process, Ctrl+C stops.
- REPL: `watch` / `watch stop` verb (starts the WatchService in a background
  thread; the REPL loop keeps accepting commands; `watch stop` halts it).
- 8 new tests (tests/test_watch_mode.py): polling detects new file / edit,
  stop idempotent, watchdog-missing fallback, WatchService trigger (async +
  sync crawler + swallows crawl errors + starts watcher and triggers on change).
  Full suite now 195 green; Arch Gate green.
- HONEST LIMITATIONS (Stage 27): no debounce -- N rapid file saves => N crawls;
  polling is O(files) every interval (fine for tens/hundreds, heavy for
  thousands); snapshot persisted per recrawl (not transactional); watchdog is
  a bonus -- if uninstalled, polling is the only path; on Windows the stock
  `watchdog` needs the `pywin32` extra to offer the real OS watcher.

## v5.0.0 (Stage 24)
- `CrawlStateTracker` now stores `sha256(content)` alongside `mtime` in
  `.crawl_state.json` (v2 format). Incremental crawl re-processes a file ONLY
  if its content hash changed — `mtime`-only bumps (git checkout, touch, copy)
  are ignored. This eliminates false triggers in Watch Mode (Stage 27).
- Legacy v1 state files (`{path: mtime}`) are auto-migrated on load — zero
  regression for existing vaults (hash=None entries fall back to mtime).
- Public tracker API unchanged (`save_state({path: mtime})`,
  `get_changed_files(vault)`) — CLI/REPL/Web UI untouched, transparent.
- `hashlib` is the only new stdlib import in `services/` (arch gate clean,
  added to `STDLIB_BASES`).
- 6 new tests (`tests/test_incremental_hash.py`). Full suite now 216 green.
- HONEST LIMITATIONS (Stage 24): hashing reads the entire file content —
  for very large `.md` files this is O(bytes); unreadable files (transient
  locks) are treated as unchanged to avoid infinite re-crawl loops.

## v5.0.0 (Stage 25)
- Plugin System: KnowledgeOS becomes a platform. `contracts/plugin.py`
  (`IPlugin` ABC: register_commands / register_exporters / on_crawl_complete)
  + `infrastructure/plugin_loader.py` (`PluginLoader`: scans --plugin-dir for
  *.py files with a top-level `class Plugin`, imports by file path via
  importlib.util, duck-typed, fail-soft — broken plugins are recorded and
  skipped, never crash the CLI).
- `main.py --plugin-dir DIR <command>`: argv pre-scan (parse_known_args)
  loads plugins BEFORE the real parser so plugin subcommands exist at parse
  time; plugin exporters merge into the DI container as `export_<fmt>`.
- `export --format` no longer constrained by argparse choices — plugin
  formats resolve via the container; unknown format -> JSON error + exit 2
  listing known formats (instead of a KeyError traceback).
- `on_crawl_complete(graph)` fires after batch `crawl`. Built-in commands
  always win a name clash (fail-soft skip of the offending plugin).
- Zero regression without --plugin-dir (loader=None path; container exposes
  `PluginLoader` as None). Real bug caught by smoke: plugin command without
  --vault crashed container build -> plugin commands default vault to cwd.
- 10 new tests (`tests/test_plugins.py`). Full suite now 226 green.
- HONEST LIMITATIONS (Stage 25): no sandbox — plugins run with full process
  rights; on_crawl_complete fires only on batch CLI crawl (not REPL/watch/
  HTTP); directory-convention loader, not setuptools entry_points; no
  inter-plugin deps/priorities; REPL does not see plugin commands.

## v5.0.0 (Stage 26)
- `GraphQueryEngine.centrality()` — in/out/total degree per node.
- `GraphQueryEngine.connected_components()` — weakly connected clusters (BFS).
- `GraphQueryEngine.pagerank(damping=0.85, iterations=30)` — iterative PageRank,
  stdlib-only; reverse adjacency prebuilt once, O(iterations * (nodes + edges)).
- API: `/api/stats/centrality`, `/api/stats/components`, `/api/stats/pagerank`.
- Web UI: "Analytics" button — centrality table, component clusters, top-10
  PageRank (innerHTML reset on each click, no duplication).
- 8 new tests (`tests/test_graph_analytics.py`). Full suite now 234 green.
- HONEST LIMITATIONS (Stage 26): weak components only (no SCC); degree-only
  centrality (no betweenness/closeness); fixed 30 iterations (no epsilon
  early-stop); metrics recomputed per request (no cache).

## v5.0.0 (Stage 28)
- Basic auth for Web UI: `serve --auth user:pass`.
- `services/auth_service.py` — `SimpleAuthService`: in-memory credentials +
  session tokens (`secrets.token_hex(32)`, `secrets.compare_digest`).
- Endpoints: `POST /api/login`, `GET /api/logout` (server-side revoke).
- Cookie `knowledgeos_session` (HttpOnly, Path=/).
- With auth on: `/` -> 302 /login.html; every other route (API and /static/*)
  -> 401 without a valid cookie. Public: `/api/login`, `/login.html` only.
- Zero regression: without `--auth` the server behaves exactly as Stage 22
  (no AuthService registration in DI).
- 5 new tests (`tests/test_auth.py`). Full suite now 239 green.
- HONEST LIMITATIONS (Stage 28): single user; RAM-only sessions (restart
  logs everyone out); unsigned hex token, no TTL; no HTTPS; password visible
  in process args; REPL serve has no --auth.

## v5.0.0 (Stage 29)
- Semantic Search: vector embeddings + cosine similarity.
  - `contracts.IEmbedding` port; `adapters.MockEmbeddingAdapter` (deterministic
    SHA-256 -> 128-dim, L2-normalized) as default wiring; `OpenAIEmbeddingAdapter`
    (stdlib urllib, optional, requires OPENAI_API_KEY).
  - `services.SemanticIndex` — brute-force cosine top-k (O(nodes)/query),
    implements ISnapshotable.
  - `VaultStreamCrawler` indexes docs into SemanticIndex during crawl (duck-typed).
  - `GraphQueryEngine.semantic_search(query, top_k)` proxy to the index.
  - Composite snapshot: SemanticIndex shares data/index_snapshot.json with
    ContentIndex ({"version":2,"index":..,"semantic":..}) — one atomic write.
  - API `GET /api/semantic?q=...&top_k=10` -> [[node_id, score], ...].
  - Web UI: Lexical/Semantic toggle. CLI: `semantic QUERY [--top-k N]`; REPL too.
- 10 new tests (`tests/test_semantic_search.py`). Full suite now 249 green.
- HONEST LIMITATIONS: Mock embedding is NOT real semantics; brute-force O(nodes);
  no incremental semantic update on watch recrawl; no FAISS (out of arch gate).

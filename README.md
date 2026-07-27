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
  ~~No persistence, no incremental update — re-crawl rebuilds from scratch.~~
  → persistence closed in **STAGE 12** (snapshot/restore); incremental crawl
  closed in **STAGE 17** (`CrawlStateTracker`, mtime-based differential update).
- **Single vault:** one root path per crawl. No multi-vault federation.
- **No content indexing:** ~~the crawler stores node labels + extracted tags in
  metadata but does NOT index full file text for search.~~
  → closed in **STAGE 18** (`ContentIndex`, inverted index + `search` command).
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
python main.py repl   --vault PATH          # интерактивный REPL (Kernel живёт весь сеанс)
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
  внутри vault, пишется при `stop()`/`crawl`-завершении). *(Исключение: `repl`
  держит Kernel весь сеанс — см. Этап 16.)*
- **Нет конфиг-файла:** все параметры — только через CLI args (`--vault`).
  *(Закрыто в Этапе 15.)*
- **Нет логирования в файл:** только stdout/stderr (`json.dumps` результатов).
- **Нет интерактивного REPL:** только batch-команды. *(Закрыто в Этапе 16 — `python main.py repl`.)*
- **Нет обработки SIGINT:** `main.py` не ловит KeyboardInterrupt — прерывание
  может оставить граф без свежего snapshot (сохраняется последний успешный).
  *(Частично закрыто в Этапе 16 для `repl` — Ctrl+C делает graceful save+stop;
  batch-команды по-прежнему полагаются на atexit из Этапа 14.)*
- **PID-файл не создаётся:** нет защиты от double-run; `stop` — honest no-op,
  если нет pid-файла.
- **Snapshot — vault-relative:** `data/graph_snapshot.json` пишется через
  `IFileSystem` (base=vault), поэтому восстановление cwd-независимо, но
  требует того же `--vault` при перезапуске.

## STAGE 14 — Periodic Autosave & Watchdog

Закрыто честное ограничение Этапа 13: «Snapshot — только на Kernel.stop().
Crash между вызовами = потеря данных.» Теперь граф автоматически снимется
по таймеру, и гарантирован final-snapshot при graceful exit.

- `Kernel(autosave_interval_sec=…)`: при `start()` (если задан интервал > 0
  и wired IGraphBuilder + IFileSystem) запускает фоновый watchdog — отдельный
  daemon-поток со своим asyncio-loop, крутящий `_autosave_loop()`. Каждые N
  секунд: `graph.snapshot()` + emit `GraphAutosaved {timestamp}`.
- `stop()` идемпотентен: повторный вызов (atexit после явного stop, или на
  UNINITIALIZED) — безопасный no-op, не бросает RuntimeError.
- `atexit` hook: `cli/commands.py` регистрирует `atexit.register(lambda: k.stop())`
  после `k.start()`, гарантируя snapshot при sys.exit / KeyboardInterrupt /
  SIGTERM (частично — см. ограничения).
- CLI: `--autosave SECONDS` у команд `crawl` и `status` (default 60; 0 — выкл).

```bash
python main.py crawl --vault ./my-vault --autosave 30   # snapshot каждые 30s
python main.py status --vault ./my-vault --autosave 30
```

### HONEST LIMITATIONS (Stage 14)
- **Autosave — только graph snapshot**, не полное состояние Kernel (capabilities,
  event-bus history, runtime-context вне scope).
- **Интервал — wall-clock через injectable sleep** (`asyncio.sleep` по умолчанию),
  не точный real-time: дрейфует при долгих операциях и при выгрузке потока.
- **atexit не ловит `kill -9` (SIGKILL):** гарантия только для graceful exit
  (normal return, sys.exit, KeyboardInterrupt, SIGTERM). При SIGKILL данные
  теряются между snapshot.
- **Нет backoff при ошибке записи:** при fail `snapshot()` просто пропускается
  (тихий no-op, без повтора и без алерта).
- **Нет differential save:** всё ещё FULL JSON snapshot каждый раз (O(n+m)),
  как в Этапе 12.
- **Watchdog — daemon-поток:** при жёстком завершении процесса не дожидается
  финального тика; последний гарантированный snapshot — либо по таймеру, либо
  по atexxit/stop.

## STAGE 15 — Config File & Profiles

Закрыто честное ограничение Этапа 13: «Нет конфиг-файла — все параметры через
CLI args.» Теперь каждый vault может хранить `knowledgeos.yaml` (или `.json`)
в корне; CLI читает его автоматически, а аргументы командной строки
переопределяют значения из файла.

- `infrastructure/config_loader.py` — `ConfigLoader`:
  - `load(vault_path, fs: IFileSystem) -> dict` ищет `knowledgeos.yaml` →
    `knowledgeos.yml` → `knowledgeos.json` через порт (YAML preferred, JSON
    fallback). Нет файла → `{}`. Битый/нет файла → `{}` (не падает).
  - `merge_with_cli(cli_args, config) -> dict`: приоритет
    **CLI arg (≠ None) > config > hardcoded default**.
    `autosave_interval`: CLI `--autosave` > `autosave_interval` > `60.0`;
    `vault`: CLI `--vault` > `vault` > `None`; `features`: dict из config.
  - Валидация: unknown top-level keys → `warnings.warn` (не ошибка).
  - Зависит только от `contracts.IFileSystem` + stdlib (json, warnings, typing).
  - YAML через `pyyaml` (optional); при отсутствии — fallback на JSON.
- CLI: `--vault` и `--autosave` стали опциональными (default `None`). Каждая
  команда: `fs = container.resolve("IFileSystem")` →
  `config = ConfigLoader().load(".", fs)` →
  `effective = ConfigLoader().merge_with_cli(args, config)`.
  - `init` пишет шаблон `knowledgeos.yaml` (vault, autosave_interval, features).
  - `crawl`/`status`/`query` пробрасывают `effective["autosave_interval"]` в Kernel.
- Конфиг остаётся на уровне CLI — Kernel получает уже готовые параметры
  (не лезет в сервисы/контракты).

```bash
python main.py init  --vault ./my-vault      # создаёт knowledgeos.yaml
python main.py crawl --vault ./my-vault       # читает autosave_interval из YAML
python main.py crawl --vault ./my-vault --autosave 30   # CLI override
```

### HONEST LIMITATIONS (Stage 15)
- **pyyaml optional** — если не установлен, fallback на JSON (`.json`).
- **Нет schema validation:** unknown keys → `warn`, игнорируются (не ошибка).
- **Нет hot-reload:** конфиг читается once per command.
- **Нет env-var override:** только CLI и YAML.
- **vault в YAML — relative to YAML location** (корень vault'а), резолвится CLI.
- **Нет секций/profiles:** один flat config на vault.

## STAGE 16 — Interactive REPL

Закрыто честное ограничение Этапа 13: «Нет интерактивного REPL — только
batch-команды.» Новый слой `cli/repl.py` — `KnowledgeOSRepl`: долгоживущий
построчный REPL-цикл. **Kernel (и DI-контейнер, и общий граф) создаётся ОДИН
раз** в `cmd_repl` и живёт весь сеанс — он НЕ пересоздаётся на каждую команду
(доказано `tests/test_repl.py::test_repl_kernel_lifecycle`).

```bash
python main.py repl --vault ./my-vault
knowledgeos> crawl
# -> {"files_scanned": 3, "nodes": 3, "edges": 2}
knowledgeos> query backlinks "C.md"
# -> ["A.md"]
knowledgeos> query path "A.md" "C.md"
# -> ["A.md", "C.md"]
knowledgeos> query orphans
# -> []
knowledgeos> status
# -> {"state": "RUNNING", "graph_nodes": 3, "graph_edges": 2}
knowledgeos> save        # форсированный snapshot, Kernel остаётся RUNNING
knowledgeos> exit        # graceful shutdown (snapshot + stop)
```

Новый публичный метод `Kernel.save()` (Stage 16): best-effort
`graph.snapshot()` + emit `GraphSnapshotted` **пока Kernel RUNNING** (не меняет
состояние жизненного цикла, REPL продолжает отвечать). Обратно совместим —
тонкая обёртка над `_try_snapshot_graph`, которую уже вызывает `stop()`.

`Ctrl+C` (KeyboardInterrupt): ловится И на промпте, И во время команды →
`_handle_sigint()` делает save + stop, затем чистый выход (данные не теряются).
`run()` также гарантирует `Kernel.stop()` на любом пути выхода.

История команд — через `readline` (optional import), **только in-memory**:
файл истории никогда не читается/пишется, поэтому между сессиями история не
сохраняется.

### HONEST LIMITATIONS (Stage 16)
- **Нет автодополнения (tab completion):** только in-memory readline-история
  (стрелки вверх/вниз для предыдущих команд), без автодополнения ввода.
- **Нет многострочного ввода:** одна команда на строку, Enter сразу исполняет.
- **Нет pipeline (`crawl | query`):** команды последовательные, вывод одной не
  передаётся на вход другой — результаты только на stdout.
- **Нет background jobs:** `crawl` блокирует REPL до завершения (синхронный
  asyncio.run внутри команды); ввод других команд пока невозможен.
- **Нет remote access:** только локальный stdin/stdout, без сети/сокетов.
- **Нет сохранения истории между сессиями:** readline in-memory only, файл
  истории не используется.
- **SIGINT для batch-команд:** `cmd_crawl/query/status` по-прежнему полагаются
  на `atexit` из Этапа 14 (как и раньше) — собственного try/except KeyboardInterrupt
  в них нет; граф сохранится по atexit, если прерывание произошло после start().

## STAGE 17 — Incremental Crawl

Закрыто честное ограничение Этапа 10: «Нет инкрементального crawl — всегда
full rescan». Новый сервис `services/incremental_tracker.py` →
`CrawlStateTracker`: отслеживает mtime всех `.md` файлов между crawl'ами,
находит только изменённые/новые/удалённые файлы и обновляет граф
**дифференциально** — без полного пересканирования vault'а и без
`graph.clear()`.

```bash
python main.py crawl --vault ./my-vault
# -> {"files_scanned": 3, "nodes": 3, "edges": 2}        # первый: full
python main.py crawl --vault ./my-vault
# -> {"status": "up_to_date", "files_scanned": 0, ...}   # без изменений: мгновенно
# правим одну заметку...
python main.py crawl --vault ./my-vault
# -> {"files_scanned": 1, "nodes": 3, "edges": 3}        # рескан ТОЛЬКО её
```

Как это работает:
- **State-файл** `.crawl_state.json` в корне vault'а: JSON `{filepath: mtime}`,
  читается/пишется через порт `IFileSystem`. Отсутствует или битый → `{}`
  (не падает), т.е. первый crawl всегда full.
- **`get_changed_files(vault)`** → `(changed_or_new, deleted)`: файл не в
  state или mtime отличается → changed; файл из state исчез с диска → deleted.
- **Дифференциальный апдейт**: deleted → `remove_node` (нода + все её рёбра);
  changed → `remove_node` + рескан только этого файла, при этом **входящие
  рёбра от неизменённых соседей сохраняются** (пойманная коллизия: никто их
  не рескачет — трекер их переносит).
- **Новый метод порта** `IGraphBuilder.remove_node(node_id) -> bool`
  (реализация в `InMemoryGraphBuilder`: удаляет ноду и все рёбра, где она
  from или to; True если нода была). snapshot/restore не затронуты.
- **DI**: `main.build_container` регистрирует `CrawlStateTracker` и передаёт
  его в `VaultStreamCrawler(tracker=...)` — инкрементальность получают И
  batch `crawl`, И REPL-команда `crawl` (второй crawl подряд → `up_to_date`).
- **Zero regression**: `tracker=None` → поведение Этапа 10 (full rescan,
  `clear()` + rebuild), state-файл не создаётся
  (`test_zero_regression_without_tracker`).
- Архитектурный контракт: трекер в `services/`, зависит ТОЛЬКО от
  `contracts.IFileSystem` + `contracts.IGraphBuilder` + stdlib (`json`, `os`).
  Crawler НЕ импортирует sibling-сервис (гейт `test_services_do_not_cross_import`):
  tracker duck-typed (`Optional[Any]`), инъекция через DI.

### HONEST LIMITATIONS (Stage 17)
- ~~**mtime, не content-hash:** если откатить файл к старой версии с тем же
  mtime → crawler пропустит изменение.~~ → closed in **STAGE 24**
  (`sha256(content)` в `.crawl_state.json` v2; mtime-only bump игнорируется).
- **Нет обработки renamed файлов:** `old.md` удалён + `new.md` создан = два
  события (удаление + добавление), не rename.
- **State-файл видимый:** `.crawl_state.json` лежит в корне vault'а (рядом с
  заметками), не в `data/`.
- **Нет защиты от concurrent crawl:** два одновременных crawl могут испортить
  state-файл (race condition).
- **Нет обработки symlink changes:** если `.md` — symlink, mtime целевого
  файла может не отражать изменение symlink'а.
- **`remove_node` — O(edges):** при удалении ноды сканируются все рёбра
  (индекса from/to нет).

## STAGE 18 — Content Indexing & Full-Text Search

Закрыто честное ограничение Этапа 10: «No content indexing — crawler stores
node labels + extracted tags in metadata but does NOT index full file text
for search». Новый сервис `services/content_index.py` → `ContentIndex`:
инвертированный индекс (word → posting list of node_ids) по полному тексту
`.md` файлов, searchable через `GraphQueryEngine.search()`.

```bash
python main.py crawl --vault ./my-vault      # строит граф + индекс
python main.py search "hello" --vault ./my-vault
# -> ["A.md", "B.md"]
python main.py search "hello python" --vault ./my-vault
# -> ["B.md"]                                # AND: оба слова в одном файле

python main.py repl --vault ./my-vault
knowledgeos> search hello python
# -> ["B.md"]
```

Как это работает:
- **Токенизация**: regex `\w+`, lowercase, минимум 2 символа. Без stemming,
  без стоп-слов (honest limitations).
- **`index_file(node_id, text)`** — replace-семантика: старые термы документа
  сбрасываются перед индексацией, поэтому reindex (full или incremental)
  никогда не оставляет stale-постингов.
- **`search(query)`** — AND-логика: intersection posting lists всех токенов
  запроса; результат отсортирован по суммарной частоте совпадений (desc),
  затем по node_id (детерминизм). Пустой запрос / отсутствующий терм → `[]`.
- **`remove_file(node_id)`** — через reverse-map `_doc_terms`: O(термов
  документа), пустые posting lists выпиливаются (stats честные).
- **Интеграция с crawler**: full crawl индексирует всё; incremental path —
  changed → `remove_file` + reindex, deleted → `remove_file`. `index=None` →
  zero regression (ничего не индексируется, `search` → `[]`).
- **DI**: `ContentIndex` — singleton в `main.build_container`; crawler ПИШЕТ,
  `GraphQueryEngine` ЧИТАЕТ тот же инстанс (конвенция как с `IGraphBuilder`).
  Оба параметра duck-typed (`Optional[Any]`) — гейт
  `test_services_do_not_cross_import` запрещает sibling-импорт.
- **`ensure_index` (cli/repl.py)**: ~~пойманная коллизия интеграции — индекс
  in-memory, а инкрементальный tracker при `up_to_date` вообще не сканирует
  файлы → в свежем процессе `search` был бы пуст. `cmd_search` и `cmd_repl`
  перед работой перестраивают пустой индекс, читая `.md` через порты
  контейнера (граф и crawl-state не трогаются).~~ → **closed in STAGE 19**:
  индекс восстанавливается из `data/index_snapshot.json` в `Kernel.initialize()`;
  `ensure_index` удалён, cold start — O(1), без перечитывания vault.

### HONEST LIMITATIONS (Stage 18)
- **Только `\w+` токенизация** — нет stemming, нет морфологии («run» и
  «running» — разные термы).
- **Нет стоп-слов** — «the», «and» индексируются как обычные слова.
- **Нет phrase search** — только AND по отдельным словам, не
  последовательность.
- **Нет ранжирования TF-IDF** — результаты отсортированы по частоте
  совпадений, не по релевантности.
- ~~**In-memory only** — индекс в RAM, при рестарте перестраивается
  (`ensure_index` в CLI/REPL перечитывает весь vault; snapshot индекса — не
  в этом этапе).~~ → **closed in STAGE 19** (snapshot/restore через `ISnapshotable`).
- **Нет fuzzy search** — только exact match токенов.

## STAGE 19 — Index Persistence (ISnapshotable + SnapshotStore)

Цель: убить `ensure_index()` и сделать так, чтобы `ContentIndex` восстанавливался
из snapshot вместе с графом. Cold start CLI/REPL стал мгновенным (O(1), без
перечитывания vault).

- **`contracts/ISnapshotable`** (Protocol, `runtime_checkable`):
  `snapshot() -> Dict` / `restore(data: Dict) -> None`. Позволяет Kernel решать
  «реализует ли сервис snapshot» без импорта конкретного `ContentIndex`.
- **`services/content_index.py`** реализует `ISnapshotable` (единственный новый
  импорт — `contracts.snapshotable`; arch-чисто: services → contracts + stdlib).
  `snapshot()` отдаёт plain-dict (списки, не set — JSON-safe); `restore(data)`
  делает полную замену состояния O(terms + doc_terms).
- **`kernel/snapshot_store.py`** → `infrastructure/SnapshotStore`: атомарная
  (tmp + `IFileSystem.rename`) запись версионированного plain-dict payload.
  Не знает схему — Kernel собирает composite dict.
- **`contracts/IFileSystem`** расширен `rename(src, dst)` (os.replace-семантика,
  атомарно на POSIX+Win); реализован в `LocalFileSystemAdapter` и обоих тестовых
  `MockFS`. `IGraphBuilder.snapshot()` тоже пишет атомарно (tmp + rename).
- **`kernel/kernel.py`**: `initialize()` восстанавливает индекс через
  `_try_restore_index()` (runtime_checkable `ISnapshotable` — ядро не импортирует
  `ContentIndex`); `save()` / `stop()` / autosave пишут индекс в
  `data/index_snapshot.json` через `SnapshotStore.save({"version": 2, "index": ...})`.
  Граф по-прежнему персистится отдельно `IGraphBuilder` (отдельный файл, чтобы не
  ломать Stage-12 тесты графа).
- **Удалён `ensure_index`** из `cli/repl.py` (оставлен no-op-заглушкой на один
  релиз для обратной совместимости внешних вызовов); `cmd_search` / `cmd_repl`
  больше не перестраивают индекс вручную — он теперь в snapshot.

### HONEST LIMITATIONS (Stage 19)
- Snapshot не атомарен относительно краша во время записи (rename помогает, но не FS-транзакция).
- Нет дельта-snapshot: при большом vault перезаписывается весь JSON.
- Индекс-снапшот пишется в отдельный файл от граф-снапшота (composite-файл не использован — сохраняет существующие Stage-12 тесты графа).

## STAGE 20 — Fuzzy Search & Autocomplete

`ContentIndex` получил два stdlib-примитива поверх Stage-18 инвертированного
индекса:

- **Prefix suggest** — `ContentIndex.suggest(prefix, limit)` возвращает
  отсортированные термы, начинающиеся с `prefix`, через `bisect_left` по
  поддерживаемому `_sorted_terms`. O(log V + k), V = размер словаря.
  Используется REPL Tab-автодополнением.
- **Fuzzy search** — `ContentIndex.fuzzy_search(query, cutoff=0.6)` —
  нечёткий AND-поиск через `difflib.get_close_matches`. Каждый токен
  запроса расширяется до ≤3 близких индексных термов (своя AND-группа);
  финальный результат — пересечение групп (документ должен матчить хотя бы
  один терм из КАЖДОЙ группы). Ранжирование по суммарной частоте
  совпавших термов (тот же tiebreaker, что у точного поиска).

`GraphQueryEngine.fuzzy_search(query)` — proxy к `ContentIndex.fuzzy_search()`;
`[]` когда индекс не подключён (zero regression).

CLI: `python main.py search "pithon" --fuzzy` находит `python`
(и другие близкие термы). REPL: новый глагол `fuzzy QUERY`; Tab-автодополнение
для команд и индексных термов (через `readline`, тихий fallback на Windows без
`pyreadline3`).

### HONEST LIMITATIONS (Stage 20)
- Fuzzy + DSL-фильтры (`tag:`, `from:`, `to:`, `is:`) одновременно — НЕ
  поддерживаются (fuzzy_search чисто текстовый; пересечение отложено на Stage 22+).
- `readline` на Windows требует `pyreadline3` (не в stdlib); без него
  autocomplete молча отключается.
- Нет ранжирования по релевантности fuzzy-match (только частота термов).

## STAGE 21 — Query Language (structural + full-text DSL)

`GraphQueryEngine.search()` теперь поддерживает мини-DSL, объединяющий
полнотекстовый поиск и структурные фильтры графа в одной строке:

```bash
python main.py search "python"                  # Stage-18 behavior
python main.py search "tag:todo python"         # AND: тег + текст
python main.py search "from:A.md"               # исходящие ссылки из A
python main.py search "to:A.md"                 # входящие ссылки в A (backlinks)
python main.py search "is:orphan"               # ноды без рёбер
python main.py search "tag:python from:A.md"    # множественные фильтры
```

- Вся логика DSL живёт в `GraphQueryEngine` (единственное место, где уже есть
  и граф, и индекс). Никаких новых сервисов, никаких cross-imports в `services/`.
- Текстовые токены передаются в `ContentIndex.search()` (сортировка по
  частоте сохраняется). Структурные фильтры (`tag:`, `from:`, `to:`, `is:`)
  накладываются как пост-фильтр на кандидатов от индекса.
- Если текстовых токенов нет — сканируются все ноды графа (поэтому `is:orphan`
  работает даже при `index=None`).
- Неизвестные фильтры игнорируются (zero regression).

### HONEST LIMITATIONS (Stage 21)
- Только AND-логика — нет OR / NOT / скобок.
- Фильтры exact match (`tag:todo` не найдёт `tag:todos`).
- Нет phrase search (кавычки не парсятся как литералы).
- При сканировании всех нод (только фильтры, без текста) — O(nodes), не O(1).

## STAGE 23 — Graph Export (DOT / JSON / GEXF)

Сериализация графа знаний в стандартные форматы визуализации:

```bash
python main.py export --format json                 # stdout (pretty JSON)
python main.py export --format dot --output g.dot    # Graphviz digraph
python main.py export --format gexf --output g.gexf  # Gephi GEXF 1.3
```

- Экспортеры живут в `adapters/exporters/` (единственное место, трогающее
  внешние форматы). Каждый принимает `{"nodes": [...], "edges": [...]}` и
  возвращает `str`. Только stdlib.
- `--output -` (по умолчанию) — stdout; `--output FILE` — запись на диск.
  Пути внутри vault идут через порт `IFileSystem`; абсолютный путь ВНЕ vault
  пишется напрямую (честное ограничение — обходит traversal-гард адаптера).
- `export` восстанавливает граф из `data/graph_snapshot.json` перед
  сериализацией (cold start работает, как у `query`/`search`).
- REPL: `export FORMAT [OUTPUT]`.
- Интеграция arch-clean: `cli/` не импортирует `adapters` напрямую — экспортеры
  зарегистрированы в DI-контейнере (`main.build_container`) и резолвятся по
  имени `export_<fmt>`.

### HONEST LIMITATIONS (Stage 23)
- Экспортеры сериализуют только универсальный граф-словарь (id/label/meta/
  relation); Obsidian-специфика больше не добавляется.
- GEXF — только направленные рёбра (`directed`), ядро-граф направленный.
- Экспорт не потоковый — весь граф держится в памяти (OK для масштаба vault).
- Абсолютный `--output` вне vault обходит traversal-гард `IFileSystem`.

## STAGE 24 — Content-Hash Incremental Tracking

`CrawlStateTracker` теперь хранит `sha256(content)` вместе с `mtime`:
- Перекроул происходит **только при изменении содержимого**, не при `touch`.
- Watch Mode (Stage 27) перестаёт стрелять вхолостую после `git checkout`.
- Формат `.crawl_state.json` — v2 (`{"path": {"mtime": ..., "hash": "..."}}`).
  v1 (`{"path": mtime}`) мигрируется автоматически при `load_state()`:
  `hash=None` → per-file fallback на mtime-сравнение (Stage-17 семантика).
- Публичный API трекера НЕ менялся (`save_state({path: mtime})`,
  `get_changed_files(vault) -> (changed, deleted)`) — crawler, CLI, REPL и
  Web UI не тронуты, поведение прозрачно.
- Arch gate: `hashlib` — единственный новый импорт в `services/` (stdlib,
  добавлен в `STDLIB_BASES`); services/ по-прежнему только `contracts` + stdlib.

### HONEST LIMITATIONS (Stage 24)
- Хеширование читает весь файл — для больших `.md` это O(bytes).
- Файл, который временно недоступен (lock), считается unchanged (чтобы не
  зациклить watch mode).

## STAGE 27 — Watch Mode (auto-recrawl)

Процесс следит за `.md` файлами vault и перекроуливает граф при изменении:

```bash
python main.py watch --vault ./my-vault            # polling (2.0s)
python main.py watch --vault ./my-vault --interval 1.0 --no-watchdog
```

- `adapters/file_watcher.py` — `FileWatcher`: polling-фолбэк (`os.walk` +
  `os.stat` каждые `--interval`, daemon-thread) **всегда работает**; опциональный
  `watchdog`-observer используется только если установлен и не `--no-watchdog`.
- `services/watch_service.py` — `WatchService` (IService), duck-typed триггер
  `crawler.crawl()` по изменению. Импортирует только `contracts` + stdlib.
- Crawler — coroutine; вотчер стреляет из фонового потока → `trigger()` гонит
  crawl в **свежем event loop** (`asyncio.new_event_loop().run_until_complete`)
  — потокобезопасно. После crawl персистит snapshot через инъектированный Kernel.
- REPL: `watch` / `watch stop`.

### HONEST LIMITATIONS (Stage 27)
- Нет debounce: N быстрых сохранений → N crawl'ов.
- Polling — O(files) каждый интервал (OK для десятков/сотен, тяжело для тысяч).
- Snapshot персистится после каждого recrawl (не транзакционно).
- `watchdog` — бонус; если не установлен, работает только polling.

## STAGE 25 — Plugin System (Entry Points)

KnowledgeOS перестаёт быть монолитом и становится платформой: новые форматы
экспорта, CLI-команды и crawl-хуки добавляются **без правки core**.

- `contracts/plugin.py` — порт `IPlugin` (ABC): `register_commands(parser)`,
  `register_exporters(container)`, `on_crawl_complete(graph)`.
- `infrastructure/plugin_loader.py` — `PluginLoader`: сканирует `--plugin-dir`,
  импортирует каждый `*.py` по file path (`importlib.util`, без загрязнения
  `sys.path`), инстанцирует top-level `class Plugin`. Duck-typed: наследовать
  `IPlugin` рекомендуется, но не обязательно (файл плагина может не иметь
  ни одного импорта из проекта). Fail-soft: битый плагин → запись в
  `loader.errors` + stderr, core CLI никогда не падает.
- `main.py --plugin-dir ./my-plugins <command>`: pre-scan argv
  (`parse_known_args`) решает chicken-and-egg — плагины регистрируют
  субкоманды ДО настоящего `parse_args`. Экспортёры мёржатся в DI-контейнер
  (`export_<fmt>`), `export --format <fmt>` больше не ограничен argparse
  `choices` (неизвестный формат → JSON-ошибка + exit 2 со списком known).
- Хук `on_crawl_complete(graph)` стреляет после batch `crawl`.
- Дубликат имени субкоманды: built-in всегда побеждает (argparse raise →
  fail-soft skip плагина).
- Zero regression: без `--plugin-dir` loader = None, поведение прежнее
  байт-в-байт (`test_no_plugin_dir_zero_regression`).

### HONEST LIMITATIONS (Stage 25)
- Плагины исполняются с полными правами процесса — **никакой песочницы**;
  битый импорт fail-soft, но злонамеренный код не изолируется.
- `on_crawl_complete` стреляет только в batch `crawl` (CLI); REPL `crawl`,
  watch-mode recrawl и HTTP-crawl хук НЕ вызывают.
- Название «Entry Points» условное: это directory-convention loader,
  setuptools entry_points (pip-устанавливаемые плагины) не поддерживаются.
- Плагины загружаются в детерминированном порядке (sorted по имени файла),
  зависимостей/приоритетов между плагинами нет.
- REPL не видит плагиновые команды (парсер REPL отдельный).

## STAGE 26 — Graph Analytics

Метрики графа знаний (чистый stdlib, без numpy):
- **Centrality** — in-degree / out-degree / total-degree для каждой ноды.
- **Connected Components** — кластеры связанных заметок (BFS, weakly connected).
- **PageRank** — итеративный алгоритм (30 итераций, damping 0.85); обратная
  adjacency строится один раз → O(iterations × (nodes + edges)).

API: `GET /api/stats/centrality`, `/api/stats/components`, `/api/stats/pagerank`.
Web UI: кнопка «Analytics» — таблицы centrality / components / top-10 PageRank.

### HONEST LIMITATIONS (Stage 26)
- Components — только weakly connected (рёбра как undirected). Нет SCC
  (Tarjan/Kosaraju не реализованы).
- Центральность — только degree; нет betweenness / closeness (all-pairs
  shortest paths дорого на чистом Python).
- PageRank: фиксированные 30 итераций, без epsilon-критерия сходимости;
  для vault-scale (сотни нод) этого достаточно.
- Analytics считается на каждый запрос заново (никакого кеша) — снимок
  графа честный, но большие графы будут пересчитываться при каждом клике.

## STAGE 28 — Basic Auth for Web UI

```bash
python main.py serve --port 8080 --auth admin:secret
```

- Login-форма на `/login.html` (POST `/api/login`, JSON `{"user","pass"}`).
- Session cookie `knowledgeos_session` (HttpOnly, Path=/), токен —
  `secrets.token_hex(32)`; сравнение кредов — `secrets.compare_digest`.
- Неавторизованный `GET /` → 302 на `/login.html`; все остальные маршруты
  (включая `/static/*`) → 401. Публичны только `/api/login` и `/login.html`.
- `GET /api/logout` отзывает сессию server-side и гасит cookie.
- Без `--auth` поведение байт-в-байт как в Stage 22 (AuthService просто
  не зарегистрирован в DI).

### HONEST LIMITATIONS (Stage 28)
- Один пользователь (`--auth user:pass`), без ролей — all-or-nothing.
- Креды и сессии живут в RAM: рестарт сервера разлогинивает всех.
- Токен — случайный hex, не подписан; нет expiry/TTL у сессий.
- Нет HTTPS — только localhost или за reverse proxy.
- Пароль виден в командной строке процесса (ps/Task Manager).
- REPL-команда `serve` не принимает `--auth` (только CLI).

## Test gates

```
pytest tests/            # unit + e2e + arch gate (158 tests, all green)
python -c "import contracts, infrastructure, kernel, runtime, adapters, services, cli"
python -c "import services.incremental_tracker"  # exit 0
python -c "import services.content_index"        # exit 0
python main.py --help   # exit 0
python main.py repl --help  # exit 0
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

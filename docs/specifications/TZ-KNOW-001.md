---
id: TZ-KNOW-001
title: "Knowledge Graph v2 — Linked Architecture Intelligence"
priority: Critical
status: Incoming
dependencies:
  - TZ-SEC-001 (Secure Runtime) — DONE
  - TZ-MULTI-001 (Tenant Isolation) — Design DONE, Code pending K5
  - ADR-011 (Knowledge Platform) — accepted
  - ADR-012 (Memory Platform) — accepted
  - ADR-021 (Architecture Intelligence Synthesis) — accepted
  - ADR-022 (AKB) — accepted
  - ADR-025 (Multimodal Knowledge Engine) — proposed
date: "2026-08-02"
---

# TZ-KNOW-001: Knowledge Graph v2 — Linked Architecture Intelligence

## 1. Executive Summary

TZ-KNOW-001 превращает разрозненные артефакты KROFT_OS (ADR, RFC, AKB, компоненты, эксперименты, capability) в **связный граф знаний**. Сейчас ADR-032 знает, что связан с TZ-SEC-001, но это записано вручную в markdown frontmatter. AKB хранит YAML-индексы, но без семантических связей. Memory Platform хранит факты, но не отношения.

**TZ-KNOW-001 вводит:**
- **Узлы (nodes):** ADR, RFC, Component, Capability, Experiment, Platform, Pattern, Law
- **Рёбра (edges):** `depends_on`, `supersedes`, `implements`, `validates`, `uses`, `violates`, `proves`, `references`
- **Query Engine:** traversable, filterable, impact-analyzable
- **AKB Sync:** двунаправленная синхронизация графа ↔ YAML-индексов
- **Evidence Traceability:** каждый ADR связан с тестами, бенчмарками, экспериментами, которые его подтверждают

**Зачем:** без связного графа архитектурная эволюция слепа. Изменение ADR-032 (Security Architecture) должно автоматически показывать: какие компоненты затронуты, какие тесты нужно перепроверить, какие ADR зависят от него.

**Критичность:** High. Это фундамент для Architecture Intelligence (Hermes v2.0, ADR-021/023/024) и Runtime Self-Analysis.

---

## 2. Baseline Re-Verify (фактура на момент старта)

После TZ-SEC-001 (commits eacd554 → 4215de4) и TZ-MULTI-001 design (8c2b0c4):

| Компонент | Статус | Где |
|-----------|--------|-----|
| Knowledge Platform | accepted (ADR-011) | `services/knowledge/` (если есть) или `docs/architecture/` |
| Memory Platform | accepted (ADR-012) | `services/memory/` |
| AKB | 13 YAML + patterns | `docs/architecture/AKB/` |
| ADR | 35 (001..035) | `docs/architecture/ADR-*.md` |
| RFC | 6 (001..004 + 006 + 007) | `docs/architecture/RFC/` |
| KRM | 16 entity-types | `docs/architecture/KRM/` |
| Graph Builder | InMemoryGraphBuilder | `infrastructure/` (порт `IGraphBuilder`) |
| Arch-gate | 14 passed | `tests/test_architecture*.py` |
| Full suite | 794 passed | `tests/` |

**Важно:**
- Связи между ADR/Component/Experiment — **только текстовые** (в markdown frontmatter `related: [...]`). Нет машиночитаемого графа.
- `IGraphBuilder` существует в `infrastructure/` или `contracts/` — но используется для runtime-графов (agent hierarchy), **не** для архитектурных связей.
- Нет `contracts/knowledge_graph/` портов.
- Нет `services/knowledge_graph/` — graph engine отсутствует как dedicated service.
- AKB `adrs.yaml` содержит `id`, `status`, `evidence_level`, но **нет** `edges` или `relations`.
- `org_memory.yaml` хранит организационную память, но не связи между артефактами.

---

## 3. Requirements

### 3.1 Functional (R)

| ID | Requirement | Priority | Law |
|----|-------------|----------|-----|
| **R1** | **Graph Schema.** Узлы: `ADR`, `RFC`, `Component`, `Capability`, `Experiment`, `Platform`, `Pattern`, `Law`. Рёбра типизированы: `depends_on`, `supersedes`, `implements`, `validates`, `uses`, `violates`, `proves`, `references`. | Must | K8 |
| **R2** | **Graph Engine.** In-memory directed graph с O(1) lookup по node_id. Поддержка traverse (BFS/DFS), filter по node_type / edge_type / date. | Must | — |
| **R3** | **AKB Sync.** Bidirectional: YAML-индексы (adrs.yaml, rfcs.yaml, history.yaml) → импорт в граф при старте; изменения в графе → экспорт обратно в YAML (atomic, с backup). | Must | K8 |
| **R4** | **ADR Auto-Linker.** Извлечение связей из ADR markdown frontmatter (`related: [ADR-032, RFC-006]`) и тела (`см. ADR-009`, `superseded by ADR-009`) → автоматическое создание рёбер `references` / `supersedes`. | Should | K8 |
| **R5** | **Evidence Traceability.** Каждый ADR связан с `Experiment` узлами (тесты, бенчмарки, ad-hoc verify). Edge `proves` от Experiment → ADR. Edge `validates` от Test → Component. | Must | K4, KES |
| **R6** | **Impact Analysis.** При изменении узла (например, ADR-032 status: accepted → proposed) → запрос `affected_nodes(depth=2)` возвращает все зависимые ADR, Component, Capability, которые нужно пересмотреть. | Must | K8 |
| **R7** | **Human + Machine Readable.** Граф хранится в YAML (`AKB/knowledge_graph.yaml`) для машин + экспортируется в Obsidian MOC (`docs/architecture/MOCs/`) для человека (markdown links, backlinks). | Should | K8 |
| **R8** | **Versioning.** Каждый узел версионируется: `version: int`, `created_at`, `modified_at`. При статус-изменении ADR — snapshot узла в `AKB/knowledge_graph_history.yaml`. | Should | K4 |
| **R9** | **K8 Compliance.** Graph engine — в `services/knowledge_graph/` (meta-layer). Порты — в `contracts/knowledge_graph/`. **Никогда** в `kernel/` или `runtime/`. | Must | K8 |
| **R10** | **Tenant Scoping (future-proof).** Graph nodes могут иметь `tenant_id` (из TZ-MULTI-001). Cross-tenant graph read → deny. Default tenant `"default"` для существующих узлов. | Should | K6 |

### 3.2 Non-Functional (N)

| ID | Requirement |
|----|-------------|
| **N1** | **K1/K8 Compliance.** `services/knowledge_graph/` импортирует только `contracts/` + stdlib. `kernel/` и `runtime/` не знают о графе. |
| **N2** | **K3 Compliance.** `KnowledgeGraphEngine` создаётся и связывается только в `composition/`. |
| **N3** | **Performance.** Graph ≤ 10k nodes, ≤ 50k edges → traverse depth 3 < 50ms. |
| **N4** | **Backward Compatibility.** Существующие AKB YAML (adrs.yaml, rfcs.yaml) не ломаются. Graph — дополнительный слой, не замена. |
| **N5** | **Test Coverage.** `tests/knowledge_graph/` ≥ 95%, включая: auto-linker accuracy, impact analysis correctness, AKB sync roundtrip, negative (circular dependency detection). |
| **N6** | **AKB Sync.** Каждый WP порождает evidence; ADR-036 регистрируется в `adrs.yaml` с `evidence_level: III`. |

---

## 4. Architecture Constraints (LAW)

| Закон | Применение |
|-------|------------|
| **K1** | `kernel/` и `runtime/` **не импортируют** `services/knowledge_graph/`. Graph — meta-layer (K8). |
| **K3** | `KnowledgeGraphEngine` инстанцируется только в `composition/`. |
| **K4** | Каждый узел/ребро — traceable: who created, when, why (evidence link). |
| **K5** | Изменение graph schema (добавление нового edge_type) → human approval через `ApprovalManager`. |
| **K6** | Graph engine читает AKB YAML через порты (file system adapter), не напрямую. |
| **K8** | **Meta-layer только в `services/` и `docs/`**. Graph engine — `services/knowledge_graph/`. Хранение — `AKB/knowledge_graph.yaml` + `docs/architecture/MOCs/`. Runtime/kernel — чистые. |

---

## 5. Work Packages (WP)

### WP-01: Graph Schema & Ports (`contracts/knowledge_graph/`)
**Scope:** Определить порты и value objects для всего graph-слоя.

**Артефакты:**
- `contracts/knowledge_graph/__init__.py`
- `NodeType` (Enum): `ADR`, `RFC`, `COMPONENT`, `CAPABILITY`, `EXPERIMENT`, `PLATFORM`, `PATTERN`, `LAW`
- `EdgeType` (Enum): `DEPENDS_ON`, `SUPERSEDES`, `IMPLEMENTS`, `VALIDATES`, `USES`, `VIOLATES`, `PROVES`, `REFERENCES`
- `Node` — dataclass: `id`, `type`, `label`, `metadata: Dict`, `version`, `created_at`, `modified_at`, `tenant_id: str = "default"`
- `Edge` — dataclass: `source_id`, `target_id`, `type`, `weight: float = 1.0`, `evidence: str = ""`
- `IGraphEngine` — порт:
  - `add_node(n: Node) -> Node`
  - `get_node(id) -> Node | None`
  - `add_edge(e: Edge) -> Edge`
  - `traverse(start_id, edge_type, depth) -> List[Node]`
  - `impact_analysis(node_id, depth) -> Dict[str, List[Node]]` (grouped by NodeType)
  - `find_cycles() -> List[List[str]]`
- `IGraphSync` — порт:
  - `import_from_akb(akb_path) -> None`
  - `export_to_akb(akb_path) -> None`
  - `export_to_moc(output_dir) -> None`

**K1:** Этот модуль — stdlib only.

---

### WP-02: Core Graph Engine (`services/knowledge_graph/`)
**Scope:** Реализация in-memory graph engine.

**Артефакты:**
- `services/knowledge_graph/__init__.py`
- `InMemoryGraphEngine` — реализация `IGraphEngine`
  - `Dict[str, Node]` — nodes
  - `Dict[str, List[Edge]]` — adjacency list (outgoing)
  - `Dict[str, List[Edge]]` — reverse adjacency (incoming, для impact analysis)
  - Thread-safe (RLock)
- `ImpactAnalyzer` — helper: BFS по reverse edges, группировка по NodeType
- `CycleDetector` — DFS с color-marking (white/gray/black)

**K1/K8:** `services/` импортирует только `contracts/`. Никаких `kernel/`, `runtime/`.

---

### WP-03: AKB Sync Adapter (`services/knowledge_graph/`)
**Scope:** Двунаправленная синхронизация с AKB YAML.

**Артефакты:**
- `AKBSyncAdapter` — реализация `IGraphSync`
  - `import_from_akb()`:
    - Читает `adrs.yaml` → Node(type=ADR) для каждой записи
    - Читает `rfcs.yaml` → Node(type=RFC)
    - Читает `history.yaml` → Node(type=EXPERIMENT) для каждого WP
    - Читает `laws.yaml` → Node(type=LAW)
    - Читает `pattern_library.yaml` → Node(type=PATTERN)
    - Создаёт edges `references` из `related` полей ADR/RFC
    - Создаёт edges `proves` из history entries → ADR (evidence link)
  - `export_to_akb()`:
    - Дописывает `knowledge_graph.yaml` в `AKB/` (не ломает существующие YAML)
    - Backup: `knowledge_graph.yaml.bak` перед записью
  - `export_to_moc()`:
    - Генерирует `docs/architecture/MOCs/ADR-Index-Graph.md` — markdown с wiki-ссылками `[[ADR-032]]`, backlinks, graphviz DOT (опционально)

**Примечание:** Не модифицирует `adrs.yaml` / `rfcs.yaml` напрямую (K4: traceable). Только читает + создаёт отдельный `knowledge_graph.yaml`.

---

### WP-04: ADR Auto-Linker (`services/knowledge_graph/`)
**Scope:** Извлечение неявных связей из ADR markdown.

**Артефакты:**
- `ADRAutoLinker`
  - `extract_from_frontmatter(adr_text) -> List[Edge]` — парсит `related: [ADR-009, RFC-006]`
  - `extract_from_body(adr_text) -> List[Edge]` — regex: `ADR-\d+`, `RFC-\d+`, `TZ-[A-Z]+-\d+`, `WP-\d+`
  - `classify_edge(text_context) -> EdgeType` — эвристика:
    - "superseded by ADR-009" → `SUPERSEDES`
    - "depends on ADR-032" → `DEPENDS_ON`
    - "см. ADR-021" → `REFERENCES`
    - "validates ADR-010" → `VALIDATES`

**Accuracy target:** ≥ 90% precision на существующих 35 ADR (manual review as ground truth).

---

### WP-05: Evidence Traceability (`services/knowledge_graph/`)
**Scope:** Связывание тестов, бенчмарков и ad-hoc verify с ADR.

**Артефакты:**
- `EvidenceLinker`
  - `link_test_to_adr(test_name, adr_id, evidence_type="test")` — Edge(type=VALIDATES или PROVES)
  - `link_experiment_to_adr(exp_id, adr_id)` — Edge(type=PROVES)
  - `get_evidence_for(adr_id) -> List[Node]` — все Experiment/Test, подтверждающие ADR
  - `get_adrs_without_evidence() -> List[Node]` — F6 mitigation (ADR without evidence)

**Интеграция:** `scripts/ci.py` после успешного прогона вызывает `EvidenceLinker.link_test_to_adr()` для architecture gate tests → соответствующие ADR.

---

### WP-06: Query Interface (`cli/` или `services/knowledge_graph/`)
**Scope:** CLI и Python API для работы с графом.

**Артефакты:**
- `kroft graph query --node ADR-032 --depth 2 --edge depends_on` — CLI
- `kroft graph impact ADR-032` — показать affected nodes
- `kroft graph cycles` — найти циклические зависимости
- `kroft graph export --format moc` — экспорт в Obsidian
- Python API: `graph_engine.impact_analysis("ADR-032", depth=2)`

---

### WP-07: Visualization / MOC Export
**Scope:** Human-readable экспорт.

**Артефакты:**
- `MOCExporter`
  - `export_adr_moc()` — `docs/architecture/MOCs/ADR-Graph-MOC.md` со списком всех ADR, grouped by status, с wiki-ссылками `[[ADR-032]]` и backlinks
  - `export_capability_map()` — `MOCs/Capability-Graph-MOC.md` — capability → component → platform
  - `export_evidence_map()` — `MOCs/Evidence-Graph-MOC.md` — ADR → tests/experiments

---

### WP-08: Tests (`tests/knowledge_graph/`)
**Scope:** Полное покрытие.

**Тесты (целевой набор ≥ 30):**
- `test_add_node_and_get` — базовый CRUD
- `test_add_edge_and_traverse` — BFS по `depends_on`
- `test_impact_analysis_depth_2` — изменение ADR → затронутые Component
- `test_impact_analysis_grouped_by_type` — группировка
- `test_cycle_detection` — цикл ADR-A → ADR-B → ADR-A
- `test_akb_sync_roundtrip` — import → export → re-import, graph не меняется
- `test_akb_sync_preserves_existing_yaml` — adrs.yaml не модифицирован
- `test_auto_linker_frontmatter` — `related: [ADR-009]` → edge
- `test_auto_linker_body_reference` — "см. ADR-021" → edge
- `test_auto_linker_supersedes` — "superseded by ADR-009" → SUPERSEDES
- `test_evidence_linker_test_to_adr` — test_architecture.py → ADR-001..035
- `test_evidence_linker_no_evidence` — ADR без evidence → F6 detection
- `test_tenant_scoping` — node tenant="acme" не видна в query tenant="corp"
- `test_backward_compat_794_regression` — полный suite не падает

**Цель:** ≥ 30 тестов, покрытие ≥ 95%.

---

### WP-09: Documentation & ADR
**Scope:** Фиксация знаний.

**Артефакты:**
- `ADR-036 Knowledge Graph v2 Architecture.md` — proposed → accepted (после K5)
- `docs/specifications/TZ-KNOW-001.md` — этот документ (уже есть)
- `PROJECT_CONTEXT_MAP.md` v1.6 — обновить §6 (metrics: 850+ tests), §2 (добавить `services/knowledge_graph/`), §4 (ADR-036)
- `AKB/history.yaml` — entries `WP-KNOW-001-design` / `WP-KNOW-001-code`

---

## 6. Integration with Existing Systems

| Система | Интеграция | Не дублирует |
|---------|-----------|--------------|
| **AKB** | Читает `adrs.yaml`, `rfcs.yaml`, `history.yaml`, `laws.yaml`, `pattern_library.yaml` | Не заменяет YAML; дополняет `knowledge_graph.yaml` |
| **ADR** | Auto-linker извлекает `related` / `supersedes` / body refs | Не меняет ADR markdown |
| **Architecture Gate** | EvidenceLinker связывает gate tests с ADR | Не меняет `test_architecture.py` |
| **TZ-SEC-001** | Graph nodes могут иметь `tenant_id` (R10) | Не меняет capability/authz логику |
| **TZ-MULTI-001** | `TenantContextProvider.get_current()` для scoped queries | Не меняет tenant engine |
| **CI (`scripts/ci.py`)** | После прогона: `EvidenceLinker.link_test_to_adr()` | Не меняет CI pipeline (ADR-031) |

---

## 7. Acceptance Criteria (Definition of Done)

- [ ] `contracts/knowledge_graph/` содержит ≥ 2 порта (`IGraphEngine`, `IGraphSync`) + `Node`/`Edge` VO
- [ ] `services/knowledge_graph/` реализует `InMemoryGraphEngine` (thread-safe, cycle detection)
- [ ] `AKBSyncAdapter` импортирует все 35 ADR + 6 RFC + laws + patterns в граф без потерь
- [ ] `ADRAutoLinker` извлекает ≥ 90% связей из существующих ADR (precision check)
- [ ] `ImpactAnalyzer` возвращает корректный список affected nodes для `ADR-032` (depth 2)
- [ ] `EvidenceLinker` связывает `tests/test_architecture.py` с соответствующими ADR
- [ ] `export_to_moc()` генерирует `docs/architecture/MOCs/ADR-Graph-MOC.md` с wiki-ссылками
- [ ] `knowledge_graph.yaml` валиден, не ломает `akb_lint.py`
- [ ] Default tenant `"default"` — обратная совместимость, 794 теста не ломаются
- [ ] Новые graph-тесты: ≥ 30, покрытие ≥ 95%
- [ ] Полный suite: ≥ 850 passed, 0 failed, arch-gate 14 passed
- [ ] `ADR-036` создан, зарегистрирован в AKB, `evidence_level: III`
- [ ] `PROJECT_CONTEXT_MAP.md` обновлён до v1.6
- [ ] `akb_lint.py` — PASSED

---

## 8. Open Questions (Defaults — подтверди или скорректируй)

| ID | Вопрос | Default |
|----|--------|---------|
| **Q1** | **Graph persistence.** Только in-memory (при перезапуске — импорт из AKB) или обязательно сохранять `knowledge_graph.yaml`? | In-memory runtime + `knowledge_graph.yaml` как cache (regenerable). AKB — source of truth. |
| **Q2** | **Auto-linker accuracy.** Достаточно ли regex-based linker (90% precision) или нужен LLM-based extraction (дорого, K8)? | Regex + heuristic (90% target). LLM — в `services/research/` (ADR-021), но не в graph engine core. |
| **Q3** | **Graph versioning.** Snapshot на каждый commit или только на ADR status change? | Snapshot на ADR status change (`accepted`, `superseded`, `rejected`). Не на каждый commit. |
| **Q4** | **MOC location.** `docs/architecture/MOCs/` или `docs/MOCs/`? | `docs/architecture/MOCs/` (рядом с AKB). |
| **Q5** | **CI integration.** `scripts/ci.py` сам вызывает `EvidenceLinker` или отдельный `scripts/sync_evidence.py`? | Отдельный `scripts/sync_evidence.py`, вызываемый из `ci.py` как post-step. |

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **R1.** Graph engine становится bottleneck при 10k+ nodes. | In-memory + adjacency list + O(1) lookup. Масштабирование — future work (external graph DB). |
| **R2.** Auto-linker даёт false positives (90% precision ≠ 100%). | Manual review MOC + `evidence` field на edge для human override. |
| **R3.** AKB sync ломает существующие YAML. | Только чтение существующих + запись в `knowledge_graph.yaml` (новый файл). Backup перед записью. |
| **R4.** Scope creep — graph engine проникает в kernel/runtime (K8 violation). | Arch-gate ловит автоматически. Code review: `services/knowledge_graph/` only. |
| **R5.** Circular dependencies в ADR (ADR-A depends on ADR-B depends on ADR-A). | `CycleDetector.find_cycles()` + CI gate: цикл = warn (не block, т.к. ADR-007/009 — legitimate supersession chain). |

---

## 10. Related Documents

- **TZ-SEC-001** — foundation (capability, tenant-scoping R10)
- **TZ-MULTI-001** — tenant model (R10 integration)
- **ADR-011** — Knowledge Platform (accepted)
- **ADR-012** — Memory Platform (accepted)
- **ADR-021** — Architecture Intelligence Synthesis (accepted)
- **ADR-022** — AKB (accepted)
- **ADR-025** — Multimodal Knowledge Engine (proposed, PHASE 6)
- **ADR-036** — *Knowledge Graph v2 Architecture* (требуется, proposed)
- **RFC-007** — Tenant Isolation (under_review)
- **AKB/knowledge_graph.yaml** — новый файл (target)
- **AKB/org_memory.yaml** — organizational memory (source)

---

## 11. Execution Protocol (LAW K5 + K8)

1. **Design-фаза** (этот документ → RFC-008 + ADR-036 draft → K5-approval → ADR accepted)
2. **Код-фаза** (WP-01..WP-08 атомарными коммитами, pytest между шагами)
3. **Верификация** (ad-hoc verify + full suite + arch-gate + akb-lint + auto-linker precision check)
4. **Docs-фаза** (PROJECT_CONTEXT_MAP v1.6, MOC export, history.yaml)

**Код НЕ стартует без твоего "go" (K5).** Жду approval на design или правки в Q1–Q5.

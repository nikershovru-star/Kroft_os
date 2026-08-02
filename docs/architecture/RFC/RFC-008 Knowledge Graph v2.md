---
id: RFC-008
title: "Knowledge Graph v2 — Linked Architecture Intelligence"
status: under_review
date: "2026-08-02"
related: [TZ-KNOW-001, ADR-036, ADR-011, ADR-012, ADR-021, ADR-022, ADR-025, TZ-SEC-001, TZ-MULTI-001]
authors: [kroft-architect]
evidence_level: III
---

# RFC-008: Knowledge Graph v2 — Linked Architecture Intelligence

## 1. Problem

Связи между архитектурными артефактами (ADR↔RFC↔Component↔Experiment) сейчас только
текстовые: `related: [...]` в markdown frontmatter + `adrs.yaml` без `edges`. Нет
машиночитаемого графа для impact-анализа. Architecture Intelligence (ADR-021/023/024)
слепа без него.

## 2. Proposal

Ввести **meta-layer graph engine** (K8: только `services/knowledge_graph/` + `contracts/knowledge_graph/`,
НЕ kernel/runtime):

- **Ports** (`contracts/knowledge_graph/`, stdlib): `NodeType`, `EdgeType`, `Node`, `Edge`,
  `IGraphEngine` (add/get/traverse/impact_analysis/find_cycles), `IGraphSync` (import/export/MOC).
- **Engine** (`services/knowledge_graph/`): `InMemoryGraphEngine` (adjacency + reverse-adjacency,
  RLock), `ImpactAnalyzer` (BFS по reverse edges), `CycleDetector` (DFS color-marking).
- **Sync**: `AKBSyncAdapter` импортирует `adrs.yaml`/`rfcs.yaml`/`history.yaml`/`laws.yaml`/
  `pattern_library.yaml` → граф; экспорт в новый `AKB/knowledge_graph.yaml` (не трогает старые).
- **Auto-linker**: извлекает `related:` + body-ссылки (regex) → edges `references`/`supersedes`/`depends_on`.
- **Evidence**: `EvidenceLinker` связывает gate-тесты с ADR (edge `validates`/`proves`).
- **MOC**: `MOCExporter` → `docs/architecture/MOCs/ADR-Graph-MOC.md` (wiki-links `[[ADR-032]]`).

### K8 / K1
Graph engine — **meta-layer**, НЕ runtime. `services/knowledge_graph/` импортирует только
`contracts/` + stdlib. `kernel/` и `runtime/` не импортируют граф. Существующий
`IGraphBuilder` (infrastructure/) — runtime-граф агентов, НЕ переиспользуется (K8 boundary).

## 3. Alternatives Considered

- **A. Расширить существующий `IGraphBuilder` (infrastructure/).** Отвергнуто: это runtime-слой;
  нарушает K8 (graph engine в meta-layer, не в infrastructure).
- **B. Внешняя graph DB (neo4j).** Отвергнуто: in-memory + YAML-cache достаточно для ≤10k узлов (N3).
- **C. LLM-based linker.** Отвергнуто (Q2): regex+heuristic 90% precision дешевле, LLM — в
  `services/research/` (ADR-021), не в core.

## 4. Risks

- **R3** AKB sync ломает YAML → митигируется: только чтение старых + запись `knowledge_graph.yaml`.
- **R4** Scope creep в kernel → arch-gate ловит (K1 детектор).

## 5. Decision Needed

K5-approval на ADR-036. После approval — код WP-01..WP-08.

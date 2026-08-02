---
id: ADR-036
title: "Knowledge Graph v2 Architecture"
status: accepted
evidence_level: III
date: "2026-08-02"
decision_score: 0.9
confidence: high
risk: low
related: [TZ-KNOW-001, RFC-008, ADR-011, ADR-012, ADR-021, ADR-022, ADR-025, TZ-SEC-001, TZ-MULTI-001]
law: [K1, K3, K4, K5, K6, K8]
authors: [kroft-architect]
---

# ADR-036: Knowledge Graph v2 Architecture

## Status

**Proposed** — ожидает K5-approval. Design-фаза TZ-KNOW-001. Код (WP-01..WP-08)
НЕ стартует без approval.

## Context

Архитектурные связи (ADR↔RFC↔Component↔Experiment) хранятся только текстом
(markdown frontmatter, `adrs.yaml` без `edges`). Нет машиночитаемого графа →
impact-анализ невозможен. Architecture Intelligence (ADR-021/023/024) требует связного графа.

## Decision

Ввести **meta-layer Knowledge Graph** как отдельный сервис (K8):

1. **Ports** (`contracts/knowledge_graph/`, stdlib-only):
   - `NodeType` (ADR, RFC, COMPONENT, CAPABILITY, EXPERIMENT, PLATFORM, PATTERN, LAW)
   - `EdgeType` (DEPENDS_ON, SUPERSEDES, IMPLEMENTS, VALIDATES, USES, VIOLATES, PROVES, REFERENCES)
   - `Node` / `Edge` dataclasses (с `tenant_id="default"` для R10)
   - `IGraphEngine`: add_node/get_node/add_edge/traverse/impact_analysis/find_cycles
   - `IGraphSync`: import_from_akb/export_to_akb/export_to_moc
2. **Engine** (`services/knowledge_graph/`, contracts-only):
   - `InMemoryGraphEngine` — Dict nodes + adjacency + reverse-adjacency (RLock)
   - `ImpactAnalyzer` — BFS по reverse edges, группировка по NodeType
   - `CycleDetector` — DFS color-marking
   - `AKBSyncAdapter` — импорт AKB YAML → граф; экспорт в `AKB/knowledge_graph.yaml` (new file)
   - `ADRAutoLinker` — frontmatter + body regex → edges
   - `EvidenceLinker` — gate-тесты → ADR (edge validates/proves)
   - `MOCExporter` — `docs/architecture/MOCs/ADR-Graph-MOC.md`

### Integration (не дублирует)
- Читает `adrs.yaml`/`rfcs.yaml`/`history.yaml`/`laws.yaml`/`pattern_library.yaml` (НЕ меняет их)
- Пишет отдельный `knowledge_graph.yaml` (backup перед записью)
- `services/graph_query_engine.py` (runtime-граф KnowledgeOS-v5) — НЕ трогаем (K8 boundary)
- `IGraphBuilder` (infrastructure/) — runtime-граф агентов, НЕ переиспользуется

## Consequences

**Positive:**
- Impact-анализ при ADR-change (K8 traceability).
- Evidence traceability (F6 mitigation: ADR без evidence → detect).
- Backward-compat: 794 теста не ломаются (graph — add-on layer).

**Negative / Trade-offs:**
- Auto-linker precision 90% (не 100%) → MOC review + `evidence` field для override.
- In-memory (≤10k nodes); external graph DB — future work.

## Compliance
- **K1:** `services/knowledge_graph/` только `contracts/` + stdlib; kernel/runtime не импортируют граф.
- **K3:** `KnowledgeGraphEngine` создаётся только в `composition/`.
- **K4:** каждый node/edge traceable (evidence link).
- **K5:** новый edge_type → ApprovalManager.
- **K6:** чтение AKB через порты (file adapter).
- **K8:** meta-layer только в `services/` + `docs/`; runtime/kernel чистые.

## Alternatives (см. RFC-008 §3)
A. расширить IGraphBuilder — отвергнуто (K8).
B. внешняя graph DB — отвергнуто (N3).
C. LLM-linker — отвергнуто (Q2).

## Open Questions (defaults)
- Q1 persistence: in-memory + `knowledge_graph.yaml` cache (AKB = source of truth).
- Q2 linker: regex+heuristic 90%.
- Q3 versioning: snapshot на ADR status change.
- Q4 MOC: `docs/architecture/MOCs/`.
- Q5 CI: `scripts/sync_evidence.py` из `ci.py` post-step.

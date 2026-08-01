---
tags: [kroft, adr, knowledge, architecture]
created: 2026-07-31
status: superseded
superseded_by: ADR-011 Knowledge Platform
---

# ADR-008 — Knowledge Platform

**Status:** Draft (Wave 8)

## Context
Knowledge Graph stores only verified facts (*Evidence Before Knowledge*).

## Decision
- Pipeline: Document → Chunk → Embedding → Entity Extraction → Relation Discovery
  → Evidence → Validation → Knowledge Graph.
- LLM produces **hypotheses only**; KG accepts **verified facts only**.
- Every edge carries: source, evidence, trust level, change history.

## Consequence
- KG is a trusted resource, not an LLM dump.
- Evaluation (ADR-007/Wave 7) scores extraction/retrieval independently.
- Detailed spec TBD in Wave 8.

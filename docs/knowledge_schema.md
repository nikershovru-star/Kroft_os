---
id: KROFT_KNOWLEDGE_SCHEMA
title: KROFT Knowledge Schema — Atomic Q&A Node
status: accepted
date: 2026-08-08
related: KROFT_Knowledge_Base_Proposal.md, ADR-107 (Slice 1–9 arc), ADR-069 (Knowledge Search Retrieval)
---

# KROFT Knowledge Schema — Atomic Q&A Node

> Schema for the `KROFT_KNOWLEDGE/` layer: a teaching knowledge base of **atomic** facts
> (Question → Answer → Example → Relations), kept SEPARATE from project decisions in the
> Obsidian Vault. Ingested through the existing `KnowledgeEngine` (headers → entities,
> `[[wikilinks]]` → relations/edges), indexed by `ContentIndex`, retrievable by AND-search.

## 1. Seven knowledge types

| Type | Meaning | Example node |
|------|---------|--------------|
| `FACTUAL` | what is known ("what?") | "What is an operating system?" |
| `CONCEPTUAL` | how concepts connect ("why?") | "What is dependency inversion?" |
| `PROCEDURAL` | how to do something ("how?") | "How to diagnose a KROFT failure?" |
| `EXPERIENTIAL` | what happened before ("what occurred?") | "After snapshot restore 17 edges invalid → added pre-restore validation" |
| `META` | how confident / how we know ("how sure?") | "How does KROFT report uncertainty?" |
| `SELF` | the system's own architecture/state ("who am I?") | "Where is the Knowledge Layer in KROFT?" |
| `DECISIONAL` | what to choose ("when?") | "When graph DB vs vector DB vs filesystem?" |

## 2. Minimal node fields

Every Q&A file (`KROFT_KNOWLEDGE/qa_NNN.md`) carries:

| Field | Required | Notes |
|-------|----------|-------|
| `id` | yes | filename stem, e.g. `qa_001` (used as `doc_id` in ingest) |
| `type` | yes | one of the 7 types above (inline `# TYPE: FACTUAL`) |
| `content` | yes | the Q&A body; MUST contain the `QUESTION` and `ANSWER`; may contain `EXAMPLE` |
| `relations` | no | `[[Concept]]` wikilinks inside `content`; extracted as graph edges |
| `confidence` | yes | `high` / `medium` / `low` (inline `# CONFIDENCE: high`) |
| `provenance` | yes | source, e.g. `textbook:OSTEP`, `paper:RAG`, `self:KROFT` (inline `# PROVENANCE:`) |
| `ttl` | yes | days until review/expiry (inline `# TTL: 365`); `0` = permanent |

## 3. File format (reference)

```markdown
# QA-001 — What is an operating system?

TYPE: FACTUAL
CONFIDENCE: high
PROVENANCE: textbook:OSTEP
TTL: 365

QUESTION: What is an operating system?
ANSWER: A program that manages hardware resources and gives applications a standard
interface to CPU, memory, files, devices, and other processes.
EXAMPLE: An app writes a file via a syscall; it does not drive the disk directly.
RELATIONS: [[Process]] [[Memory]] [[Kernel]] [[Filesystem]]
```

`# TYPE:` / `# CONFIDENCE:` / `# PROVENANCE:` / `# TTL:` are inline metadata lines (human
readable; the harness test reads them with a small parser — no new port, no contracts change).
`[[X]]` wikilinks are extracted by `KnowledgeEngine.ingest` as `REFERENCES` edges (+ `BACKLINKS`).

## 4. Ingestion contract (K5 reuse)

- Reader: a thin `KROFT_KNOWLEDGE/` markdown reader (or `ContentIndex` directly per file).
- `KnowledgeEngine.ingest(doc_id, text)`:
  - `#`-headers → `Entity(type="concept")`
  - `[[wikilink]]` → `Relation(doc_id, "links", target)` + graph edge (REFERENCES + BACKLINKS)
  - `content_index.index_file(doc_id, text)` → inverted index for AND-search retrieval
- Graph: `InMemoryGraphEngine` (nodes + edges). Retrieval: `ContentIndex.search(query)`.
- Persistence: `KnowledgeSnapshotStore.save(graph_state, index_state, ...)` round-trips the
  post-ingest state to JSON; `load()` restores it. No new storage layer.

## 5. Retrieval contract (test-facing)

For each node, its `QUESTION` is a valid query. `ContentIndex.search(question)` MUST return
the node's `doc_id` in the top-k (k=3) for **≥ 90 %** of the pilot corpus. AND-search means a
node matches only if it contains ALL query tokens, so each `QUESTION` must embed distinctive
terms also present in its own `content` (true by construction: question ⊂ content).

## 6. Type coverage required by the pilot

The pilot (`KROFT_KNOWLEDGE/qa_*.md`, 60–100 nodes) MUST include, per type:
- `SELF` — "how is KROFT built / where is the Knowledge Layer" etc.
- `DECISIONAL` — "when graph DB vs vector DB vs filesystem" etc.
- the other 5 types with ≥ 5 nodes each.

## 7. Extension rule (stop condition)

If a knowledge type cannot be represented by the schema above (e.g. a `DECISIONAL` rule with
structured `IF/THEN` that `ingest`'s header/wikilink extraction cannot surface as a node),
REQUEST a schema extension from the owner BEFORE mass-generating. The pilot stays within the
7-type / 7-field model; scaling to 10k–20k Q&A happens only after the pilot proves retrieval.

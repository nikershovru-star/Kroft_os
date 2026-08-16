"""PHASE C — Graph ← Self-Evolution integration (ТЗ Integration & Trust Closure).

Reuse-first, K1-clean (kernel/ -> contracts + stdlib only). This is the MINIMAL
integration boundary that closes the contour:

    Experience (Episode)
        -> ReferenceMemoryEvolution.consolidate()   [already exists, SOFT-only O1]
        -> SemanticFact (validated, provenanced, MIN-aggregated confidence)
        -> Runtime Graph (IGraphBuilder.add_node)    [THIS wiring]

The consolidation safety (min_repetitions>=2, confidence>=0.7, MIN aggregation,
SOFT-only, O1 HARD guard) already lives in ``ReferenceMemoryEvolution``. This
module only MOVES a consolidated SemanticFact into the graph — it adds NO new
policy, NO new confidence math, NO LLM judgement.

Safety (ТЗ §11-§17):
- SOFT-only: only SemanticFact (never Policy / HARD) is written to the graph.
- Provenance preserved: fact.source_episodes -> node meta['provenance'].
- Duplicate control: idempotent by fact.id (skip if node already exists).
- No LLM output reaches GraphBuilder.add_node without the consolidation gate.
"""

from __future__ import annotations

from typing import Any, List, Optional

from contracts.i_memory_evolution import IMemoryEvolution
from contracts.igraph_builder import IGraphBuilder


def promote_facts_to_graph(
    episodes: List[Any],
    memory_evolution: IMemoryEvolution,
    builder: IGraphBuilder,
    label_prefix: str = "fact",
) -> List[str]:
    """Consolidate episodes and write resulting SOFT SemanticFacts into the graph.

    Returns the list of graph node ids created (empty when nothing consolidated,
    or all facts already present — idempotent, no duplicates).

    Trust/safety is delegated to ``memory_evolution.consolidate`` (which enforces
    repetition + confidence + SOFT-only). This function only performs the write,
    never relaxes any gate.
    """
    facts, _policies = memory_evolution.consolidate(episodes)
    created: List[str] = []
    # Identity/dedup (ТЗ §17/C.6): consolidated facts carry a RANDOM uuid id
    # (ReferenceMemoryEvolution._uid), so dedup MUST be by content, not by id.
    # Re-consolidating the same experience must not create a second node.
    existing = {
        n.get("id") for n in builder.get_graph().get("nodes", [])
    }
    existing_content = {
        (n.get("meta") or {}).get("content") for n in builder.get_graph().get("nodes", [])
    }
    for fact in facts:
        fid = fact.id
        content = getattr(fact, "content", None)
        if fid in existing or content in existing_content:
            continue  # duplicate control: never duplicate a consolidated fact
        meta = {
            "type": "SOFT_FACT",  # runtime layer tag; production schema has no type
            "content": content,
            "confidence": float(getattr(fact.confidence, "value", 0.0)),
            "provenance": list(getattr(fact, "source_episodes", ()) or ()),
            "causal_mark": getattr(fact, "causal", None),
            "layer": "soft",
        }
        builder.add_node(fid, f"{label_prefix}: {content or fid}", meta)
        created.append(fid)
        existing.add(fid)
        existing_content.add(content)
    return created

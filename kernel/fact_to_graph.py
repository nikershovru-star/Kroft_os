"""PHASE C + PHASE B.3 — Graph <- Self-Evolution + Multi-Resolution ladder.

Reuse-first, K1-clean (kernel/ -> contracts + stdlib only). Closes TWO contours:

  (1) PHASE C (Integration & Trust Closure): Experience -> consolidate -> graph.
  (2) PHASE B.3 (Multi-Resolution): the consolidated graph carries a semantic
      ladder OBSERVATION -> FACT -> PATTERN -> CONCEPT, with `level` metadata and
      `aggregates` / `summarizes` edges so GraphQueryEngine.zoom_in/zoom_out work.

Safety (ТЗ §11-§17 + Phase B §3):
- SOFT-only: only SemanticFact (never Policy / HARD) reaches the graph.
- Provenance preserved: fact.source_episodes -> node meta['provenance'].
- Duplicate control: dedup by content (ReferenceMemoryEvolution._uid is random),
  so re-consolidating the same experience never creates a second node.
- No LLM output reaches GraphBuilder.add_node without the consolidation gate.
- Pattern/Concept nodes are DERIVED from consolidated facts (not invented):
  a PATTERN groups >=2 facts sharing a keyword; a CONCEPT groups >=2 patterns
  sharing an abstract tag. Edges carry the ladder direction.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from contracts.i_memory_evolution import IMemoryEvolution
from contracts.igraph_builder import IGraphBuilder
from contracts.knowledge_graph import NodeType


def _keyword(content: str) -> str:
    """Deterministic grouping key: first 3 significant words (lowercased)."""
    words = re.findall(r"[a-zа-я0-9_]+", content.lower())
    return " ".join(words[:3]) if words else content.lower()


def promote_facts_to_graph(
    episodes: List[Any],
    memory_evolution: IMemoryEvolution,
    builder: IGraphBuilder,
    label_prefix: str = "fact",
) -> Dict[str, List[str]]:
    """Consolidate episodes and write the semantic ladder into the graph.

    Returns a dict of created node-id lists:
        {"facts": [...], "patterns": [...], "concepts": [...]}

    Trust/safety is delegated to ``memory_evolution.consolidate`` (repetition +
    confidence + SOFT-only O1). This function only performs the write + ladder
    derivation, never relaxes any gate.
    """
    facts, _policies = memory_evolution.consolidate(episodes)
    created: Dict[str, List[str]] = {"facts": [], "patterns": [], "concepts": []}
    if not facts:
        return created

    # --- dedup against existing graph (by content) ---
    existing_content = {
        (n.get("meta") or {}).get("content") for n in builder.get_graph().get("nodes", [])
    }
    # group facts by keyword for pattern detection
    by_kw: Dict[str, List[Any]] = defaultdict(list)

    for fact in facts:
        content = getattr(fact, "content", None)
        if content in existing_content:
            continue  # duplicate control (ТЗ §17 / Phase B §3 dedup)
        fid = fact.id
        meta = {
            "type": NodeType.FACT.value,
            "level": "fact",
            "content": content,
            "confidence": float(getattr(fact.confidence, "value", 0.0)),
            "provenance": list(getattr(fact, "source_episodes", ()) or ()),
            "causal_mark": getattr(fact, "causal", None),
            "layer": "soft",
        }
        builder.add_node(fid, f"{label_prefix}: {content or fid}", meta)
        created["facts"].append(fid)
        existing_content.add(content)
        by_kw[_keyword(content or fid)].append((fid, content))

    # --- PATTERN: >=2 facts share a keyword ---
    for kw, members in by_kw.items():
        if len(members) < 2:
            continue
        pid = f"pattern-{abs(hash(kw)) % 10**8:08x}"
        if any(n.get("meta", {}).get("content") == f"pattern:{kw}" for n in builder.get_graph().get("nodes", [])):
            continue  # pattern already exists for this keyword
        pmeta = {
            "type": NodeType.PATTERN.value,
            "level": "pattern",
            "content": f"pattern:{kw}",
            "aggregates": [m[0] for m in members],
            "confidence": 0.0,
        }
        builder.add_node(pid, f"pattern: {kw}", pmeta)
        created["patterns"].append(pid)
        for fid, _ in members:
            builder.add_edge(fid, pid, "aggregates")  # fact -> pattern

    # --- CONCEPT: >=2 patterns share an abstract tag (here: first keyword token) ---
    # Patterns carry no explicit tag in this minimal model; group by their first
    # keyword token to form a concept over related patterns.
    pat_by_token: Dict[str, List[str]] = defaultdict(list)
    for pid in created["patterns"]:
        node = next((n for n in builder.get_graph().get("nodes", []) if n["id"] == pid), None)
        if not node:
            continue
        token = (node["meta"].get("content", "pattern:").split(":", 1)[-1].split()[0]
                 if node["meta"].get("content") else "x")
        pat_by_token[token].append(pid)
    for token, pats in pat_by_token.items():
        if len(pats) < 2:
            continue
        cid = f"concept-{abs(hash(token)) % 10**8:08x}"
        cmeta = {
            "type": NodeType.CONCEPT.value,
            "level": "concept",
            "content": f"concept:{token}",
            "summarizes": list(pats),
            "confidence": 0.0,
        }
        builder.add_node(cid, f"concept: {token}", cmeta)
        created["concepts"].append(cid)
        for pid in pats:
            builder.add_edge(pid, cid, "summarizes")  # pattern -> concept

    return created

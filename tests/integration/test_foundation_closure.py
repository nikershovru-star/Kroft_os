"""PHASE A + B — Foundation -> Runtime Graph + Multi-Resolution Query (production).

Slow: builds the real container (loads KROFT_KNOWLEDGE_FOUNDATION/_snapshot.json,
~717MB) and proves the production foundation becomes a queryable runtime graph
with the REAL production node shape (no schema migration).

Run: pytest tests/integration/test_foundation_closure.py -m slow
"""

import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.container_builder import build_container  # noqa: E402
from services.graph_query_engine import GraphQueryEngine  # noqa: E402


@pytest.mark.slow
def test_foundation_becomes_runtime_graph_and_queryable():
    with tempfile.TemporaryDirectory() as tmp:
        c = build_container(tmp)
        gqe: GraphQueryEngine = c.resolve("GraphQueryEngine")
        snap = gqe._snapshot()
        nodes = snap["nodes"]
        edges = snap["edges"]

        # PHASE A: production foundation restored into runtime graph.
        # (Known production counts — must match; if they drift, foundation changed.)
        assert len(nodes) == 17641, f"nodes={len(nodes)}"
        assert len(edges) == 33490, f"edges={len(edges)}"

        # Schema preservation: production shape is {id, label, meta:{...}}.
        # Top-level `type` is absent; type (if any) lives inside meta.
        sample = nodes[0]
        assert "id" in sample and "label" in sample and "meta" in sample
        assert "type" not in sample  # production has no top-level type

        # PHASE B: Multi-Resolution query on the REAL production shape.
        # nodes_by_metadata must read meta dict (production uses meta, not top-level).
        # Pick a real metadata key present in the sample node.
        meta_keys = set()
        for n in nodes[:200]:
            meta_keys.update((n.get("meta") or {}).keys())
        # At least one of these real production keys should be present somewhere.
        for key in ("source", "tags", "question", "answer", "related_concepts"):
            if key in meta_keys:
                hits = gqe.nodes_by_metadata(key)
                # may be empty for some keys; non-crashing is the contract
                assert isinstance(hits, list)
                break
        else:
            # Fallback: tag-based resolution (nodes_by_tag reads meta['tags']).
            # Must not raise on production shape.
            assert isinstance(gqe.nodes_by_tag("nonexistent-tag"), list)

        # nodes_by_type on production (no top-level/meta type) must return [] gracefully
        # (not crash) — production foundation simply has no typed nodes.
        assert gqe.nodes_by_type("FACT") == []

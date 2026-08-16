"""PHASE B — Multi-Resolution verification (fast).

Covers: NodeType ladder (Фаза 1), get_level, nodes_by_level / zoom_in / zoom_out
(Фаза 2) on a synthetic graph, and a Foundation-load smoke test (Фаза 0 residual:
the boot-bridge itself is verified by tests/graph/test_foundation_bridge.py).
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.knowledge_graph import NodeType, get_level  # noqa: E402
from infrastructure.graph_builder import InMemoryGraphBuilder  # noqa: E402
from services.graph_query_engine import GraphQueryEngine  # noqa: E402
from services.multi_resolution import MultiResolutionQuery  # noqa: E402


def _mr(b: InMemoryGraphBuilder) -> MultiResolutionQuery:
    return MultiResolutionQuery(GraphQueryEngine(b), b)


def test_nodetype_ladder_present():
    for t in ("OBSERVATION", "FACT", "PATTERN", "CONCEPT"):
        assert hasattr(NodeType, t), f"NodeType.{t} missing"
    # existing v2 types preserved
    assert hasattr(NodeType, "ADR")
    assert hasattr(NodeType, "NOTE")


def test_get_level_typed_and_metadata():
    b = InMemoryGraphBuilder()
    b.add_node("f1", "F", {"type": "FACT", "level": "fact"})
    b.add_node("m1", "M", {"level": "concept"})
    b.add_node("old", "O", {"type": "work"})  # no ladder -> None
    mr = _mr(b)
    # get_level reads NodeType ladder member
    assert mr.get_level("f1") == "fact"
    # ...or metadata['level']
    assert mr.get_level("m1") == "concept"
    # old snapshot node: no level -> None
    assert mr.get_level("old") is None


def test_nodes_by_level_and_zoom():
    b = InMemoryGraphBuilder()
    b.add_node("obs1", "o", {"type": "OBSERVATION", "level": "observation"})
    b.add_node("fact1", "f", {"type": "FACT", "level": "fact"})
    b.add_node("pat1", "p", {"type": "PATTERN", "level": "pattern"})
    b.add_edge("obs1", "fact1", "derived_from")
    b.add_edge("fact1", "pat1", "aggregates")
    mr = _mr(b)
    assert set(mr.nodes_by_level("fact")) == {"fact1"}
    assert set(mr.nodes_by_level("pattern")) == {"pat1"}
    # zoom_in(pattern) -> fact (child, more detailed, edge into pattern)
    assert mr.zoom_in("pat1") == ["fact1"]
    # zoom_out(fact) -> pattern (parent, more abstract, edge out of fact)
    assert mr.zoom_out("fact1") == ["pat1"]
    # zoom_out(observation) -> fact (derived_from)
    assert mr.zoom_out("obs1") == ["fact1"]


def test_add_level_relation_writes_edge():
    b = InMemoryGraphBuilder()
    b.add_node("c1", "c", {"type": "CONCEPT", "level": "concept"})
    b.add_node("p1", "p", {"type": "PATTERN", "level": "pattern"})
    mr = _mr(b)
    mr.add_level_relation("p1", "c1", "summarizes")
    assert ("p1", "c1", "summarizes") in (
        (e["from"], e["to"], e["relation"]) for e in b.get_graph()["edges"]
    )


def test_foundation_loads_with_new_nodetype_no_error():
    """Фаза 0 residual smoke: build_container must not break with extended NodeType.

    Sibling's tests/graph/test_foundation_bridge.py asserts the 17641-node count;
    here we only prove the container builds and the Query API resolves without
    raising (fast path, no full-count assertion).
    """
    import tempfile
    from composition.container_builder import build_container
    from services.multi_resolution import MultiResolutionQuery
    with tempfile.TemporaryDirectory() as tmp:
        c = build_container(tmp)
        q = c.resolve("GraphQueryEngine")
        mr = MultiResolutionQuery(q, c.resolve("IGraphBuilder"))
        # Query API usable; production nodes carry no ladder level -> empty is fine.
        assert isinstance(mr.nodes_by_level("concept"), list)
        assert mr.nodes_by_level("concept") == []  # production has no typed levels yet

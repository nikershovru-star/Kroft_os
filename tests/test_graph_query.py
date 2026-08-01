"""Stage 11 - GraphQueryEngine unit tests (10)."""
from contracts import IService, IGraphBuilder, IGraphQuery
from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine


def _g():
    g = InMemoryGraphBuilder()
    return g


def _with_edges():
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {"tags": ["idea"]})
    g.add_node("B", "B", {"tags": ["idea"]})
    g.add_node("C", "C", {"tags": ["todo"]})
    g.add_edge("A", "B", "links_to")
    g.add_edge("C", "B", "links_to")
    return g


def test_backlinks():
    g = _with_edges()
    q = GraphQueryEngine(g)
    assert sorted(q.backlinks("B")) == ["A", "C"]
    assert q.backlinks("A") == []
    assert q.backlinks("C") == []


def test_forward_links():
    g = _with_edges()
    q = GraphQueryEngine(g)
    assert sorted(q.forward_links("A")) == ["B"]
    assert sorted(q.forward_links("C")) == ["B"]
    assert q.forward_links("B") == []


def test_nodes_by_tag():
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {"tags": ["idea"]})
    g.add_node("B", "B", {"tags": ["idea"]})
    g.add_node("C", "C", {"tags": ["todo"]})
    q = GraphQueryEngine(g)
    assert sorted(q.nodes_by_tag("idea")) == ["A", "B"]
    assert q.nodes_by_tag("todo") == ["C"]
    assert q.nodes_by_tag("missing") == []


def test_orphan_nodes():
    g = InMemoryGraphBuilder()
    # A -> B ; C has NO edges at all (orphan)
    g.add_node("A", "A", {"tags": []})
    g.add_node("B", "B", {"tags": []})
    g.add_node("C", "C", {"tags": []})
    g.add_edge("A", "B", "links_to")
    q = GraphQueryEngine(g)
    # NOTE: orphan = node with in-degree 0 AND out-degree 0.
    # A has out-degree>0 -> not orphan. B has in-degree>0 -> not orphan.
    # C has no edges -> orphan.
    assert q.orphan_nodes() == ["C"]


def test_path_found():
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {"tags": []})
    g.add_node("B", "B", {"tags": []})
    g.add_node("C", "C", {"tags": []})
    g.add_edge("A", "B", "links_to")
    g.add_edge("B", "C", "links_to")
    q = GraphQueryEngine(g)
    p = q.path("A", "C")
    # BFS shortest path: [A, B, C]
    assert p == ["A", "B", "C"]
    # direct self
    assert q.path("A", "A") == ["A"]


def test_path_not_found():
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {"tags": []})
    g.add_node("B", "B", {"tags": []})
    # A and B isolated
    q = GraphQueryEngine(g)
    assert q.path("A", "B") is None
    # unknown node
    assert q.path("A", "ZZZ") is None


def test_path_max_depth():
    g = InMemoryGraphBuilder()
    # chain A->B->C->... length 20
    prev = None
    names = [f"N{i}" for i in range(20)]
    for n in names:
        g.add_node(n, n, {"tags": []})
    for i in range(len(names) - 1):
        g.add_edge(names[i], names[i + 1], "links_to")
    q = GraphQueryEngine(g)
    # default max_depth=10: path of 19 hops exceeds depth -> None
    assert q.path("N0", "N19") is None
    # explicit large max_depth finds it
    p = q.path("N0", "N19", max_depth=50)
    assert p is not None and p[0] == "N0" and p[-1] == "N19"


def test_cluster_by_tag():
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {"tags": ["idea"]})
    g.add_node("B", "B", {"tags": ["idea", "todo"]})
    g.add_node("C", "C", {"tags": ["todo"]})
    g.add_node("D", "D", {"tags": []})
    q = GraphQueryEngine(g)
    clusters = q.cluster_by_tag()
    assert sorted(clusters["idea"]) == ["A", "B"]
    assert sorted(clusters["todo"]) == ["B", "C"]
    assert "idea" in clusters and "todo" in clusters


def test_stats():
    g = InMemoryGraphBuilder()
    for n in ["A", "B", "C", "D", "E"]:
        g.add_node(n, n, {"tags": []})
    # 4 edges: A->B, B->C, C->D, D->E
    g.add_edge("A", "B", "links_to")
    g.add_edge("B", "C", "links_to")
    g.add_edge("C", "D", "links_to")
    g.add_edge("D", "E", "links_to")
    q = GraphQueryEngine(g)
    s = q.stats()
    assert s["total_nodes"] == 5
    assert s["total_edges"] == 4
    assert abs(s["avg_degree"] - (4 / 5)) < 1e-9
    # A..E all have degree>0 -> no orphans
    assert s["orphan_count"] == 0


def test_query_engine_is_iservice():
    g = _g()
    q = GraphQueryEngine(g)
    assert isinstance(q, IService)
    assert isinstance(q, IGraphQuery)

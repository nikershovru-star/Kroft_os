"""Stage 12 - Graph persistence E2E tests (4)."""
import asyncio
import tempfile

from kernel import Kernel
from infrastructure import DependencyContainer, InMemoryGraphBuilder, InMemoryEventBus
from adapters import LocalFileSystemAdapter
from services import VaultStreamCrawler, GraphQueryEngine


def _assemble_with_fs(tmp):
    # Real LocalFileSystemAdapter so snapshots hit real disk (survives restart).
    fs = LocalFileSystemAdapter(tmp)
    bus = InMemoryEventBus()
    graph = InMemoryGraphBuilder()
    c = DependencyContainer()
    c.register_instance("IFileSystem", fs)
    c.register_instance("IEventBus", bus)
    c.register_instance("IGraphBuilder", graph)
    return c, fs, bus, graph


VAULT = {
    "vault": ["A.md", "B.md", "C.md"],
    "vault/A.md": ["#idea hub links [[vault/B.md]] and [[vault/C.md]]"],
    "vault/B.md": ["#todo leaf links [[vault/C.md]]"],
    "vault/C.md": ["#idea #todo sink no links"],
}


def test_full_lifecycle():
    tmp = tempfile.mkdtemp()
    c, fs, bus, graph = _assemble_with_fs(tmp)
    # materialize the vault onto real disk (LocalFileSystemAdapter reads disk)
    for rel, lines in VAULT.items():
        if rel == "vault":
            continue
        fs.write_content(rel, "\n".join(lines))
    k = Kernel(c)
    k.initialize()
    k.start()
    # crawl builds the graph
    crawler = VaultStreamCrawler(fs, bus, graph, "vault")
    asyncio.run(crawler.crawl())
    q = GraphQueryEngine(graph)
    assert sorted(q.backlinks("vault/C.md")) == ["vault/A.md", "vault/B.md"]
    k.stop()  # persists snapshot

    # NEW kernel, SAME disk -> restore
    c2, fs2, bus2, graph2 = _assemble_with_fs(tmp)
    k2 = Kernel(c2)
    k2.initialize()  # restores from disk
    q2 = GraphQueryEngine(graph2)
    assert {n["id"] for n in graph2.get_graph()["nodes"]} == {
        "vault/A.md", "vault/B.md", "vault/C.md"
    }
    assert sorted(q2.backlinks("vault/C.md")) == ["vault/A.md", "vault/B.md"]
    k2.start()
    k2.stop()


def test_persistence_survives_restart():
    tmp = tempfile.mkdtemp()
    c, fs, bus, graph = _assemble_with_fs(tmp)
    k = Kernel(c)
    k.initialize()
    k.start()
    graph.add_node("K", "K", {"tags": ["keep"]})
    graph.add_edge("K", "K", "self")
    k.stop()
    # "process dies" -> brand new Kernel on the same disk
    c2, fs2, bus2, graph2 = _assemble_with_fs(tmp)
    k2 = Kernel(c2)
    k2.initialize()
    g = graph2.get_graph()
    assert "K" in {n["id"] for n in g["nodes"]}
    assert any(e["from"] == "K" for e in g["edges"])


def test_no_persistence_without_fs():
    # Kernel with NO IFileSystem registered -> stop() must not crash (no-op).
    c = DependencyContainer()
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    k = Kernel(c)
    k.initialize()
    k.start()
    k.stop()  # no exception expected
    assert k.state.name == "STOPPED"


def test_events_emitted():
    tmp = tempfile.mkdtemp()
    c, fs, bus, graph = _assemble_with_fs(tmp)
    # seed a snapshot so restore would actually succeed on init
    seed = InMemoryGraphBuilder()
    seed.add_node("A", "A", {"tags": []})
    seed.snapshot(fs, "data/graph_snapshot.json")
    k = Kernel(c)
    k.initialize()  # GraphRestored emitted
    k.start()
    k.stop()  # GraphSnapshotted emitted
    topics = {h["topic"] for h in bus.get_history()}
    assert "GraphRestored" in topics
    assert "GraphSnapshotted" in topics

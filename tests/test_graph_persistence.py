"""Stage 12 - Graph persistence unit tests (8)."""
import json

from contracts import IFileSystem
from infrastructure import InMemoryGraphBuilder, InMemoryEventBus
from adapters import LocalFileSystemAdapter


class MockFS(IFileSystem):
    """In-memory IFileSystem that records write/exists/read for assertions."""
    def __init__(self, store=None):
        self._store = store if store is not None else {}
        self.written = []
        self.deleted = []

    def exists(self, p): return p in self._store
    def read_content(self, p):
        if p not in self._store:
            raise FileNotFoundError(p)
        return self._store[p]
    def write_content(self, p, c):
        self._store[p] = c
        self.written.append(p)
        return True
    def append(self, p, c):
        self._store[p] = self._store.get(p, "") + c
        return True
    def delete(self, p):
        self._store.pop(p, None)
        self.deleted.append(p)
        return True
    def rename(self, src, dst):
        if src in self._store:
            self._store[dst] = self._store.pop(src)
        self.written.append(dst)  # record the final (post-rename) path
        return True
    def list_dir(self, p):
        return [k.split("/")[-1] for k in self._store if k.startswith(str(p) + "/")]


def _populated():
    g = InMemoryGraphBuilder()
    g.add_node("A", "A", {"tags": ["idea"]})
    g.add_node("B", "B", {"tags": ["todo"]})
    g.add_edge("A", "B", "links_to")
    return g


def test_snapshot_creates_file():
    fs = MockFS()
    g = _populated()
    g.snapshot(fs, "snap.json")
    assert "snap.json" in fs.written
    assert fs.exists("snap.json")


def test_snapshot_content_valid_json():
    fs = MockFS()
    g = _populated()
    g.snapshot(fs, "snap.json")
    data = json.loads(fs.read_content("snap.json"))
    assert "nodes" in data and "edges" in data
    assert isinstance(data["nodes"], dict)
    assert isinstance(data["edges"], list)
    # content matches live graph
    assert data["edges"] == g.get_graph()["edges"]


def test_restore_recovers_graph():
    fs = MockFS()
    g = _populated()
    g.snapshot(fs, "snap.json")
    g2 = InMemoryGraphBuilder()
    ok = g2.restore(fs, "snap.json")
    assert ok is True
    assert g.get_graph()["nodes"] == g2.get_graph()["nodes"]
    assert g.get_graph()["edges"] == g2.get_graph()["edges"]


def test_restore_missing_file_returns_false():
    fs = MockFS()
    g = InMemoryGraphBuilder()
    ok = g.restore(fs, "nope.json")
    assert ok is False
    # graph untouched (silent fallback, no exception); still empty here
    assert g.get_graph()["nodes"] == []


def test_restore_corrupt_file_returns_false():
    fs = MockFS({"bad.json": "{not valid json,,,,"})
    g = InMemoryGraphBuilder()
    ok = g.restore(fs, "bad.json")
    assert ok is False
    # corrupt file left the graph empty (no node added by restore)
    assert g.get_graph()["nodes"] == []


def test_snapshot_thread_safe():
    import threading
    fs = MockFS()
    g = InMemoryGraphBuilder()
    for i in range(50):
        g.add_node(f"N{i}", f"N{i}", {"tags": [f"t{i}"]})
    errors = []

    def worker():
        try:
            g.snapshot(fs, "snap.json")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"snapshot raised: {errors}"
    # the final snapshot must be a valid JSON graph
    data = json.loads(fs.read_content("snap.json"))
    assert len(data["nodes"]) == 50


def test_kernel_restores_on_init():
    from kernel import Kernel
    from infrastructure import DependencyContainer

    # Pre-seed a snapshot via MockFS.
    fs = MockFS()
    seed = InMemoryGraphBuilder()
    seed.add_node("A", "A", {"tags": ["idea"]})
    seed.add_node("B", "B", {"tags": []})
    seed.add_edge("A", "B", "links_to")
    seed.snapshot(fs, "data/graph_snapshot.json")

    c = DependencyContainer()
    c.register_instance("IFileSystem", fs)
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    k = Kernel(c)
    k.initialize()  # should restore the seeded graph

    graph = c.resolve("IGraphBuilder")
    g = graph.get_graph()
    assert {n["id"] for n in g["nodes"]} == {"A", "B"}
    assert len(g["edges"]) == 1


def test_kernel_snapshots_on_stop():
    from kernel import Kernel
    from infrastructure import DependencyContainer

    fs = MockFS()
    c = DependencyContainer()
    c.register_instance("IFileSystem", fs)
    graph = InMemoryGraphBuilder()
    graph.add_node("A", "A", {"tags": ["idea"]})
    c.register_instance("IGraphBuilder", graph)

    k = Kernel(c)
    k.initialize()
    k.start()
    k.stop()  # should snapshot the graph

    assert "data/graph_snapshot.json" in fs.written
    # the snapshot actually contains the node
    data = json.loads(fs.read_content("data/graph_snapshot.json"))
    assert "A" in data["nodes"]

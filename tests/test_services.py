"""Stage 10 - VaultStreamCrawler application service tests."""
import asyncio
from pathlib import Path

import pytest

from contracts import IService, IFileSystem, IEventBus, IGraphBuilder
from infrastructure import InMemoryEventBus, InMemoryGraphBuilder
from services import VaultStreamCrawler


class MockFS(IFileSystem):
    """Minimal in-memory IFileSystem returning bare names from list_dir."""

    def __init__(self, tree):
        self._tree = tree

    def exists(self, p): return p in self._tree
    def read_content(self, p):
        v = self._tree.get(p)
        return v[0] if isinstance(v, list) and v and isinstance(v[0], str) else str(v or "")
    def write_content(self, p, c): return True
    def append(self, p, c): return True
    def delete(self, p): return True
    def list_dir(self, p):
        # Mirror the real LocalFileSystemAdapter: entries are paths RELATIVE
        # TO THE BASE (p is already relative to base). Bare child names are
        # returned as full relative paths by prefixing the listed directory.
        return [f"{p}/{x}" for x in self._tree.get(p, []) if isinstance(x, str)]


def _make_crawler(tree):
    fs = MockFS(tree)
    bus = InMemoryEventBus()
    graph = InMemoryGraphBuilder()
    return VaultStreamCrawler(fs, bus, graph, "vault"), bus, graph


TWO_MD = {
    "vault": ["A.md", "B.md"],
    "vault/A.md": ["#idea note about [[B]]"],
    "vault/B.md": ["plain"],
}


def test_crawl_finds_markdown_files():
    c, bus, g = _make_crawler(TWO_MD)
    stats = asyncio.run(c.crawl())
    assert stats["files_scanned"] == 2
    ids = {n["id"] for n in g.get_graph()["nodes"]}
    assert {"vault/A.md", "vault/B.md"}.issubset(ids)


def test_crawl_extracts_wiki_links():
    c, bus, g = _make_crawler(TWO_MD)
    asyncio.run(c.crawl())
    edges = g.get_graph()["edges"]
    assert any(e["from"] == "vault/A.md" and e["to"] == "B" for e in edges)


def test_crawl_extracts_tags():
    tree = {"vault": ["A.md"], "vault/A.md": ["text #idea #todo more"]}
    c, bus, g = _make_crawler(tree)
    asyncio.run(c.crawl())
    node = next(n for n in g.get_graph()["nodes"] if n["id"] == "vault/A.md")
    assert node["meta"]["tags"] == ["idea", "todo"]


def test_crawl_publishes_events():
    c, bus, g = _make_crawler(TWO_MD)
    asyncio.run(c.crawl())
    topics = [h["topic"] for h in bus.get_history()]
    assert "crawl.started" in topics
    assert "crawl.finished" in topics


def test_crawl_no_md_files():
    tree = {"vault": ["readme.txt", "sub"]}
    c, bus, g = _make_crawler(tree)
    stats = asyncio.run(c.crawl())
    assert stats["files_scanned"] == 0
    assert stats["files"] == 0 if "files" in stats else True


def test_graph_neighbors():
    tree = {
        "vault": ["A.md", "B.md", "C.md"],
        "vault/A.md": ["link [[B]] and [[C]]"],
        "vault/B.md": ["x"],
        "vault/C.md": ["y"],
    }
    c, bus, g = _make_crawler(tree)
    asyncio.run(c.crawl())
    assert set(g.get_neighbors("vault/A.md")) == {"B", "C"}


def test_crawl_idempotent():
    c, bus, g = _make_crawler(TWO_MD)
    asyncio.run(c.crawl())
    n1 = len(g.get_graph()["nodes"])
    # second crawl must clear + rebuild (no duplicate nodes)
    asyncio.run(c.crawl())
    g2 = g.get_graph()
    assert len(g2["nodes"]) == n1
    # edges non-duplicated (A->B single)
    assert sum(1 for e in g2["edges"] if e["from"] == "vault/A.md" and e["to"] == "B") == 1


def test_crawler_is_iservice():
    c, bus, g = _make_crawler(TWO_MD)
    assert isinstance(c, IService)


def test_arch_service_only_contracts():
    import ast
    from pathlib import Path
    ROOT = Path(__file__).resolve().parent.parent
    src = (ROOT / "services" / "vault_stream_crawler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {"kernel", "runtime", "adapters", "infrastructure"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            top = (node.module or "").split(".")[0]
            if top in forbidden:
                violations.append(f"{node.lineno}: {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in forbidden:
                    violations.append(f"{node.lineno}: {alias.name}")
    assert not violations, f"services axis violation: {violations}"


def test_e2e_full_assembly():
    # DI Container assembles the full application stack (hexagonal proof).
    from infrastructure import DependencyContainer, InMemoryGraphBuilder
    from contracts import IGraphBuilder
    import tempfile, os
    from adapters import LocalFileSystemAdapter

    tmp = tempfile.mkdtemp()
    (Path(tmp) / "A.md").write_text("#idea root [[MissingNote]]", encoding="utf-8")
    (Path(tmp) / "sub").mkdir(exist_ok=True)
    (Path(tmp) / "sub" / "B.md").write_text("#todo deeper", encoding="utf-8")

    container = DependencyContainer()
    fs = LocalFileSystemAdapter(tmp)
    bus = InMemoryEventBus()
    graph = InMemoryGraphBuilder()
    container.register_instance("IFileSystem", fs)
    container.register_instance("IEventBus", bus)
    container.register_instance("IGraphBuilder", graph)
    container.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            container.resolve("IFileSystem"),
            container.resolve("IEventBus"),
            container.resolve("IGraphBuilder"),
            ".",
        ),
        singleton=True,
    )

    crawler = container.resolve("VaultStreamCrawler")
    assert isinstance(crawler, IService)
    # confirm it is wired through ports only (no adapter import in service)
    stats = asyncio.run(crawler.crawl())
    assert stats["files_scanned"] == 2

    # graph built via resolved IGraphBuilder
    g = container.resolve("IGraphBuilder").get_graph()
    ids = {n["id"] for n in g["nodes"]}
    assert "A.md" in ids
    assert any(i.replace("\\", "/").endswith("sub/B.md") for i in ids)
    assert len(ids) == 2
    # events published on the resolved bus
    topics = [h["topic"] for h in container.resolve("IEventBus").get_history()]
    assert "crawl.started" in topics and "crawl.finished" in topics
    # real files actually exist on disk
    assert os.path.exists(os.path.join(tmp, "A.md"))
    assert os.path.exists(os.path.join(tmp, "sub", "B.md"))

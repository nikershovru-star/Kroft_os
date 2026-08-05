"""Stage 11 - GraphQueryEngine E2E tests (4): service-to-service via shared port."""
from tests._repo_root import repo_root
import asyncio
import ast
from pathlib import Path

import pytest

from contracts import IService, IGraphBuilder, IGraphQuery
from infrastructure import InMemoryEventBus, InMemoryGraphBuilder
from services import VaultStreamCrawler, GraphQueryEngine


def _make_crawler(tree):
    fs = MockFS(tree)
    bus = InMemoryEventBus()
    graph = InMemoryGraphBuilder()
    return VaultStreamCrawler(fs, bus, graph, "vault"), bus, graph


class MockFS:
    """Minimal in-memory IFileSystem returning paths relative to base."""
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
        return [f"{p}/{x}" for x in self._tree.get(p, []) if isinstance(x, str)]


# Vault where wiki-links use FULL relative paths so node-id == edge-target.
VAULT = {
    "vault": ["A.md", "B.md", "C.md"],
    "vault/A.md": ["#idea hub links [[vault/B.md]] and [[vault/C.md]]"],
    "vault/B.md": ["#todo leaf links [[vault/C.md]]"],
    "vault/C.md": ["#idea #todo sink no links"],
}


def test_crawl_then_query():
    c, bus, g = _make_crawler(VAULT)
    asyncio.run(c.crawl())
    q = GraphQueryEngine(g)
    # backlinks of C: A and B link to it
    assert sorted(q.backlinks("vault/C.md")) == ["vault/A.md", "vault/B.md"]
    # forward links of A
    assert sorted(q.forward_links("vault/A.md")) == ["vault/B.md", "vault/C.md"]
    # tags
    assert "vault/A.md" in q.nodes_by_tag("idea")
    assert "vault/C.md" in q.nodes_by_tag("idea")
    assert "vault/C.md" in q.nodes_by_tag("todo")
    # path A -> C (direct link exists)
    p = q.path("vault/A.md", "vault/C.md")
    assert p is not None and p[0] == "vault/A.md" and p[-1] == "vault/C.md"
    # stats consistent with crawl
    s = q.stats()
    assert s["total_nodes"] == 3
    assert s["total_edges"] == 3
    # no orphans in a fully-linked small vault
    assert q.orphan_nodes() == []


def test_query_while_crawl():
    # Query against an EMPTY graph must not crash and return empty results.
    g = InMemoryGraphBuilder()
    q = GraphQueryEngine(g)
    assert q.backlinks("X") == []
    assert q.forward_links("X") == []
    assert q.nodes_by_tag("idea") == []
    assert q.orphan_nodes() == []
    assert q.path("X", "Y") is None
    assert q.cluster_by_tag() == {}
    s = q.stats()
    assert s["total_nodes"] == 0 and s["total_edges"] == 0 and s["orphan_count"] == 0
    assert isinstance(q, IService)


def test_service_isolation():
    # GraphQueryEngine must NOT import VaultStreamCrawler.
    import importlib
    mod = importlib.import_module("services.graph_query_engine")
    src = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(src):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[-1] == "vault_stream_crawler":
                raise AssertionError("GraphQueryEngine imports VaultStreamCrawler")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[-1] == "vault_stream_crawler":
                    raise AssertionError("GraphQueryEngine imports VaultStreamCrawler")
    assert True


def test_arch_services_no_cross_import():
    ROOT = repo_root()
    src = (ROOT / "services" / "graph_query_engine.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {"kernel", "runtime", "adapters", "infrastructure"}
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            top = (node.module or "").split(".")[0]
            if top in forbidden:
                violations.append(f"{node.lineno}: {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in forbidden:
                    violations.append(f"{node.lineno}: {alias.name}")
    # Also: must not import the sibling service module directly.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[-1] == "vault_stream_crawler":
                violations.append(f"{node.lineno}: sibling service import")
    assert not violations, f"services axis violation: {violations}"
    # positive: it DOES import contracts (the only allowed project package)
    allowed = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "contracts":
            allowed = True
    assert allowed, "GraphQueryEngine does not import contracts"

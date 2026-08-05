"""Stage 63 — Graph Access Control & Permissions tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine


class MockFS:
    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write_content(self, path: str, data: str) -> None:
        self._files[path] = data

    def read_content(self, path: str) -> str:
        return self._files[path]


class TestGraphACL:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        b.add_node("secret.md", "Secret", {"tags": ["doc"]})
        return GraphQueryEngine(b, fs=MockFS(), snapshot_path="g.json")

    # ------------------------------------------------------------------ #
    # grant / revoke / check / list                                       #
    # ------------------------------------------------------------------ #
    def test_grant_creates_acl_edge(self):
        engine = self._make_engine()
        r = engine.grant_permission("alice", "bob", "secret.md", "read")
        assert r["ok"] is True
        assert r["created"] is True
        snap = engine._snapshot()
        acl_edges = [
            e
            for e in snap.get("edges", [])
            if isinstance(e, dict) and e.get("from") == "user:alice" and e.get("to") == "secret.md" and (e.get("relation") or "").startswith("acl:")
        ]
        assert len(acl_edges) == 1

    def test_check_explicit_grant_allowed(self):
        engine = self._make_engine()
        engine.grant_permission("alice", "bob", "secret.md", "read")
        r = engine.check_permission("bob", "read", "secret.md")
        assert r["ok"] is True
        assert r["allowed"] is True
        assert r["reason"] == "explicit"

    def test_list_permissions_returns_grants(self):
        engine = self._make_engine()
        engine.grant_permission("alice", "bob", "secret.md", "read")
        engine.grant_permission("alice", "bob", "secret.md", "write")
        r = engine.list_permissions("alice")
        assert r["ok"] is True
        assert len(r["permissions"]) >= 1
        resources = {p["resource"] for p in r["permissions"]}
        assert "secret.md" in resources

    def test_revoke_removes_permission(self):
        engine = self._make_engine()
        engine.grant_permission("alice", "bob", "secret.md", "read")
        r = engine.revoke_permission("alice", "bob", "secret.md")
        assert r["ok"] is True
        assert r["removed"] >= 1

    def test_wildcard_grant(self):
        engine = self._make_engine()
        engine.grant_permission("alice", "bob", "*", "read")
        r = engine.check_permission("bob", "read", "secret.md")
        assert r["ok"] is True
        assert r["allowed"] is True
        assert r["reason"] == "wildcard"

    def test_acl_methods_exist(self):
        b = InMemoryGraphBuilder()
        b.add_node("secret.md", "Secret", {"tags": ["doc"]})
        engine = GraphQueryEngine(b)
        for method in [
            "grant_permission",
            "revoke_permission",
            "check_permission",
            "list_permissions",
            "set_user_context",
            "get_user_context",
            "share_session",
            "revoke_session",
        ]:
            assert hasattr(engine, method)

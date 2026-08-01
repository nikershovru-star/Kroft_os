"""Stage 64 — Graph Collaborative Editing (Enhanced) tests."""
from __future__ import annotations

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class MockFS:
    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    def write_content(self, path: str, data: str) -> None:
        self._files[path] = data

    def read_content(self, path: str) -> str:
        return self._files[path]


class TestGraphCollaborative:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        b.add_node("shared.md", "Hello world", {"tags": ["doc"]})
        return GraphQueryEngine(b, fs=MockFS(), snapshot_path="g.json")

    # ------------------------------------------------------------------ #
    # Optimistic locking                                                   #
    # ------------------------------------------------------------------ #
    def test_optimistic_lock_success(self):
        engine = self._make_engine()
        # legacy node has no _rev → current_rev == 0
        r = engine.add_node(
            "shared.md",
            "Hello alice",
            base_revision=0,
            actor="alice",
            strategy="reject",
        )
        assert r["ok"] is True
        assert r["revision"] >= 1

    def test_conflict_detected_and_rejected(self):
        engine = self._make_engine()
        engine.add_node(
            "shared.md",
            "Hello alice",
            base_revision=0,
            actor="alice",
            strategy="reject",
        )
        # bob edits from stale base_revision == 0
        r = engine.add_node(
            "shared.md",
            "Hello bob",
            base_revision=0,
            actor="bob",
            strategy="reject",
        )
        assert r["ok"] is False
        assert "Conflict" in r["error"]

    # ------------------------------------------------------------------ #
    # Merge strategies                                                     #
    # ------------------------------------------------------------------ #
    def test_lww_automatic_resolution(self):
        engine = self._make_engine()
        engine.add_node(
            "shared.md",
            "Alice version",
            base_revision=0,
            actor="alice",
            strategy="reject",
        )
        r = engine.add_node(
            "shared.md",
            "Bob version",
            base_revision=0,
            actor="bob",
            strategy="lww",
        )
        # lww compares vector clocks; bob's write wins here
        assert r["ok"] is True
        node = engine._find_node("shared.md")
        assert "Bob version" in node["content"]

    def test_three_way_merge_non_overlapping(self):
        engine = self._make_engine()
        base = "Line1\nLine2\nLine3\n"
        engine.add_node("doc.md", base, {})

        r1 = engine.add_node(
            "doc.md",
            "Line1-A\nLine2\nLine3\n",
            base_revision=0,
            actor="alice",
            strategy="content_merge",
        )
        assert r1["ok"] is True

        r2 = engine.add_node(
            "doc.md",
            "Line1\nLine2\nLine3-B\n",
            base_revision=0,
            actor="bob",
            strategy="content_merge",
        )
        assert r2["ok"] is True

        content = engine._find_node("doc.md")["content"]
        assert "Line1-A" in content
        assert "Line3-B" in content

    # ------------------------------------------------------------------ #
    # Branching                                                            #
    # ------------------------------------------------------------------ #
    def test_branch_fork_and_merge(self):
        engine = self._make_engine()
        engine.fork_branch("alice", "feature", from_revision=0)
        r = engine.merge_branch(
            "alice",
            "feature",
            target_resource="shared.md",
            strategy="lww",
        )
        assert r["ok"] is True

    # ------------------------------------------------------------------ #
    # Offline-first queue                                                  #
    # ------------------------------------------------------------------ #
    def test_offline_queue_sync(self):
        engine = self._make_engine()
        engine.queue_mutation(
            "bob",
            "add_node",
            {
                "node_id": "offline.md",
                "content": "Created offline",
                "meta": {},
            },
            base_revision=0,
        )
        r = engine.sync_queue("bob", strategy="lww")
        assert r["ok"] is True
        assert r["applied"] == 1
        assert engine._find_node("offline.md") is not None

    # ------------------------------------------------------------------ #
    # ACL-aware merge                                                      #
    # ------------------------------------------------------------------ #
    def test_acl_blocks_merge(self):
        engine = self._make_engine()
        engine.grant_permission("alice", "bob", "shared.md", "read")
        r = engine.add_node(
            "shared.md",
            "Hacked",
            base_revision=0,
            actor="bob",
            strategy="reject",
        )
        assert r["ok"] is False
        assert "permission" in r["error"].lower()

    # ------------------------------------------------------------------ #
    # Agent NL intents                                                     #
    # ------------------------------------------------------------------ #
    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("add_node", lambda **kw: {"ok": True})
        reg.register("fork_branch", lambda **kw: {"ok": True})
        reg.register("merge_branch", lambda **kw: {"ok": True})
        reg.register("sync_queue", lambda **kw: {"ok": True})
        svc = AgentService(reg)
        assert svc.execute("edit shared.md with base 0 content Hello")["tool"] == "add_node"
        assert svc.execute("fork branch feature from rev 0")["tool"] == "fork_branch"
        assert svc.execute("merge branch feature into shared.md with strategy lww")["tool"] == "merge_branch"
        assert svc.execute("синхронизируй мои изменения")["tool"] == "sync_queue"

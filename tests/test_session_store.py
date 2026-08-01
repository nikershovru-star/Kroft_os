"""Stage 39 - Session persistence & agent state recovery tests (5)."""
import json
import os
import tempfile

import pytest

from services import AgentService, SessionStore, ToolRegistry


class TestSessionStore:
    def test_persistence_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sess.json")
            s = SessionStore(path)
            s.set_last_find([{"id": "a.md", "score": 0.9}], "find python")
            assert os.path.exists(path)
            s2 = SessionStore(path)
            assert s2.get_last_find()[0]["id"] == "a.md"

    def test_reset_clears_data(self):
        s = SessionStore()
        s.set_last_find([{"id": "x"}])
        s.reset()
        assert s.get_last_find() == []

    def test_agent_implicit_ref_with_session(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "y.md", "score": 0.8}])
        r.register("open_note", lambda query, top_k=1: {"opened": query})
        session = SessionStore()
        svc = AgentService(r, session_store=session)
        svc.execute("find python")
        r2 = svc.execute("open the first one")
        assert r2["action"] == "open"
        assert r2["target"] == "y.md"

    def test_agent_implicit_ref_survives_recreate(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "z.md", "score": 0.8}])
        r.register("open_note", lambda query, top_k=1: {"opened": query})
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sess.json")
            s1 = AgentService(r, session_store=SessionStore(path))
            s1.execute("find python")
            # Simulate process restart: new AgentService with same store
            s2 = AgentService(r, session_store=SessionStore(path))
            r2 = s2.execute("open the first one")
            assert r2["action"] == "open"
            assert r2["target"] == "z.md"

    def test_agent_without_session_store_stateless(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "n.md"}])
        svc = AgentService(r)  # no session_store
        svc.execute("find python")
        # new instance has no memory
        svc2 = AgentService(r)
        r2 = svc2.execute("open the first one")
        assert r2.get("ok") is False  # unknown command (no last_find)

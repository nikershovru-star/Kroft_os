"""Stage 41 - Conversation history & contextual shortcuts tests (5)."""
from __future__ import annotations

import os
import tempfile

import pytest

from services import AgentService, SessionStore, ToolRegistry


class TestConversation:
    def test_again_repeats_last_command(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "a.md"}])
        session = SessionStore()
        svc = AgentService(r, session_store=session)
        svc.execute("find python")
        r2 = svc.execute("again")
        assert r2["tool"] == "list_notes"

    def test_more_uses_last_query(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "b.md"}])
        session = SessionStore()
        svc = AgentService(r, session_store=session)
        svc.execute("find python")
        r2 = svc.execute("more")
        assert r2["tool"] == "list_notes"
        assert r2["query"] == "find python"  # last_query heuristic

    def test_bare_show_resolves_last_find(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "c.md"}])
        r.register("show_note", lambda query, top_k=1: {"id": query, "content": "# C"})
        session = SessionStore()
        svc = AgentService(r, session_store=session)
        svc.execute("find python")
        r2 = svc.execute("show")
        assert r2["tool"] == "show_note"
        assert r2["result"]["id"] == "c.md"

    def test_turns_persisted_in_session(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "d.md"}])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sess.json")
            session = SessionStore(path)
            svc = AgentService(r, session_store=session)
            svc.execute("find python")
            turns = session.get_turns()
            assert len(turns) == 1
            assert turns[0]["action"] == "list_notes"

    def test_no_context_returns_error(self):
        r = ToolRegistry()
        svc = AgentService(r, session_store=SessionStore())
        r2 = svc.execute("again")
        assert r2.get("ok") is False
        assert "no conversation context" in r2.get("error", "")

"""Stage 42 - Agent batch script execution tests (5)."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from services import AgentService, SessionStore, ToolRegistry


class TestAgentBatch:
    def test_batch_executes_sequence(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "a.md"}])
        r.register("show_note", lambda query, top_k=1: {"id": query, "content": "# A"})
        svc = AgentService(r, session_store=SessionStore())
        results = svc.execute_batch(["find python", "show"])
        assert len(results) == 2
        assert results[0]["tool"] == "list_notes"
        assert results[1]["tool"] == "show_note"

    def test_batch_stop_on_error(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "a.md"}])
        svc = AgentService(r, session_store=SessionStore())
        results = svc.execute_batch(["find python", "again", "again"])  # again after no context = error
        # second again fails (no context after first again consumed nothing)
        # Actually: find -> ok; again -> find (ok); again -> find (ok). Let's use unknown command.
        results = svc.execute_batch(["find python", "bad_command_xyz"])
        assert len(results) == 2  # stopped on error
        assert results[0]["ok"] is True
        assert results[1]["ok"] is False

    def test_batch_continue_on_error(self):
        r = ToolRegistry()
        svc = AgentService(r, session_store=SessionStore())
        results = svc.execute_batch(["bad_command_1", "bad_command_2"], continue_on_error=True)
        assert len(results) == 2
        assert results[0]["ok"] is False
        assert results[1]["ok"] is False

    def test_batch_session_context_shared(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "b.md"}])
        r.register("show_note", lambda query, top_k=1: {"id": query, "content": "# B"})
        svc = AgentService(r, session_store=SessionStore())
        results = svc.execute_batch(["find python", "show"])
        # "show" (bare) resolves last_find from step 1 within same batch
        assert results[1]["tool"] == "show_note"
        assert results[1]["result"]["id"] == "b.md"

    def test_batch_reads_jsonl_file(self):
        r = ToolRegistry()
        r.register("list_notes", lambda query, top_k=1: [{"id": "c.md"}])
        svc = AgentService(r, session_store=SessionStore())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
            f.write(json.dumps({"command": "find python"}) + "\n")
            f.write(json.dumps({"command": "again"}) + "\n")
            path = f.name
        try:
            with open(path, "r", encoding="utf-8") as f:
                commands = [json.loads(line)["command"] for line in f if line.strip()]
            results = svc.execute_batch(commands)
            assert len(results) == 2
            assert results[0]["tool"] == "list_notes"
            assert results[1]["tool"] == "list_notes"  # again repeats find
        finally:
            os.unlink(path)

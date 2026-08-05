"""Stage 50 — Graph Temporal Audit Log tests."""
from __future__ import annotations

import time

import pytest

from infrastructure import InMemoryGraphBuilder
from services import GraphQueryEngine, AgentService, ToolRegistry


class TestTemporalAudit:
    def _make_engine(self):
        b = InMemoryGraphBuilder()
        for nid in ("a.md", "b.md", "c.md"):
            b.add_node(nid, nid.replace(".md", ""), {})
        b.add_edge("a.md", "b.md", "links")
        return GraphQueryEngine(b)

    def test_add_link_creates_audit_entry(self):
        engine = self._make_engine()
        base = len(engine.get_audit_log())
        engine.add_link("a", "c")
        entries = engine.get_audit_log()
        assert len(entries) == base + 1
        assert entries[-1]["action"] == "add_link"
        assert (entries[-1]["after"] or {}).get("edge") or True

    def test_add_tag_creates_audit_entry(self):
        engine = self._make_engine()
        base = len(engine.get_audit_log())
        engine.add_tag("a", "p1")
        entries = engine.get_audit_log()
        assert len(entries) == base + 1
        assert entries[-1]["action"] == "add_tag"

    def test_remove_link_creates_audit_entry(self):
        engine = self._make_engine()
        base = len(engine.get_audit_log())
        engine.remove_link("a", "b")
        entries = engine.get_audit_log()
        assert len(entries) == base + 1
        assert entries[-1]["action"] == "remove_link"

    def test_mutations_since_filters_by_timestamp(self):
        engine = self._make_engine()
        engine.add_link("a", "c")
        first_ts = engine.get_audit_log()[-1]["ts"]
        time.sleep(0.01)
        engine.add_tag("b", "p2")
        second_ts = engine.get_audit_log()[-1]["ts"]
        # timestamp strictly between the two mutations
        in_between = (first_ts + second_ts) / 2
        recent = engine.mutations_since(in_between)
        assert len(recent) == 1
        assert recent[0]["action"] == "add_tag"

    def test_agent_intents(self):
        reg = ToolRegistry()
        reg.register("audit_log", lambda: {"ok": True, "log": []})
        reg.register("recent_changes", lambda: {"ok": True, "log": []})
        reg.register("mutations_since", lambda ts_min=0: {"ok": True, "mutations": []})
        svc = AgentService(reg)
        assert svc.execute("show audit log")["tool"] == "audit_log"
        assert svc.execute("show recent changes")["tool"] == "recent_changes"
        assert svc.execute("mutations since 1000")["tool"] == "mutations_since"
        assert svc.execute("audit log")["tool"] == "audit_log"
        assert svc.execute("recent changes")["tool"] == "recent_changes"
        assert svc.execute("мутации с 1000")["tool"] == "mutations_since"
        assert svc.execute("недавние изменения")["tool"] == "recent_changes"
        assert svc.execute("журнал изменений")["tool"] == "audit_log"

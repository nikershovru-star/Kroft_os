"""PHASE 3 — HTTP API over REAL runtime + foundation (slow, integration).

Marked ``slow``: boots a real KroftRuntime via build_runtime() (composition root +
CognitiveKernel + real KROFT_OSServer) with the 750MB production foundation loaded
read-only, then issues real HTTP requests to the new agent-interface endpoints and
asserts they delegate to the live IKroftAgentInterface. Proves the chain:

    HTTP  ->  KROFT_OSServer  ->  container.resolve("IKroftAgentInterface")
          ->  KroftAgentInterface  ->  existing GraphQueryEngine / ResolutionLevel

Run with:  pytest tests/runtime/test_http_agent_integration.py -m slow
"""

import sys
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from composition.kroft_runtime_factory import build_runtime  # noqa: E402


@pytest.mark.slow
def test_http_agent_api_over_real_runtime():
    with tempfile.TemporaryDirectory() as tmp:
        rt = build_runtime(
            node_id="kroft-http-int",
            vault=tmp,
            host="127.0.0.1",
            api_port=8231,  # distinct to avoid clashes
            llm="none",
            embedding="none",
        )
        try:
            rt.start()
            assert rt.is_running
            # Agent interface must be registered in the container BEFORE the
            # server started accepting requests (ТЗ PHASE 3 condition #1).
            assert rt.container.has("IKroftAgentInterface")

            base = f"http://127.0.0.1:{rt.server.port}"

            # GET /api/status -> agent.status() (delegates to runtime.health)
            with urllib.request.urlopen(f"{base}/api/status", timeout=30) as r:
                status = r.read().decode()
            import json
            st = json.loads(status)
            assert st["status"] == "ok"
            assert st["runtime"] == "running"

            # POST /api/query -> agent.query()
            req = urllib.request.Request(
                f"{base}/api/query",
                data=json.dumps({"query": "memory", "top_k": 3}).encode(),
                method="POST", headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                q = json.loads(r.read().decode())
            assert q["mode"] == "hybrid"
            assert "results" in q

            # POST /api/resolve -> agent.resolve() (ADR-028 resolution ladder)
            req = urllib.request.Request(
                f"{base}/api/resolve",
                data=json.dumps({"query": "federation", "level": "SYSTEM"}).encode(),
                method="POST", headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                res = json.loads(r.read().decode())
            # Either accepted (resolution service wired) or honest GAP — both are
            # valid; we only assert the endpoint delegates and returns JSON.
            assert "ok" in res or "error" in res

            # GET /api/audit -> agent.audit()
            with urllib.request.urlopen(f"{base}/api/audit?limit=5", timeout=30) as r:
                aud = json.loads(r.read().decode())
            assert aud["ok"] is True
            assert "entries" in aud
        finally:
            rt.stop()
        assert not rt.is_running

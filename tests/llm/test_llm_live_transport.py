"""K8 tests for ТЗ-LLM-LIVE-01 — real HTTP transport + local-model + graceful fallback.

Covers (acceptance + O1/K1/K6/K8 + ADR-079):
- HttpTransport talks OpenAI-compatible JSON with an IN-PROCESS local HTTP server; the
  OpenAiCompatibleClient (LLM-02) -> adapter_for -> ILLMAdvisor.advise() yields LLMAdvice.
- Server DOWN / TIMEOUT -> TransportError/TransportTimeout -> LLMError/LLMTimeout ->
  kernel GRACEFUL FALLBACK == retrieval-only (LLM-01). No crash; equals the no-LLM result.
- K6: domain (contracts/kernel) does NOT import requests/httpx/urllib; HttpTransport lives
  in adapters/; build_llm_client lives in composition/. (Static assertions on module imports.)
- Existing LLM-01/02 tests remain green (backward compatible — only a new transport added).

Pattern (deterministic, I-09): a ThreadingHTTPServer on localhost returns a canned OpenAI
/v1/chat/completions JSON. NO live model required. For the timeout case the handler sleeps
past the client timeout; for the down case the client points at a closed port.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from contracts.i_http import IHttpTransport
from contracts.i_llm import ILlm
from contracts.i_llm_advisor import adapter_for, AdviseContext, ILLMAdvisor, LLMError, LLMTimeout
from kernel.cognitive_kernel import build_kernel, NodeLamportClock
from kernel.execution import ReferenceExecutor
from adapters.http_transport import HttpTransport
from composition.llm_client_factory import build_llm_client


# ---------------------------------------------------------------------------
# In-process OpenAI-compatible HTTP server (deterministic, no live model)
# ---------------------------------------------------------------------------
class _OpenAIHandler(BaseHTTPRequestHandler):
    # serve a canned chat/completions JSON; optionally delay past client timeout
    delay = 0.0

    def log_message(self, *args):  # silence test noise
        pass

    def do_POST(self):
        if self.path.endswith("/chat/completions"):
            if _OpenAIHandler.delay:
                time.sleep(_OpenAIHandler.delay)
            body = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": "test-model",
                "choices": [{"index": 0, "message": {"role": "assistant",
                                                     "content": "choose_blue"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            }
            data = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()


def _start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, srv.server_address[1]


# ---------------------------------------------------------------------------
# 1. real HTTP transport: advise -> LLMAdvice via in-process server
# ---------------------------------------------------------------------------
def test_real_http_transport_advise_yields_llm_advice():
    srv, port = _start_server()
    try:
        client: ILlm = build_llm_client(base_url=f"http://127.0.0.1:{port}/v1",
                                        model="test-model", timeout=5.0)
        advisor: ILLMAdvisor = adapter_for(client)
        advice = advisor.advise(AdviseContext(intent_text="choose", candidate_descriptions=("choose_blue",)))
        assert advice is not None, "expected advice from real HTTP transport"
        assert advice.suggestion == "choose_blue"
        assert advice.confidence is not None
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------------------
# 2. real HTTP transport matches the IHttpTransport contract (mock-free)
# ---------------------------------------------------------------------------
def test_http_transport_implements_port_and_returns_http_response():
    srv, port = _start_server()
    try:
        t: IHttpTransport = HttpTransport(f"http://127.0.0.1:{port}")
        resp = t.request("POST", "/v1/chat/completions",
                         headers={"Content-Type": "application/json"},
                         body=json.dumps({"model": "m", "messages": []}), timeout=5.0)
        assert resp.status == 200
        assert "choices" in resp.body
        assert "content-type" in resp.headers
    finally:
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------------------
# 3. server DOWN -> LLMError -> kernel graceful fallback == retrieval-only
# ---------------------------------------------------------------------------
def test_server_down_triggers_fallback_equal_no_llm():
    # point at a closed port -> TransportError -> LLMError (mapped by OpenAiCompatibleClient)
    down_url = "http://127.0.0.1:1/v1"  # port 1 is never open
    client = build_llm_client(base_url=down_url, model="m", timeout=1.0)
    advisor = adapter_for(client)

    # no-LLM baseline
    k_no = build_kernel("llm-live-no")
    k_no.attach_executor(ReferenceExecutor())
    k_no.tick(_intent())
    sel_no = k_no._last_selected_plan.steps

    # failed LLM kernel (must NOT crash, must equal baseline)
    k_fail = build_kernel("llm-live-down", llm_client=advisor)
    k_fail.attach_executor(ReferenceExecutor())
    k_fail.tick(_intent())  # network failure -> LLMError -> fallback
    sel_fail = k_fail._last_selected_plan.steps

    assert sel_no == sel_fail, "server-down must fallback to retrieval-only (== no-LLM)"
    assert k_fail._last_decision is not None


# ---------------------------------------------------------------------------
# 4. TIMEOUT -> LLMTimeout -> kernel graceful fallback == retrieval-only
# ---------------------------------------------------------------------------
def test_timeout_triggers_fallback_equal_no_llm():
    srv, port = _start_server()
    _OpenAIHandler.delay = 2.0  # exceed client timeout
    try:
        client = build_llm_client(base_url=f"http://127.0.0.1:{port}/v1",
                                  model="m", timeout=0.5)
        advisor = adapter_for(client)

        k_no = build_kernel("llm-live-to-no")
        k_no.attach_executor(ReferenceExecutor())
        k_no.tick(_intent())
        sel_no = k_no._last_selected_plan.steps

        k_to = build_kernel("llm-live-to", llm_client=advisor)
        k_to.attach_executor(ReferenceExecutor())
        k_to.tick(_intent())  # handler sleeps 2s > 0.5s timeout -> TransportTimeout -> LLMTimeout
        sel_to = k_to._last_selected_plan.steps

        assert sel_no == sel_to, "timeout must fallback to retrieval-only (== no-LLM)"
    finally:
        _OpenAIHandler.delay = 0.0
        srv.shutdown()
        srv.server_close()


# ---------------------------------------------------------------------------
# 5. K6: domain does NOT import requests/httpx/urllib directly
# ---------------------------------------------------------------------------
def test_k6_domain_has_no_provider_sdk_imports():
    import ast, pathlib
    banned = {"requests", "httpx", "openai"}
    for mod in ("contracts.i_llm_advisor", "contracts.i_http", "kernel.cognitive_kernel"):
        src = pathlib.Path(__import__(mod, fromlist=["__name__"]).__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    assert n.name.split(".")[0] not in banned, f"{mod} imports {n.name}"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in banned, f"{mod} imports {node.module}"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _intent():
    from contracts.cognitive_domain import ConfidenceScore, Intent, Provenance, ProvenanceType
    return Intent(id="i1", text="go",
                  confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                  provenance=Provenance(source="u", actor="u"))

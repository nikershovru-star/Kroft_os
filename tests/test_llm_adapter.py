"""Model Platform MVP tests (candidate ADR-033).

- Contract tests: mock transport, no network.
- Golden test: real keyless `auto` ping to a running OmniRoute gateway
  (skipped automatically when the gateway is not up).
"""
import os
import time

import pytest

from contracts.i_llm import ILlm, IModelMetadata, IHealth, ModelQuery, LlmResponse
from adapters.model_platform import OpenAiCompatibleClient
from adapters.omni_route_adapter import OmniRouteAdapter, _select_model


# ---- contract: adapter implements all three ports -------------------------
def test_omniroute_implements_ports():
    a = OmniRouteAdapter()
    assert isinstance(a, ILlm)
    assert isinstance(a, IModelMetadata)
    assert isinstance(a, IHealth)


# ---- contract: LlmResponse shape (observability fields present) -----------
def test_llm_response_carries_observability_fields():
    r = LlmResponse(text="hi", trace_id="t1", provider="p", model="m", actual_model="m", tokens=3)
    assert r.ok()
    assert r.trace_id and r.provider and r.model and r.actual_model
    assert r.latency_ms == 0.0 and r.cost == 0.0


def test_llm_response_error_not_ok():
    r = LlmResponse(text="", error="boom")
    assert not r.ok()


# ---- routing: ModelQuery dimensions map to a concrete model --------------
def test_select_model_default_is_reasoning_free():
    assert _select_model(ModelQuery(task="reasoning")) == "Qoder/Kimi-K2-Free"


def test_select_model_cheap_uses_pollinations():
    assert _select_model(ModelQuery(task="cheap", cheap=True)) == "Pollinations"


def test_select_model_json_uses_openrouter_free():
    assert _select_model(ModelQuery(json_mode=True)) == "OpenRouter:free"


def test_select_model_preferred_wins():
    assert _select_model(ModelQuery(preferred_provider="X/Y")) == "X/Y"


# ---- metadata: declared catalog is populated ------------------------------
def test_omniroute_catalog_has_free_models():
    a = OmniRouteAdapter()
    cat = a.catalog()
    assert len(cat) >= 4
    assert all(m.free for m in cat)
    assert a.capabilities("Pollinations").provider == "omniroute"


# ---- client: mock transport, no network ----------------------------------
class _FakeClient(OpenAiCompatibleClient):
    def __init__(self):
        super().__init__()
        self.last_payload = None

    def _post(self, path, payload):
        self.last_payload = payload
        return {
            "model": payload["model"],
            "choices": [{"message": {"content": "hello from " + payload["model"]}}],
            "usage": {"total_tokens": 7},
        }


def test_complete_returns_normalized_response():
    c = _FakeClient()
    r = c.complete(ModelQuery(prompt="hi", preferred_provider="OpenCode Zen"))
    assert r.ok()
    assert r.text == "hello from OpenCode Zen"
    assert r.model == "OpenCode Zen"
    assert r.actual_model == "OpenCode Zen"   # double-routing resolved
    assert r.tokens == 7


def test_complete_json_mode_sets_response_format():
    c = _FakeClient()
    c.complete(ModelQuery(prompt="p", json_mode=True, preferred_provider="OpenRouter:free"))
    assert c.last_payload["response_format"] == {"type": "json_object"}


def test_complete_normalizes_errors():
    class _Boomy(OpenAiCompatibleClient):
        def _post(self, path, payload):
            raise RuntimeError("gateway down")
    r = _Boomy().complete(ModelQuery(prompt="x"))
    assert not r.ok()
    assert "gateway down" in (r.error or "")


def test_omniroute_routes_as_dumb_pipe():
    class _Spy(OmniRouteAdapter):
        def __init__(self):
            super().__init__()
            self.sent_model = None
        def _post(self, path, payload):
            self.sent_model = payload["model"]
            return {"model": payload["model"], "choices": [{"message": {"content": "ok"}}], "usage": {}}
    s = _Spy()
    s.complete(ModelQuery(task="cheap"))
    assert s.sent_model == "Pollinations"   # Hermes chose, not OmniRoute auto


# ---- golden: real keyless ping (skipped if no gateway) --------------------
OMNIROUTE_URL = os.environ.get("OMNIROUTE_URL", "http://localhost:20128/v1")


@pytest.mark.skipif(
    os.environ.get("OMNIROUTE_LIVE") != "1",
    reason="set OMNIROUTE_LIVE=1 with a running gateway to run the live keyless ping",
)
def test_golden_keyless_auto_ping():
    a = OmniRouteAdapter(base_url=OMNIROUTE_URL)
    assert a.ping(), f"OmniRoute not reachable at {OMNIROUTE_URL}"
    r = a.complete(ModelQuery(prompt="Say the single word: pong", preferred_provider="auto"))
    assert r.ok(), r.error
    assert r.text.strip()
    assert r.actual_model, "double-routing: actual_model must be reported"

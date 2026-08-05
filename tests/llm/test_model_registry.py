"""Wave 3 (Ollama) + Wave 4 (ModelRegistry) tests (candidate ADR-033).

- Contract tests: mock transport, no network.
- Golden tests: real pings to local Ollama (skipped if not running) and
  aggregate the OmniRoute + Ollama catalogs through the registry.
"""
import os

import pytest

from contracts.i_llm import IModelMetadata, ModelQuery
from contracts.model_registry import ModelRegistry
from adapters.model_platform import OpenAiCompatibleClient
from adapters.omni_route_adapter import OmniRouteAdapter, _select_model
from adapters.ollama_adapter import OllamaAdapter, _select_local_model


# ---- Wave 3: OllamaAdapter ------------------------------------------------
def test_ollama_implements_ports():
    a = OllamaAdapter()
    assert isinstance(a, IModelMetadata)


def test_ollama_default_base_url():
    assert OllamaAdapter().base_url == "http://localhost:11434/v1"


def test_ollama_local_routing():
    assert _select_local_model(ModelQuery(reasoning=True)) == "phi4"
    assert _select_local_model(ModelQuery(json_mode=True)) == "qwen2.5"
    assert _select_local_model(ModelQuery(cheap=True)) == "llama3.2"
    assert _select_local_model(ModelQuery(task="reasoning")) == "llama3.2"


def test_ollama_catalog_all_local():
    cat = OllamaAdapter().catalog()
    assert len(cat) >= 4
    assert all(m.local for m in cat)


def test_ollama_forces_local_flag():
    class _Spy(OllamaAdapter):
        def __init__(self):
            super().__init__()
            self.sent = None
        def _post(self, path, payload):
            self.sent = payload["model"]
            return {"model": payload["model"], "choices": [{"message": {"content": "ok"}}], "usage": {}}
    s = _Spy()
    s.complete(ModelQuery(task="reasoning", local=False))  # input says online
    assert s.sent == "llama3.2"  # but adapter forced a local model


# ---- Wave 4: ModelRegistry aggregates sources ----------------------------
def test_registry_aggregates_omniroute_and_ollama():
    reg = ModelRegistry()
    reg.register_source(OmniRouteAdapter())
    reg.register_source(OllamaAdapter())
    cat = reg.catalog()
    ids = {m.id for m in cat}
    assert "Qoder/Kimi-K2-Free" in ids
    assert "llama3.2" in ids
    assert any(m.provider == "omniroute" for m in cat)
    assert any(m.provider == "ollama" for m in cat)


def test_registry_select_reasoning_online():
    reg = ModelRegistry()
    reg.register_source(OmniRouteAdapter())
    reg.register_source(OllamaAdapter())
    chosen = reg.select(ModelQuery(reasoning=True, local=False))
    assert chosen is not None
    assert chosen.reasoning is True
    # online + reasoning -> an omniroute free model, not a local one
    assert chosen.provider == "omniroute"


def test_registry_select_local_only():
    reg = ModelRegistry()
    reg.register_source(OmniRouteAdapter())
    reg.register_source(OllamaAdapter())
    chosen = reg.select(ModelQuery(reasoning=False, local=True))
    assert chosen is not None
    assert chosen.local is True
    assert chosen.provider == "ollama"


def test_registry_select_no_match_returns_none():
    reg = ModelRegistry()
    reg.register_source(OllamaAdapter())
    # ask for a 10M context window — no declared model satisfies it
    assert reg.select(ModelQuery(context_window=10_000_000)) is None


# ---- golden: live Ollama ping (skipped if gateway down) ------------------
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/v1")


@pytest.mark.skipif(
    os.environ.get("OLLAMA_LIVE") != "1",
    reason="set OLLAMA_LIVE=1 with a running Ollama to run the live local ping",
)
def test_golden_ollama_ping():
    a = OllamaAdapter(base_url=OLLAMA_URL)
    assert a.ping(), f"Ollama not reachable at {OLLAMA_URL}"
    r = a.complete(ModelQuery(prompt="Say the single word: pong", preferred_provider="llama3.2"))
    assert r.ok(), r.error
    assert r.text.strip()
    assert r.actual_model

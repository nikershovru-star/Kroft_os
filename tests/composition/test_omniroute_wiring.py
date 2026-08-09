"""OmniRoute gateway wiring proof (ТЗ-OMNI-01) — no network, no new port/adapter.

Verifies that the OmniRoute LLM gateway is reachable through the EXISTING
OpenAiCompatibleClient (K5 reuse): build_omniroute_client() and the
KroftConfig(llm="omniroute") path both yield an OpenAiCompatibleClient pointed
at the gateway with the combo name as the model routing-key.

No real calls to OmniRoute are made — we only assert wiring (type + base_url +
model). Network I/O happens lazily inside .complete(), which is never invoked.
"""

from __future__ import annotations

from adapters.openai_compatible import OpenAiCompatibleClient
from composition.llm_client_factory import build_omniroute_client
from composition.run_kroft import KroftApp, KroftConfig


def test_omniroute_factory_returns_client():
    """build_omniroute_client() returns an OpenAiCompatibleClient wired to the gateway."""
    client = build_omniroute_client()
    assert isinstance(client, OpenAiCompatibleClient), type(client)
    # combo name is the model routing-key; gateway is the base_url
    # (OpenAiCompatibleClient stores them as private attrs — assert the values
    # build_omniroute_client passed through, proving K5 reuse without a new adapter)
    assert getattr(client, "_base_url", None) == "http://localhost:3000/v1", client._base_url
    assert getattr(client, "_model", None) == "kroft-free", client._model


def test_omniroute_factory_custom_combo():
    client = build_omniroute_client(combo="kroft-deep", gateway="http://localhost:3000/v1")
    assert isinstance(client, OpenAiCompatibleClient)
    assert getattr(client, "_model", None) == "kroft-deep"
    assert getattr(client, "_base_url", None) == "http://localhost:3000/v1"


def test_omniroute_config_wires_llm():
    """KroftApp(KroftConfig(llm='omniroute')) wires an OpenAiCompatibleClient as app.llm."""
    app = KroftApp(KroftConfig(node_id="t-omni", llm="omniroute", ticks=0))
    assert isinstance(app.llm, OpenAiCompatibleClient), type(app.llm)
    assert getattr(app.llm, "_base_url", None) == "http://localhost:3000/v1", app.llm._base_url
    assert getattr(app.llm, "_model", None) == "kroft-free", app.llm._model

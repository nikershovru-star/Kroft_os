"""OmniRoute Model Platform adapter (MVP, candidate ADR-033).

OmniRoute = keyless free AI gateway: one endpoint, 290+ providers, 500+ models.
In MVP it runs as a DUMB-PIPE: we (Hermes) are the only router — we map a
ModelQuery to a concrete model and send it; OmniRoute's internal `auto` is NOT
used for routing decisions here. Double-routing is resolved by reading
`actual_model` back from the response (already done in OpenAiCompatibleClient).

Later (Wave 6): allow OmniRoute's `auto`, parse the `X-OmniRoute-Decision`
response header and surface provider/model in LlmResponse.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from contracts.i_llm import ModelInfo, ModelQuery
from adapters.model_platform import OpenAiCompatibleClient

# Declared free models available through OmniRoute (capability discovery src 1/3).
# Kept minimal for MVP; the registry (Wave 4) will expand this.
OMNIROUTE_FREE_MODELS: List[ModelInfo] = [
    ModelInfo(id="Qoder/Kimi-K2-Free", provider="omniroute", reasoning=True, context_window=128000, free=True),
    ModelInfo(id="OpenCode Zen", provider="omniroute", reasoning=True, context_window=64000, free=True),
    ModelInfo(id="Pollinations", provider="omniroute", reasoning=False, context_window=32000, free=True),
    ModelInfo(id="OpenRouter:free", provider="omniroute", reasoning=True, context_window=128000, free=True),
]

# Simple rule-based mapping from ModelQuery dimensions to a concrete model.
# Single source of routing truth in MVP (Hermes = router).
def _select_model(query: ModelQuery) -> str:
    if query.preferred_provider:
        return query.preferred_provider
    if query.local:
        return "Qoder/Kimi-K2-Free"
    if query.cheap or query.task == "cheap":
        return "Pollinations"
    if query.json_mode:
        return "OpenRouter:free"
    # default: a reasoning-capable free model
    return "Qoder/Kimi-K2-Free"


class OmniRouteAdapter(OpenAiCompatibleClient):
    """OpenAI-compatible client pointed at a local OmniRoute gateway."""

    def __init__(
        self,
        base_url: str = "http://localhost:20128/v1",
        api_key: str = "[REDACTED]",
        model: str = "auto",
        timeout: float = 60.0,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, model=model, timeout=timeout)
        for m in OMNIROUTE_FREE_MODELS:
            self.register_model(m)

    def complete(self, query: ModelQuery):
        # MVP: Hermes routes — override the requested model with our choice.
        routed = ModelQuery(
            task=query.task,
            reasoning=query.reasoning,
            local=query.local,
            json_mode=query.json_mode,
            cheap=query.cheap,
            context_window=query.context_window,
            preferred_provider=_select_model(query),
            prompt=query.prompt,
        )
        return super().complete(routed)

    def stream(self, query: ModelQuery):
        routed = ModelQuery(
            task=query.task,
            reasoning=query.reasoning,
            local=query.local,
            json_mode=query.json_mode,
            cheap=query.cheap,
            context_window=query.context_window,
            preferred_provider=_select_model(query),
            prompt=query.prompt,
        )
        yield from super().stream(routed)

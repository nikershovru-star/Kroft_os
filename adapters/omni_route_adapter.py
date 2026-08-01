"""OmniRoute Model Platform adapter (MVP + Wave 6, candidate ADR-033).

OmniRoute = keyless free AI gateway: one endpoint, 290+ providers, 500+ models.

Two operating modes (double-routing resolution, see ADR-033):
- `dumb_pipe=True` (MVP / default): Hermes is the ONLY router. We map a
  ModelQuery to a concrete model via `_select_model` and send it; OmniRoute's
  internal `auto` is NOT used for routing. `actual_model` = what we sent.
- `dumb_pipe=False` (Wave 6): we let OmniRoute route via its `auto` strategy and
  treat its response headers (X-OmniRoute-Model / X-OmniRoute-Provider /
  X-OmniRoute-Decision) as the authoritative second source of truth. The gateway
  genuinely chose the model, so `actual_model`/`actual_provider` come from the
  headers, not from our request.
"""
from __future__ import annotations

from typing import Iterator, List

from contracts.i_llm import ModelInfo, ModelQuery
from adapters.model_platform import OpenAiCompatibleClient

# Declared free models available through OmniRoute (capability discovery src 1/3).
OMNIROUTE_FREE_MODELS: List[ModelInfo] = [
    ModelInfo(id="Qoder/Kimi-K2-Free", provider="omniroute", reasoning=True, context_window=128000, free=True),
    ModelInfo(id="OpenCode Zen", provider="omniroute", reasoning=True, context_window=64000, free=True),
    ModelInfo(id="Pollinations", provider="omniroute", reasoning=False, context_window=32000, free=True),
    ModelInfo(id="OpenRouter:free", provider="omniroute", reasoning=True, context_window=128000, free=True),
]

# Simple rule-based mapping from ModelQuery dimensions to a concrete model.
# Single source of routing truth in dumb-pipe mode (Hermes = router).
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
        dumb_pipe: bool = True,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, model=model, timeout=timeout)
        self.dumb_pipe = dumb_pipe
        for m in OMNIROUTE_FREE_MODELS:
            self.register_model(m)

    def _resolve(self, query: ModelQuery) -> ModelQuery:
        """Apply Hermes-side routing only in dumb-pipe mode.

        In Wave 6 mode (dumb_pipe=False) we pass the query through with model
        "auto" and let the gateway route — its decision comes back in headers.
        """
        if self.dumb_pipe:
            return ModelQuery(
                task=query.task,
                reasoning=query.reasoning,
                local=query.local,
                json_mode=query.json_mode,
                cheap=query.cheap,
                context_window=query.context_window,
                preferred_provider=_select_model(query),
                prompt=query.prompt,
            )
        # gateway routes: keep user's preferred_provider if given, else "auto"
        model = query.preferred_provider or "auto"
        return ModelQuery(
            task=query.task,
            reasoning=query.reasoning,
            local=query.local,
            json_mode=query.json_mode,
            cheap=query.cheap,
            context_window=query.context_window,
            preferred_provider=model,
            prompt=query.prompt,
        )

    def complete(self, query: ModelQuery):
        return super().complete(self._resolve(query))

    def stream(self, query: ModelQuery) -> Iterator[str]:
        yield from super().stream(self._resolve(query))

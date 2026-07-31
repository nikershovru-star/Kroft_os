"""Ollama Model Platform adapter (Wave 3, candidate ADR-033).

Local, offline-capable OpenAI-compatible backend. Inherits OpenAiCompatibleClient
exactly like OmniRouteAdapter — only the base_url and declared catalog differ.
This gives Model Platform its second pole: OmniRoute = free online, Ollama =
local offline. Together they make the Wave 4 Registry meaningful (2+ sources).
"""
from __future__ import annotations

from typing import List

from contracts.i_llm import ModelInfo, ModelQuery
from adapters.model_platform import OpenAiCompatibleClient

# Declared local models (capability discovery src 1/3). Expand as installed.
OLLAMA_LOCAL_MODELS: List[ModelInfo] = [
    ModelInfo(id="llama3.2", provider="ollama", local=True, context_window=128000, free=True),
    ModelInfo(id="phi4", provider="ollama", local=True, reasoning=True, context_window=16000, free=True),
    ModelInfo(id="qwen2.5", provider="ollama", local=True, context_window=32000, free=True),
    ModelInfo(id="mistral", provider="ollama", local=True, context_window=32000, free=True),
]


def _select_local_model(query: ModelQuery) -> str:
    """Local-first routing: pick the smallest model that satisfies the ask."""
    if query.preferred_provider:
        return query.preferred_provider
    if query.reasoning:
        return "phi4"
    if query.json_mode:
        return "qwen2.5"
    if query.cheap:
        return "llama3.2"
    # default: small general model
    return "llama3.2"


class OllamaAdapter(OpenAiCompatibleClient):
    """OpenAI-compatible client pointed at a local Ollama gateway."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "[REDACTED]",
        model: str = "llama3.2",
        timeout: float = 120.0,
    ) -> None:
        super().__init__(base_url=base_url, api_key=api_key, model=model, timeout=timeout)
        for m in OLLAMA_LOCAL_MODELS:
            self.register_model(m)

    def complete(self, query: ModelQuery):
        routed = ModelQuery(
            task=query.task,
            reasoning=query.reasoning,
            local=True,  # force local flag regardless of input
            json_mode=query.json_mode,
            cheap=query.cheap,
            context_window=query.context_window,
            preferred_provider=_select_local_model(query),
            prompt=query.prompt,
        )
        return super().complete(routed)

    def stream(self, query: ModelQuery):
        routed = ModelQuery(
            task=query.task,
            reasoning=query.reasoning,
            local=True,
            json_mode=query.json_mode,
            cheap=query.cheap,
            context_window=query.context_window,
            preferred_provider=_select_local_model(query),
            prompt=query.prompt,
        )
        yield from super().stream(routed)

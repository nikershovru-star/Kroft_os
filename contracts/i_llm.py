"""ILlm — language-model port (Model Platform MVP, candidate ADR-033).

Adapters (OpenAiCompatibleClient, OmniRouteAdapter, OllamaAdapter) implement
this port; domain services depend only on the abstraction.

Arch rule (inherited from the rest of contracts/): adapters may import
contracts + stdlib only. No `from openai import ...` in the domain layer.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Iterator, List, Optional


@dataclass
class ModelQuery:
    """Multi-dimensional routing hint — NOT a coarse TaskType enum.

    Lets the Router pick a model on several axes at once instead of a single
    REASONING/CHEAP switch. See Master Roadmap v2.0 / ADR-033.
    """

    task: str = "reasoning"          # reasoning | cheap | embed | json | local
    reasoning: bool = False
    local: bool = False
    json_mode: bool = False
    cheap: bool = False
    context_window: int = 0
    preferred_provider: Optional[str] = None
    prompt: str = ""


@dataclass
class LlmResponse:
    """Normalized response. `actual_model` is MANDATORY — it resolves the
    double-routing problem (who chose the model: us or the gateway?).

    When the gateway routes for us (Wave 6), `actual_provider` / `actual_model`
    / `decision` come from authoritative gateway headers (e.g.
    X-OmniRoute-Model / X-OmniRoute-Provider / X-OmniRoute-Decision) — the
    gateway is the second source of truth for observability & eval.
    """

    text: str
    trace_id: str = ""
    provider: str = ""            # requested provider/base_url
    model: str = ""               # requested model
    actual_provider: str = ""     # model that actually answered (gateway truth)
    actual_model: str = ""        # model that actually answered (gateway truth)
    decision: str = ""            # raw gateway routing decision, if any
    tokens: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: float = 0.0
    cost: float = 0.0             # 0.0 for keyless providers
    error: Optional[str] = None

    def ok(self) -> bool:
        return self.error is None


@dataclass
class ModelInfo:
    """Declared contract for a model (capability discovery, source 1/3)."""

    id: str
    provider: str
    reasoning: bool = False
    local: bool = False
    json_mode: bool = False
    context_window: int = 0
    free: bool = True
    cost_per_1k: float = 0.0     # USD per 1k tokens (0.0 for keyless/free) — ADR-009


class ILlm(abc.ABC):
    """Port: generate text / reasoning from a prompt."""

    @abc.abstractmethod
    def complete(self, query: ModelQuery) -> LlmResponse:
        """Run a single (non-streaming) completion."""
        raise NotImplementedError

    @abc.abstractmethod
    def stream(self, query: ModelQuery) -> Iterator[str]:
        """Yield completion chunks. Default impl wraps complete()."""
        raise NotImplementedError


class IModelMetadata(abc.ABC):
    """Port: declared model catalog (capability discovery, source 1/3)."""

    @abc.abstractmethod
    def catalog(self) -> List[ModelInfo]:
        raise NotImplementedError

    @abc.abstractmethod
    def capabilities(self, model_id: str) -> Optional[ModelInfo]:
        raise NotImplementedError


class IHealth(abc.ABC):
    """Port: provider liveliness (observability / circuit-breaker input)."""

    @abc.abstractmethod
    def ping(self) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def stats(self) -> dict:
        raise NotImplementedError

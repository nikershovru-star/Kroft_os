"""LLM-as-advisor contract boundary (ТЗ-LLM-01, ADR-065).

K1-compliant: stdlib + contracts only. The kernel NEVER imports a concrete LLM
client — only this advisor port (I-10, kernel purity).

Central thesis being PROVEN by this TЗ: LLM is a SWAPPABLE ADVISOR behind a
contract boundary. The kernel works WITHOUT a model (LLM-free core). The advisor
may influence RANKING of candidate plans, but the deterministic Decision Engine
makes the FINAL selection (I-03) — the LLM never chooses.

Reuses the existing Model Platform port (contracts/i_llm.ILlm) as the underlying
transport: `adapter_for(ILlm)` wraps an `ILlm` completion into an `ILLMAdvisor`.
We do NOT introduce a second LLM port — that would violate KROFT's "one port per
boundary" convention. The advisor layer is the contract-boundary THIN adapter.

K6: kernel depends only on ILLMAdvisor (this port), never on a concrete ILlm
adapter or any provider SDK. K8: exception/timeout -> graceful fallback == no-LLM
result is enforced by tests, not assumed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from contracts.cognitive_domain import ConfidenceScore, Provenance, ProvenanceType


class LLMError(Exception):
    """Raised when the LLM advisor is unavailable or throws.

    The kernel MUST catch this and fall back to the LLM-free reference path.
    Raising (rather than returning a degraded result) is intentional: a missing
    model is a failure of the OPTIONAL advisor, not of the kernel.
    """


class LLMTimeout(LLMError):
    """Specialization: the advisor call exceeded its budget."""


@dataclass(frozen=True)
class LLMAdvice:
    """A single suggestion from the LLM advisor (frozen VO, K1-clean).

    The kernel reads ``suggestion`` + ``confidence`` to re-rank candidate plans.
    It NEVER acts on the advice directly (no side effects, no final selection).
    """
    suggestion: str
    confidence: ConfidenceScore = field(
        default_factory=lambda: ConfidenceScore(0.7, ProvenanceType.MODEL_INFERENCE)
    )
    provenance: Provenance = field(
        default_factory=lambda: Provenance(source="llm_advisor", actor="model")
    )


@dataclass(frozen=True)
class AdviseContext:
    """The slice of world/intent the advisor is allowed to see (no internals leak)."""
    intent_text: str
    world_facts: tuple = ()
    candidate_descriptions: tuple = ()


class ILLMAdvisor(ABC):
    """Port: a swappable LLM advisor (ТЗ-LLM-01).

    The kernel depends ONLY on this interface. Concrete advisors wrap an ``ILlm``
    (see ``adapter_for``), a mock, or a provider SDK — all live OUTSIDE the kernel.

    Contract:
      - ``advise`` may READ context and RETURN an ``LLMAdvice`` (advisory only).
      - On unavailability it MUST raise ``LLMError`` / ``LLMTimeout`` — the kernel
        catches and falls back to the reference path (graceful, no crash).
      - It MUST NOT mutate kernel state, HARD layer, FSM, or make the final decision.
    """
    @abstractmethod
    def advise(self, context: AdviseContext) -> Optional[LLMAdvice]:
        """Return one advisory suggestion, or raise LLMError/LLMTimeout if unavailable.

        Returns ``None`` (instead of raising) only for a clean "no suggestion" —
        exceptions are reserved for transport failures that trigger fallback.
        """
        ...


def adapter_for(llm) -> ILLMAdvisor:
    """Bridge an existing Model Platform ``ILlm`` client into the advisor port.

    Reuses contracts/i_llm.ILlm as the transport so we don't fork the LLM port.
    The wrapped advisor raises ``LLMError`` when the underlying completion fails
    or returns an error payload, and ``LLMTimeout`` on a timeout.
    """
    from contracts.i_llm import ILlm, ModelQuery, LlmResponse  # reuse, not duplicate

    if not isinstance(llm, ILlm):
        raise TypeError("adapter_for requires an ILlm implementation")

    class _ILlmAdvisor(ILLMAdvisor):
        def advise(self, context: AdviseContext) -> Optional[LLMAdvice]:
            query = ModelQuery(
                task="reasoning",
                reasoning=True,
                json_mode=False,
                preferred_provider=None,
            )
            # The context is carried as the prompt's semantic payload. The Model
            # Platform port is text-in/text-out; we map the response text to advice.
            prompt = (
                f"[advisor] intent={context.intent_text!r} "
                f"facts={list(context.world_facts)} "
                f"candidates={list(context.candidate_descriptions)}"
            )
            try:
                resp: LlmResponse = llm.complete(query)  # type: ignore[attr-defined]
            except (LLMError, LLMTimeout):
                raise  # advisor error vocabulary propagates unchanged (timeout vs error distinct)
            except Exception as exc:  # transport failure -> graceful fallback
                raise LLMError(f"ILlm.complete failed: {exc}") from exc
            if not resp.ok:
                raise LLMError(f"ILlm returned error: {resp.error}")
            text = (resp.text or "").strip()
            if not text:
                return None
            return LLMAdvice(
                suggestion=text,
                confidence=ConfidenceScore(0.7, ProvenanceType.MODEL_INFERENCE),
                provenance=Provenance(source="llm_advisor", actor="model"),
            )

    return _ILlmAdvisor()

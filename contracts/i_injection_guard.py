"""PHASE D — IInjectionGuard contract (ТЗ Integration & Trust Closure §19-§23).

Minimal trust-boundary primitive proposed after forensic (ТЗ §23): the existing
codebase has NO injection guard — retrieved/external content flows into callers
without a trust classification. This contract encodes the rule from ТЗ §21:

    > Retrieved content is data, not authority.

It does NOT decide LLM behaviour (that stays in the LLM adapter / caller). It
ONLY classifies a piece of content by its trust origin so that context assembly
can mark untrusted content explicitly (e.g. wrap it, label it, refuse to treat
its text as instructions). K1-compliant: contracts + stdlib only.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Tuple


class TrustClass(str, Enum):
    """Conceptual trust classification (ТЗ §20, minimal model)."""

    SYSTEM_INSTRUCTION = "system_instruction"   # authoritative, kernel-owned
    TRUSTED_POLICY = "trusted_policy"           # validated internal policy
    INTERNAL_KNOWLEDGE = "internal_knowledge"   # graph / foundation (LOCAL)
    VALIDATED_FACT = "validated_fact"           # consolidated SOFT fact
    USER_CONTENT = "user_content"               # user-provided, scoped to user
    TOOL_OUTPUT = "tool_output"                 # sandbox/tool result
    UNTRUSTED_EXTERNAL = "untrusted_external"   # web/external search result
    LLM_GENERATED = "llm_generated"             # model output, not truth


# Source prefixes map to a TrustClass. External/search hits are UNTRUSTED.
_SOURCE_TRUST: Dict[str, TrustClass] = {
    "graph": TrustClass.INTERNAL_KNOWLEDGE,
    "semantic": TrustClass.VALIDATED_FACT,
    "episodic": TrustClass.INTERNAL_KNOWLEDGE,
    "normative": TrustClass.TRUSTED_POLICY,
    "external": TrustClass.UNTRUSTED_EXTERNAL,
    "web": TrustClass.UNTRUSTED_EXTERNAL,
}


def classify_source(source: str) -> TrustClass:
    """Map a SearchHit.source prefix to a TrustClass."""
    prefix = source.split(":", 1)[0].lower()
    return _SOURCE_TRUST.get(prefix, TrustClass.UNTRUSTED_EXTERNAL)


class IInjectionGuard:
    """Trust-boundary contract: classify + mark content (ТЗ §21, §23)."""

    def classify(self, source: str) -> TrustClass:
        raise NotImplementedError

    def is_authoritative(self, source: str) -> bool:
        """True only for content that may carry instructions (never external)."""
        return self.classify(source) in (
            TrustClass.SYSTEM_INSTRUCTION,
            TrustClass.TRUSTED_POLICY,
        )

    def mark_context(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return context entries with an explicit trust mark.

        Untrusted external content is labelled data (never authority) so a caller
        assembling an LLM prompt cannot accidentally treat retrieved text as
        instructions. Pure classification — no LLM call, no mutation.
        """
        out: List[Dict[str, Any]] = []
        for h in hits:
            src = h.get("source", "external")
            tc = self.classify(src)
            out.append(
                {
                    "content": h.get("content", ""),
                    "source": src,
                    "trust": tc.value,
                    "authoritative": self.is_authoritative(src),
                }
            )
        return out

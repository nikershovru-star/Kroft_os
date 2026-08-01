"""PrivacyPolicy (Wave 5.1, ADR-009 §4.2).
PII governance + provider restrictions. v0.1 uses regex heuristics;
v1.0 may plug in a lightweight local classifier.
"""
from __future__ import annotations
import re
from typing import List, Optional
from contracts.i_llm import ModelInfo
from contracts.i_policy import IPolicy, PolicyContext, PolicyDecision

# v0.1 heuristic PII patterns (ADR-009 §10, question 2)
# NOTE: word boundaries must be the two-char escape \b, not a literal backspace.
_PII_PATTERNS = [
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),          # email
    re.compile(r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"),                               # phone
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),                                      # SSN
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),                                     # credit-card-ish
]


def _has_pii(text: str) -> bool:
    """Return True if the prompt contains probable PII markers."""
    return any(p.search(text) for p in _PII_PATTERNS)


class PrivacyPolicy(IPolicy):
    """Restrict models by data-residency, provider trust, and PII presence.

    Rules (applied in order):
      1. allowed_providers / blocked_providers filter.
      2. If local_only → keep only local models.
      3. If no_cloud_reasoning + query.reasoning → keep only local models.
      4. If PII detected in prompt → force local (implicit local_only for this call).
      5. If nothing survives → veto.
    """

    def __init__(
        self,
        local_only: bool = False,
        no_cloud_reasoning: bool = False,
        allowed_providers: Optional[List[str]] = None,
        blocked_providers: Optional[List[str]] = None,
    ) -> None:
        self.local_only = local_only
        self.no_cloud_reasoning = no_cloud_reasoning
        self.allowed_providers = set(allowed_providers or [])
        self.blocked_providers = set(blocked_providers or [])

    # --- IPolicy contract ---------------------------------------------------
    @property
    def name(self) -> str:
        return "PrivacyPolicy"

    @property
    def priority(self) -> int:
        return 20

    @property
    def can_veto(self) -> bool:
        return True

    # --- evaluation ----------------------------------------------------------
    def evaluate(self, context: PolicyContext, catalog: List[ModelInfo]) -> PolicyDecision:
        filtered = list(catalog)

        # 1) provider whitelist / blacklist
        if self.allowed_providers:
            filtered = [m for m in filtered if m.provider in self.allowed_providers]
        if self.blocked_providers:
            filtered = [m for m in filtered if m.provider not in self.blocked_providers]

        # 2) local-only flags + PII detection
        force_local = self.local_only
        if self.no_cloud_reasoning and context.query.reasoning:
            force_local = True
        if _has_pii(context.query.prompt or ""):
            force_local = True

        if force_local:
            filtered = [m for m in filtered if m.local]

        # 3) veto if nothing survives
        if not filtered:
            return PolicyDecision(
                allowed=False,
                reason=(
                    "PrivacyPolicy: no models satisfy "
                    f"local_only={self.local_only}, no_cloud_reasoning={self.no_cloud_reasoning}, "
                    f"allowed={self.allowed_providers}, blocked={self.blocked_providers}"
                ),
                vetoed_by=self.name,
                audit_log=[f"PrivacyPolicy: force_local={force_local}, survivors=0"],
                constraints_applied=[self.name],
            )

        return PolicyDecision(
            allowed=True,
            selected_model=filtered[0],
            fallback_chain=filtered,
            reason=f"PrivacyPolicy: {len(filtered)} models after privacy filter",
            audit_log=[f"PrivacyPolicy: passed with {len(filtered)} models (force_local={force_local})"],
            constraints_applied=[self.name],
        )

"""SecurityPolicy (Wave 5.2, ADR-009 §4 / checklist).

Filters the candidate catalog by trust tier and an explicit blocklist. This is a
FILTER, not a veto (can_veto=False): an empty result is a valid outcome — the
next policy or the engine decides what to do (LAW 4 + ADR-009 pipeline).

Architecture laws:
- LAW 2: depends only on `contracts` (IPolicy, PolicyContext, ModelInfo).
- LAW 3: trust tier is a COMPUTED property (function), never stored mutable state.
- LAW 4: audit log explains WHY each model was filtered (Decision -> Evidence).
- LAW 5: trust tier v0.1 is a heuristic from ModelInfo fields (free/local). v1.0
  plugs in measured data from Wave 7 (scorecards) — acceptable without it.
- LAW 6: no new ISecurityPolicy port; reuses existing IPolicy.
"""
from __future__ import annotations

from typing import List

from contracts.i_llm import ModelInfo, ModelQuery
from contracts.i_policy import IPolicy, PolicyContext, PolicyDecision


def trust_tier(model: ModelInfo) -> int:
    """Compute trust tier (1-5) from ModelInfo — heuristic v0.1 (LAW 3/5).

    5 = local + free  (offline, no cost, max trust)
    3 = cloud + free
    2 = cloud + paid
    0 = explicitly blocked (added by caller via blocked_models list)
    """
    if model.free and model.local:
        return 5
    if model.free and not model.local:
        return 3
    if (not model.free) and not model.local:
        return 2
    # local + paid: treat as 3 (local execution still reduces exfil risk)
    return 3


class SecurityPolicy(IPolicy):
    """Filter candidates by trust tier and blocklist (Wave 5.2, ADR-009)."""

    def __init__(
        self,
        min_trust_tier: int = 1,
        blocked_models: List[str] = None,
        require_audit_trail: bool = False,
    ) -> None:
        # min_trust_tier clamped to 1-5 (LAW 3: constructor args are config, not mutable state)
        self.min_trust_tier = max(1, min(5, int(min_trust_tier)))
        self.blocked_models = list(blocked_models or [])
        self.require_audit_trail = require_audit_trail

    # --- IPolicy contract ---------------------------------------------------
    @property
    def name(self) -> str:
        return "SecurityPolicy"

    @property
    def priority(self) -> int:
        return 30

    @property
    def can_veto(self) -> bool:
        return False

    # --- filtering ----------------------------------------------------------
    def evaluate(self, context: PolicyContext, catalog: List[ModelInfo]) -> PolicyDecision:
        kept: List[ModelInfo] = []
        audit: List[str] = []

        for m in catalog:
            if m.id in self.blocked_models:
                audit.append(f"SecurityPolicy: '{m.id}' BLOCKED (blocklist)")
                continue
            tier = trust_tier(m)
            if tier < self.min_trust_tier:
                audit.append(
                    f"SecurityPolicy: '{m.id}' tier={tier} < min={self.min_trust_tier} DROPPED"
                )
                continue
            kept.append(m)

        if self.require_audit_trail:
            audit.append(
                f"SecurityPolicy: audit_trail REQUIRED; "
                f"{len(kept)}/{len(catalog)} models passed (min_tier={self.min_trust_tier})"
            )

        return PolicyDecision(
            allowed=True,  # filter, not veto (can_veto=False)
            fallback_chain=kept,
            reason=f"security filter: {len(kept)}/{len(catalog)} models kept "
                   f"(min_trust_tier={self.min_trust_tier}, "
                   f"blocked={len(self.blocked_models)})",
            audit_log=audit,
            constraints_applied=[self.name],
        )

"""PolicyRegistry — named policy registry (Phase C.2, ADR-009 Extension).

Makes policies pluggable by name (like plugins). The PolicyEngine still
orchestrates the pipeline (Phase 1-4); the registry is a convenience layer
for registering/looking-up policies by string key, enabling:
    PolicyRegistry.register("budget", BudgetPolicy())
    PolicyRegistry.register("safety", SafetyPolicy())
    PolicyRegistry.register("rate_limit", RateLimitPolicy())
    engine = PolicyEngine(registry); engine.register_all(registry.all())

Policies depend ONLY on contracts (K6). Registry lives in `policies/` (domain),
never imported by adapters/services directly except via composition root.
"""
from __future__ import annotations

from typing import Dict, List

from contracts.i_policy import IPolicy


class PolicyRegistry:
    """Named registry of policy instances (plug-and-play)."""

    def __init__(self) -> None:
        self._by_name: Dict[str, IPolicy] = {}

    def register(self, name: str, policy: IPolicy) -> "PolicyRegistry":
        if not isinstance(policy, IPolicy):
            raise TypeError(f"policy {name!r} must implement IPolicy")
        self._by_name[name] = policy
        return self

    def get(self, name: str) -> IPolicy:
        if name not in self._by_name:
            raise KeyError(f"no policy registered under {name!r}")
        return self._by_name[name]

    def has(self, name: str) -> bool:
        return name in self._by_name

    def names(self) -> List[str]:
        return list(self._by_name.keys())

    def all(self) -> List[IPolicy]:
        """Return policies sorted by priority (ascending), ready for engine."""
        return sorted(self._by_name.values(), key=lambda p: p.priority)

    def unregister(self, name: str) -> None:
        self._by_name.pop(name, None)

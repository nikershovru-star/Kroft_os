"""Recovery policy registry — maps component name -> RecoveryPolicy (config-driven).

Per Phase 4: policies are declarative (from YAML/dict), not hard-coded. Different
components get different rules (DB: 10 attempts; LLM worker: 3; human-approval: none).
Imports ONLY contracts + local recovery modules + stdlib (arch-gate LAW K8).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from runtime.recovery.policy import RecoveryPolicy


class RecoveryPolicyRegistry:
    """Resolves the RecoveryPolicy for a component; defaults if unspecified."""

    def __init__(self, policies: Dict[str, RecoveryPolicy] | None = None,
                 default: RecoveryPolicy | None = None) -> None:
        self._policies = policies or {}
        self._default = default or RecoveryPolicy()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryPolicyRegistry":
        """`data` maps component -> policy dict (or bare 'restart' flag)."""
        policies: Dict[str, RecoveryPolicy] = {}
        for name, spec in (data or {}).items():
            if isinstance(spec, dict):
                policies[name] = RecoveryPolicy.from_dict(spec)
            else:
                # bare bool: restart yes/no, default attempts
                policies[name] = RecoveryPolicy(restart=bool(spec))
        return cls(policies)

    @classmethod
    def from_yaml(cls, path: Path) -> "RecoveryPolicyRegistry":
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        # Expect structure: {supervisor: {recovery: {<component>: {...}}}}
        recovery = data.get("supervisor", {}).get("recovery", data)
        return cls.from_dict(recovery if isinstance(recovery, dict) else {})

    def policy_for(self, component: str) -> RecoveryPolicy:
        return self._policies.get(component, self._default)

    def set(self, component: str, policy: RecoveryPolicy) -> None:
        self._policies[component] = policy

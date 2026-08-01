"""Policy implementations (Wave 5, ADR-009).

Phase B: BudgetPolicy — cost governance with veto.
Other policies (Privacy/Security/ProviderSelection/Fallback) land in later phases.
"""
from __future__ import annotations

import time
from typing import Dict, List

from contracts.i_llm import ModelInfo
from contracts.i_policy import IPolicy, PolicyContext, PolicyDecision, CallRecord
from contracts.cost import estimate_cost


class BudgetPolicy(IPolicy):
    """Cost governance. Veto if any limit would be exceeded (ADR-009 §4.1).

    v0.1: in-memory state, reset on restart (see §8). No new dependencies.
    """

    def __init__(
        self,
        daily_limit: float = 0.0,
        session_limit: float = 0.0,
        per_call_limit: float = 0.0,
    ) -> None:
        self.daily_limit = daily_limit
        self.session_limit = session_limit
        self.per_call_limit = per_call_limit
        # state: user_id -> {"calls": List[CallRecord]}
        self._state: Dict[str, Dict] = {}

    # --- IPolicy contract ---------------------------------------------------
    @property
    def name(self) -> str:
        return "BudgetPolicy"

    @property
    def priority(self) -> int:
        return 10

    @property
    def can_veto(self) -> bool:
        return True

    def evaluate(self, context: PolicyContext, catalog: List[ModelInfo]) -> PolicyDecision:
        uid = context.user_id
        est = context.estimated_cost

        # per-call hard limit
        if self.per_call_limit > 0 and est > self.per_call_limit:
            return PolicyDecision(
                allowed=False,
                reason=f"estimated cost {est:.4f} > per_call_limit {self.per_call_limit:.4f}",
                vetoed_by=self.name,
                audit_log=[f"BudgetPolicy: per-call veto (est={est:.4f})"],
                constraints_applied=[self.name],
            )

        # session + daily accumulation
        rec = self._state.setdefault(uid, {"calls": []})
        now = time.time()
        session_cost = sum(c.cost for c in rec["calls"] if context.session_id == "" or True)
        # daily = calls within last 24h
        day_ago = now - 86400.0
        daily_cost = sum(c.cost for c in rec["calls"] if c.timestamp >= day_ago)

        if self.session_limit > 0 and session_cost + est > self.session_limit:
            return PolicyDecision(
                allowed=False,
                reason=f"session cost {session_cost + est:.4f} > session_limit {self.session_limit:.4f}",
                vetoed_by=self.name,
                audit_log=[f"BudgetPolicy: session veto"],
                constraints_applied=[self.name],
            )
        if self.daily_limit > 0 and daily_cost + est > self.daily_limit:
            return PolicyDecision(
                allowed=False,
                reason=f"daily cost {daily_cost + est:.4f} > daily_limit {self.daily_limit:.4f}",
                vetoed_by=self.name,
                audit_log=[f"BudgetPolicy: daily veto"],
                constraints_applied=[self.name],
            )

        # passed: record the projected call (v0.1 — count before execution)
        rec["calls"].append(
            CallRecord(model="?", cost=est, timestamp=now)
        )
        return PolicyDecision(
            allowed=True,
            fallback_chain=list(catalog),
            reason="budget OK",
            audit_log=[f"BudgetPolicy: passed (est={est:.4f})"],
            constraints_applied=[self.name],
        )

    # --- helpers (engine/router call these to record real cost) --------------
    def record(self, user_id: str, model: str, cost: float) -> None:
        """Update state with an actual completed call (called by engine.post-exec)."""
        rec = self._state.setdefault(user_id, {"calls": []})
        rec["calls"].append(CallRecord(model=model, cost=cost, timestamp=time.time()))

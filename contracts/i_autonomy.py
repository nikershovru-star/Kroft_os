"""(contracts) Autonomy Platform ports — Wave 14, ADR-017.

Contracts Before Code (LAW 1). Ports + entities only:
- NO implementation
- NO adapters
- NO services imports (domain depends on contracts, never the reverse — LAW 2)

Definition of Done (Roadmap Wave 14):

    The agent can self-initiate retrospection and self-maintain docs —
    but NEVER mutate runtime without an explicit ConfigApplier approve().

Wave 14 closes the observe-learn-optimize-act loop. All three ports are
*observe / recommend / propose* surfaces; mutation stays exclusively in
Wave 13's `ConfigApplier` (two-phase commit). No port here calls apply().
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, List, Tuple

from contracts.i_learning import ExecutionTrace, Pattern
from contracts.i_optimization import Recommendation


# --------------------------------------------------------------------------
# Entities (frozen — LAW 3)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class EvaluationReport:
    """Self-assessment of past runs (ADR-017 §2.2).

    Built strictly from Wave 12 fields (NOT from a non-existent StepTrace.status):
    - plan_success_rate: fraction of traces with final_status == "done"
    - pattern_drift: applied / (applied + rolled_back) recommendations
    - optimization_yield: fraction of proposed recs that reached approved+
    `attention` lists rec ids needing human review (e.g. drift above threshold).
    Carries `timestamp` + `trace_ids` for LAW 4 (attributable).
    """

    timestamp: str
    plan_success_rate: float
    pattern_drift: float
    optimization_yield: float
    attention: Tuple[str, ...] = ()
    trace_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DocSyncResult:
    """Read-only doc/code consistency check (ADR-017 §2.3).

    `mismatches` are detected inconsistencies; `proposed_diffs` are the
    suggested fixes. The maintainer NEVER writes files — only proposes.
    """

    mismatches: Tuple[str, ...] = ()
    proposed_diffs: Tuple[str, ...] = ()


# --------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------
class IAutonomyController(abc.ABC):
    """Decide WHEN to run a retrospective (ADR-017 §2.1).

    Pure trigger logic. Does not execute anything — returns a bool. Rate-limit
    (max 1 retrospective/hour) is the caller's guard against loop autonomy.
    """

    @abc.abstractmethod
    def should_retrospect(self, traces: List[ExecutionTrace], config: Dict) -> bool:
        """True when enough evidence has accumulated for self-analysis."""
        raise NotImplementedError


class ISelfEvaluator(abc.ABC):
    """Retrospective analysis of past runs (ADR-017 §2.2).

    Consumes Wave 12 `ExecutionTrace`s + `Pattern`s and produces an
    `EvaluationReport`. Pure analysis — no runtime mutation.
    """

    @abc.abstractmethod
    def evaluate(
        self, traces: List[ExecutionTrace], patterns: List[Pattern]
    ) -> EvaluationReport:
        """Compute drift/success/yield metrics from history."""
        raise NotImplementedError


class IDocMaintainer(abc.ABC):
    """Keep docs in sync with code — read-only (ADR-017 §2.3).

    Produces a `DocSyncResult` (mismatches + proposed diffs). NEVER writes
    files; the human (or orchestrator) must approve before anything changes.
    """

    @abc.abstractmethod
    def sync(self, docs_root: str, code_state: Dict) -> DocSyncResult:
        """Check ADR statuses, MOC links, Roadmap hashes vs actual code."""
        raise NotImplementedError

"""Autonomous Knowledge Loop (ТЗ-KNOWLEDGE-AUTONOMOUS-LOOP-01).

Composition-root seam (K5-legal): closes the self-improving cycle
  research(goal) -> gap_detected -> GapPlanner.plan -> autonomous_ingest_step

It MUST NOT live in services/ (K6: services import only contracts). It takes the
already-wired ResearchAgent (or its ISearchService) and, when a query yields a
knowledge gap, plans the missing catalog entries and merges the available ones
into a TEMP copy (never the live snapshot unless explicitly told).

Deterministic (I-09): no sleep/timers; LLM-free planning/ingest.

Example (run_kroft composition root):
    loop = AutonomousKnowledgeLoop(
        research_agent=research_agent,
        snapshot_path=self.config.knowledge_snapshot,
        catalog_path=CATALOG_YAML,
    )
    report = loop.self_heal("cybernetics control theory", output_dir=tmp)
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

# composition root may import concrete ingest helpers (K5-legal here)
from scripts.foundation_ingest import GapPlanner, autonomous_ingest_step

DEFAULT_CATALOG = str(
    Path(__file__).resolve().parent.parent
    / "docs" / "architecture" / "AKB" / "knowledge_foundation_v1.yaml"
)


class AutonomousKnowledgeLoop:
    """One autonomous self-heal step over a research goal (ТЗ-KNOWLEDGE-AUTONOMOUS-LOOP-01)."""

    def __init__(self, research_agent, snapshot_path: str,
                 catalog_path: str = DEFAULT_CATALOG,
                 extracted_dir: Optional[str] = None) -> None:
        self._agent = research_agent
        self._snapshot = snapshot_path
        self._catalog = catalog_path
        self._extracted = extracted_dir
        self._planner = GapPlanner(snapshot_path, catalog_path, extracted_dir=extracted_dir)

    def self_heal(self, goal: str, output_dir: Optional[str] = None) -> dict:
        """Run a research goal; if a gap is detected, plan + merge missing catalog entries.

        Returns:
            {
              "goal": str,
              "gap_detected": bool,
              "plan": {actions, gaps_total, actionable},
              "ingested": bool,
              "report": dict|None,        # from autonomous_ingest_step
              "output_path": str|None,    # TEMP copy written (None when no ingest)
            }

        SAFETY: the LIVE snapshot is never mutated. When ``output_dir`` is None a
        fresh temp dir is used. Pass ``output_path`` == live snapshot only with an
        explicit `accept` command from the operator.
        """
        result = self._agent.run(goal)
        gap = bool(getattr(result, "gap_detected", False))

        if not gap:
            return {
                "goal": goal, "gap_detected": False,
                "plan": {"actions": [], "gaps_total": 0, "actionable": 0},
                "ingested": False, "report": None, "output_path": None,
            }

        plan = self._planner.plan(goals=[goal])
        if plan["actionable"] == 0:
            return {
                "goal": goal, "gap_detected": True,
                "plan": plan, "ingested": False, "report": None, "output_path": None,
            }

        out_dir = output_dir or tempfile.mkdtemp(prefix="kroft_autoloop_")
        out_path = os.path.join(out_dir, "_snapshot.auto.json")
        ingest = autonomous_ingest_step(
            self._snapshot, self._catalog,
            extracted_dir=self._extracted, output_path=out_path,
        )
        return {
            "goal": goal, "gap_detected": True,
            "plan": plan, "ingested": ingest.get("ingested", False),
            "report": ingest.get("report"), "output_path": out_path,
        }

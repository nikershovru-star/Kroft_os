"""Reference Autonomous Planner (ТЗ-PL-01) — deterministic, LLM-free (I-09).

K1-compliant: imports ONLY contracts + stdlib. No service/adapter/runtime imports.

The Planner is the DELIBERATE candidate generator (ADR-054: Reasoning -> Planning ->
Decision). It turns ReasoningSteps into candidate Plans, runs each through the World
Model (lookahead via simulate), and RANKS them by PREDICTED VALUE-AWARE utility
(ТЗ-PL-01 flag 2). The ranking rides in `Plan.confidence`; the planner only RANKS —
the deterministic Decision Engine still makes the final pick (I-03 / I-09).
"""

from __future__ import annotations

import re
import uuid
from typing import List, Optional, Tuple

from contracts.cognitive_domain import (
    Action,
    ConfidenceScore,
    Goal,
    Intent,
    Plan,
    Provenance,
    ProvenanceType,
    ReasoningStep,
    WorldState,
)
from contracts.i_cognitive_kernel import IValueSystem
from contracts.i_world_model import IWorldModel
from contracts.i_planner import IPlanner


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class ReferencePlanner(IPlanner):
    """Deterministic planner with World-Model lookahead (LLM-free core).

    Strategy: one candidate Plan per reasoning step (its description becomes the plan
    step). When a WorldModel is wired, each candidate is ROLLED OUT via
    `simulate(world, plan)` and scored by `evaluate(predicted, intent, values)` —
    value-aware (hard violations veto the candidate to utility 0; soft utilities
    re-rank). The candidate's `Plan.confidence` becomes the predicted value-aware
    utility, and candidates are returned BEST-first.

    Without a WorldModel the planner falls back to ranking by the reasoning-step
    confidence (backward compatible). Hard-violating candidates (utility 0) sink to
    the bottom; an explore-only step still yields a fallback candidate.
    """

    def __init__(self, clock, world_model: Optional[IWorldModel] = None,
                 values: Optional[IValueSystem] = None,
                 procedural: Optional[object] = None) -> None:
        # ТЗ-RE-01 flag 1: planner advances the SAME shared node clock as the kernel.
        self._clock = clock
        self._world_model = world_model
        self._values = values
        # Slice 4: optional procedural memory (InMemoryProceduralMemory) for
        # experience-informed ranking. Duck-typed (any object with a _procedures
        # dict keyed by capability), so the planner stays K6-clean (no services import).
        self._procedural = procedural

    def _predicted_utility(self, plan: Plan, world: WorldState,
                          intent: Optional[Intent],
                          step: Optional[ReasoningStep] = None) -> float:
        """Value-aware predicted utility of a candidate plan via World Model lookahead."""
        if self._world_model is None or intent is None:
            return plan.confidence.value  # backward-compatible fallback
        # Build the simulated action from the GROUNDED fact (not the step description),
        # so the predicted outcome actually reflects acting on that world fact — this
        # is what makes Y-rank > X-rank value-aware (ТЗ-PL-01 flag 3: full-world eval,
        # but the action is the fact's content, not the step label).
        if step is not None and step.based_on_facts:
            key = step.based_on_facts[0]
            payload = world.facts.get(key, step.description)
        else:
            payload = plan.steps[0] if plan.steps else plan.description if hasattr(plan, "description") else ""
        action = Action(id=f"{plan.id}-sim", kind="rule", payload=payload,
                        confidence=plan.confidence, provenance=plan.provenance)
        rollout = self._world_model.simulate(world, Plan(
            id=plan.id, goal_id=plan.goal_id, steps=(payload,),
            confidence=plan.confidence, provenance=plan.provenance), horizon=1)
        if not rollout:
            return plan.confidence.value
        # predicted utility = worst-case along the rollout (a plan is only as good as
        # its weakest predicted step); value-aware via evaluate(intent, values).
        utils = [self._world_model.evaluate(st, intent, self._values) for st in rollout]
        return float(min(utils))

    def _build_execution_steps(self, step: ReasoningStep) -> Optional[Tuple[dict, ...]]:
        """Best-effort structured execution intent from a reasoning step.

        ТЗ-PHASE-P.2 (ADR-O.9 K6-exception): populate Plan.execution_steps so the
        cognitive loop can drive REAL actions via RealWorldExecutor._exec_plan (PHASE O.3).
        Returns None when no structured intent can be derived -> backward compatible
        (textual plan unchanged). Recognises lightweight markers in the step description;
        any other text yields None until an upstream source emits structured intent.
        """
        desc = (step.description or "").strip()
        low = desc.lower()
        try:
            if low.startswith(("exec:", "cmd:", "shell:")):
                return ({"kind": "command", "cmd": desc.split(":", 1)[1].strip()},)
            if low.startswith("write:"):
                _, rest = desc.split("write:", 1)
                path, _, content = rest.partition("|")
                return ({"kind": "file", "path": path.strip(), "content": content},)
            if "click" in low or "type" in low or "open_app" in low or low.startswith("open "):
                verb = low.split()[0] if low.split() else "click"
                op = "open_app" if verb == "open" else verb
                return ({"kind": "desktop", "op": op, "text": desc},)
        except Exception:  # noqa: BLE001 — any parse failure -> no structured intent
            return None
        return None

    def _goal_intent_steps(self, goal: Goal) -> Optional[Tuple[dict, ...]]:
        """Recognise file/command intent from a natural-language GOAL (Slice 3 / D3).

        Complements ``_build_execution_steps`` (which only reads explicit markers in
        reasoning-step text). When the reasoning layer emits no structured intent, the
        planner still recognises a real user goal like "запиши hello в x.txt" or
        "выполни echo hi" and emits the corresponding execution_steps so the cognitive
        loop can drive REAL actions via RealWorldExecutor (PHASE O.3) autonomously.
        Returns None when no intent is recognised. K6-clean: kernel/planning only.
        """
        text = (goal.description or "").strip()
        if not text:
            return None
        low = text.lower()
        try:
            # FILE: "запиши <content> в <path>" / "сохрани/напиши/создай файл ... в <path>"
            if any(k in low for k in ("запиши", "сохрани", "напиши", "создай файл", "в файл")):
                parts = re.split(r"\s+в\s+", text, maxsplit=1, flags=re.I)
                head = parts[0]
                path = parts[1].strip() if len(parts) > 1 else None
                if path:
                    content = re.sub(
                        r"^(запиши|сохрани|напиши|создай файл|в файл)\s*", "", head,
                        flags=re.I,
                    ).strip()
                    if content:
                        return ({"kind": "file", "path": path, "content": content},)
            if low.startswith("write ") or low.startswith("create "):
                path = low.split(" ", 1)[1].strip()
                if path:
                    return ({"kind": "file", "path": path, "content": ""},)
            # COMMAND: "выполни <cmd>" / "run <cmd>" / "execute <cmd>" / "эхо/echo <cmd>"
            if low.startswith(("выполни", "run ", "execute ", "эхо ", "echo ")):
                cmd = text.split(" ", 1)[1] if " " in text else text
                if cmd:
                    return ({"kind": "command", "cmd": cmd},)
        except Exception:  # noqa: BLE001 — any parse failure -> no structured intent
            return None
        return None

    def _apply_experience_ranking(self, candidates: List[Plan]) -> List[Plan]:
        """Slice 4: bias plan confidence by past procedural success-rate (K5).

        For candidates that carry a structured execution intent (file/command), read
        the capability's success_rate from the procedural memory and nudge confidence
        upward toward 1.0 in proportion to experience. Unknown capability (no entry,
        or zero runs) is left UNCHANGED — so abstract deliberation (choose_blue/red,
        which has no execution_steps) is never touched and stays deterministic.
        Deterministic for a given memory state; no new port / planner contract change.
        """
        if self._procedural is None:
            return candidates
        procs = getattr(self._procedural, "_procedures", None)
        if not isinstance(procs, dict):
            return candidates
        out = []
        for c in candidates:
            kind = None
            if c.execution_steps:
                first = c.execution_steps[0]
                if isinstance(first, dict):
                    kind = first.get("kind")
            if not kind:
                out.append(c)
                continue
            proc = procs.get(f"exec:{kind}")
            base = c.confidence.value
            adj = base
            if proc and proc.get("runs", 0) > 0:
                sr = proc.get("success_rate") or (
                    proc.get("successes", 0) / float(proc["runs"]))
                # minimal deterministic boost: move base toward 1.0 by sr * 0.3
                adj = min(1.0, base + (1.0 - base) * float(sr) * 0.3)
            out.append(Plan(id=c.id, goal_id=c.goal_id, steps=c.steps,
                            confidence=ConfidenceScore(adj, ProvenanceType.RULE_INFERENCE),
                            provenance=c.provenance, execution_steps=c.execution_steps))
        return out

    def plan(self, goal: Goal, reasoning_steps: List[ReasoningStep],
             world: WorldState, budget_tokens: int,
             intent: Optional[Intent] = None) -> List[Plan]:
        candidates: List[Plan] = []
        for s in reasoning_steps:
            # each reasoning step becomes a candidate plan whose step is the step's
            # grounded description (e.g. "grounded-in:prefer-Y").
            plan = Plan(id=_uid("plan"), goal_id=goal.id,
                        steps=(s.description,),
                        confidence=s.confidence,
                        provenance=Provenance(source="reasoning", actor="kernel"),
                        execution_steps=self._build_execution_steps(s))
            # value-aware predicted utility via World Model lookahead (ТЗ-PL-01 flag 2)
            util = self._predicted_utility(plan, world, intent, step=s)
            ranked = Plan(id=plan.id, goal_id=goal.id, steps=plan.steps,
                          confidence=ConfidenceScore(util, ProvenanceType.RULE_INFERENCE),
                          provenance=plan.provenance,
                          execution_steps=plan.execution_steps)
            candidates.append(ranked)

        if not candidates:
            # fallback explore candidate (no reasoning step)
            candidates.append(Plan(id=_uid("plan"), goal_id=goal.id,
                                    steps=(f"explore-for:{goal.description}",),
                                    confidence=ConfidenceScore(0.4, ProvenanceType.RULE_INFERENCE),
                                    provenance=Provenance(source="planner", actor="kernel")))

        # Slice 3 / D3: if reasoning steps yielded no structured intent, try to
        # recognise it from the natural-language GOAL itself so the loop can drive
        # REAL actions autonomously (file / command) without external markers.
        if not any(c.execution_steps for c in candidates):
            goal_steps = self._goal_intent_steps(goal)
            if goal_steps:
                candidates = [
                    Plan(id=c.id, goal_id=c.goal_id, steps=c.steps,
                         confidence=c.confidence, provenance=c.provenance,
                         execution_steps=goal_steps)
                    for c in candidates
                ]

        # Slice 4: bias confidence by past procedural success-rate for execution
        # intent (file/command). Abstract deliberation (no execution_steps) untouched.
        candidates = self._apply_experience_ranking(candidates)

        # rank BEST-first by predicted value-aware utility (planner only ranks)
        candidates.sort(key=lambda p: p.confidence.value, reverse=True)
        return candidates

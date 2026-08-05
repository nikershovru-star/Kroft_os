#!/usr/bin/env python3
"""run_evolution.py — live launch of a self-evolving KROFT_OS kernel (ТЗ-LIVE-01, ADR-087).

Флаг C (standalone entry point, root-level): this is a composition root, so it may import
kernel.* + services.* + composition.* (cross-layer wiring lives here, NOT in kernel/).

What it does:
  1. Builds a CognitiveKernel via build_kernel, optionally wrapped with a local Ollama
     advisor (detect_local_ollama -> build_llm_client; skip-if-unavailable: the kernel is
     LLM-free by construction, so absence of Ollama is NOT an error).
  2. Loads persisted evolution state (JsonMemoryStore) if a state file exists, and replays
     it into a fresh memory store so the kernel RESUMES its self-evolution across restarts.
  3. Runs N ticks of a demo goal stream (deterministic, no LLM). Repeated "failures" on a
     chosen path make the kernel learn a soft `avoid:` policy (self-evolution); a
     ProcedureConsolidator over the same stream consolidates reusable skills.
  4. Prints the evolution (new soft policies / skills / trust deltas) and SAVES the state.

Determinism (I-09): without LLM the run is fully deterministic; the same state file + same
N ticks reproduces the same evolution. O1: persistence never mutates HARD.

Usage:
    python run_evolution.py --state state.json --ticks 6 [--no-llm]
"""

from __future__ import annotations

import argparse
import sys
from typing import List

# composition root: allowed to cross layers (like tests/ helpers).
from kernel.cognitive_kernel import build_kernel
from kernel.memory_store import InMemoryLayeredMemory
from kernel.persistence import JsonMemoryStore, KernelState
from kernel.procedural import ProcedureConsolidator, build_procedural
from services.memory_platform import InMemoryProceduralMemory
from kernel.identity import ReferenceTrustRegistry
from contracts.cognitive_domain import Episode, ConfidenceScore, Provenance, ProvenanceType
from contracts.i_orchestrator import OrchestrationGoal

# Capability that the demo stream repeatedly "fails" on, so the kernel learns avoid:capability.
_FAIL_CAPABILITY = "choose_red"
_SUCCESS_CAPABILITY = "choose_blue"


def _demo_stream(n: int) -> List[OrchestrationGoal]:
    """Deterministic demo goal stream: mostly failures on choose_red, successes on choose_blue."""
    goals: List[OrchestrationGoal] = []
    for i in range(n):
        # Alternate: every even tick fails on red (learned -> avoided), odd ticks succeed on blue.
        cap = _FAIL_CAPABILITY if i % 2 == 0 else _SUCCESS_CAPABILITY
        goals.append(OrchestrationGoal(goal_id=f"g{i}", capability=cap, payload={"step": i}))
    return goals


def _replay_state(state: KernelState, mem: InMemoryLayeredMemory,
                  proc: InMemoryProceduralMemory, trust: ReferenceTrustRegistry) -> None:
    """Replay a loaded KernelState into fresh stores so the kernel resumes its evolution."""
    for e in state.episodes:
        mem.record_episode(e)
    for f in state.semantic:
        mem.commit_semantic(f)
    for p in state.normative:
        mem.commit_normative(p)
    for s in state.skills:
        proc.store_skill(s)
    for author, score in state.trust.items():
        # seed running trust; record_outcome would move it, so set directly for resume.
        trust._running[author] = float(score)


def _extract_state(kernel, proc: InMemoryProceduralMemory,
                   trust: ReferenceTrustRegistry) -> KernelState:
    mem = kernel._memory
    return KernelState(
        episodes=list(mem.get_episodes()),
        semantic=list(mem.get_semantic()),
        normative=list(mem.get_normative()),
        skills=list(proc.list_skills()),
        trust=dict(trust._running),
    )


def _print_evolution(state: KernelState, label: str) -> None:
    soft_policies = [p for p in state.normative if p.layer == "soft"]
    print(f"\n=== {label} ===")
    print(f"  episodes       : {len(state.episodes)}")
    print(f"  semantic facts : {len(state.semantic)}")
    print(f"  soft policies  : {len(soft_policies)}")
    for p in soft_policies:
        print(f"    - {p.body} (conf={p.confidence.value:.2f})")
    print(f"  skills         : {len(state.skills)}")
    for s in state.skills:
        print(f"    - {s.capability} (conf={s.confidence:.2f})")
    print(f"  trust          : {state.trust}")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a self-evolving KROFT_OS kernel (ТЗ-LIVE-01).")
    parser.add_argument("--state", default="kroft_state.json", help="Path to the JSON state file.")
    parser.add_argument("--ticks", type=int, default=6, help="Number of demo goal ticks to run.")
    parser.add_argument("--node-id", default="local", help="Node id for this kernel instance.")
    parser.add_argument("--no-llm", action="store_true",
                        help="Force LLM-free run (skip Ollama auto-detect).")
    args = parser.parse_args(argv)

    # 1. Optional local LLM advisor (skip-if-unavailable).
    llm_client = None
    if not args.no_llm:
        try:
            from composition.llm_client_factory import detect_local_ollama, build_llm_client
            if detect_local_ollama():
                llm_client = build_llm_client()
                print("[run_evolution] local Ollama detected -> advisor enabled")
            else:
                print("[run_evolution] no local Ollama -> LLM-free run (deterministic)")
        except Exception as exc:  # skip-if-unavailable: never fail the run on LLM issues
            print(f"[run_evolution] LLM advisor skipped ({exc!r}) -> LLM-free run")

    # 2. Load + replay persisted state (resume across restarts).
    store = JsonMemoryStore()
    mem = InMemoryLayeredMemory()
    proc = InMemoryProceduralMemory()
    trust = ReferenceTrustRegistry()
    consolidator = build_procedural(proc, threshold=2, min_rate=0.5)
    if _state_file_exists(args.state):
        loaded = store.load(args.state)
        _replay_state(loaded, mem, proc, trust)
        print(f"[run_evolution] resumed from {args.state}: "
              f"{len(loaded.episodes)} episodes, {len(loaded.normative)} policies")

    kernel = build_kernel(args.node_id, llm_client=llm_client, memory=mem)
    # Reference executor fails on choose_red / succeeds on choose_blue (deterministic rule env),
    # so the kernel's self-evolution EMITS a real soft `avoid:` policy after repeated failures
    # (non-vacuous evolution). LLM-free and deterministic (I-09).
    from kernel.execution import ReferenceExecutor
    kernel.attach_executor(ReferenceExecutor())

    # 3. Run the demo stream: each tick feeds a goal; the kernel self-evolves (soft policy),
    #    and the consolidator records the skill outcome -> evolves skills/trust.
    goals = _demo_stream(args.ticks)
    for g in goals:
        kernel.tick(_goal_to_intent(g))
        # Demo-level skill/trust evolution keyed on capability success:
        # choose_blue succeeds (skill +), choose_red fails (skill -); trust in 'demo' source.
        success = g.capability != _FAIL_CAPABILITY
        consolidator.learn(g.capability, steps=(g.capability,), success=success)
        trust.record_outcome("demo", success)
    # After ticks: surface skill confidence deltas from outcomes too.
    for g in goals:
        success = g.capability != _FAIL_CAPABILITY
        if proc.has_skill(g.capability):
            proc.record_skill_outcome(g.capability, success, 0.1)

    # 4. Persist + print evolution.
    state = _extract_state(kernel, proc, trust)
    store.save(state, args.state)
    _print_evolution(state, f"after {args.ticks} ticks (state saved -> {args.state})")
    return 0


def _state_file_exists(path: str) -> bool:
    import os
    return os.path.exists(path)


def _goal_to_intent(goal: "OrchestrationGoal"):
    """Map an OrchestrationGoal to the kernel's Intent shape for tick()."""
    from contracts.cognitive_domain import Intent, ConfidenceScore, Provenance
    return Intent(
        id=goal.goal_id,
        text=goal.capability,
        confidence=ConfidenceScore(0.8),
        provenance=Provenance(source="demo", actor="run_evolution"),
    )


if __name__ == "__main__":
    sys.exit(main())

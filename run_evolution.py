#!/usr/bin/env python3
"""run_evolution.py — living self-evolving KROFT_OS kernel (ТЗ-LIVE-01 extended, ADR-088).

Флаг C (standalone entry point, root-level): composition root, may import
kernel.* + services.* + composition.* (cross-layer wiring lives here, NOT in kernel/).

What it does (living core, Этап 1 roadmap):
  1. Builds a CognitiveKernel via build_kernel, optionally wrapped with a local Ollama
     advisor (detect_local_ollama -> build_llm_client; skip-if-unavailable: the kernel is
     LLM-free by construction, so absence of Ollama is NOT an error). --llm auto|none.
  2. Loads persisted evolution state (JsonMemoryStore) from --state-dir if present, and
     replays it into fresh stores so the kernel RESUMES self-evolution across restarts.
  3. Runs the demo goal stream (deterministic, no LLM): repeated "failures" on a chosen
     path make the kernel learn a soft `avoid:` policy (self-evolution); a ProcedureConsolidator
     over the same stream consolidates reusable skills. Trust is updated per outcome.
  4. Runs FOREVER (--ticks 0, default) or for N ticks, with a background autosave timer
     (periodic save) and optional background consolidation tick (off by default). Prints
     evolution deltas. On SIGINT: graceful save + stop.

Determinism (I-09): without LLM the run is fully deterministic; same state-dir + same N ticks
reproduces the same evolution. O1: persistence never mutates HARD.

Usage:
    python run_evolution.py --state-dir ./kroft_state --ticks 6 [--llm auto|none]
    python run_evolution.py --state-dir ./kroft_state --ticks 0   # live: blocks until SIGINT
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

# composition root: allowed to cross layers (like tests/ helpers).
from kernel.cognitive_kernel import build_kernel
from kernel.memory_store import InMemoryLayeredMemory
from kernel.persistence import JsonMemoryStore, KernelState
from kernel.procedural import ProcedureConsolidator, build_procedural
from services.memory_platform import InMemoryProceduralMemory
from kernel.identity import ReferenceTrustRegistry
from kernel.execution import ReferenceExecutor
from contracts.cognitive_domain import Episode, ConfidenceScore, Provenance, ProvenanceType
from contracts.i_orchestrator import OrchestrationGoal
from contracts.cognitive_domain import Intent

# Capability that the demo stream repeatedly "fails" on, so the kernel learns avoid:capability.
_FAIL_CAPABILITY = "choose_red"
_SUCCESS_CAPABILITY = "choose_blue"


def _demo_stream(n: int) -> List[OrchestrationGoal]:
    """Deterministic demo goal stream: mostly failures on choose_red, successes on choose_blue."""
    goals: List[OrchestrationGoal] = []
    for i in range(n):
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
                   trust: ReferenceTrustRegistry, baseline: Optional[KernelState]) -> KernelState:
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


def _goal_to_intent(goal: "OrchestrationGoal") -> "Intent":
    return Intent(
        id=goal.goal_id,
        text=goal.capability,
        confidence=ConfidenceScore(0.8),
        provenance=Provenance(source="demo", actor="run_evolution"),
    )


class _LivingCore:
    """Wiring of kernel + stores + background services (autosave timer + optional bg consolidate)."""

    def __init__(self, state_dir: str, node_id: str, llm_client, ticks: int,
                 autosave_sec: float, bg_consolidate: bool,
                 knowledge_snapshot: Optional[str] = None):
        self.state_path = str(Path(state_dir) / "kernel_state.json")
        self.knowledge_snapshot = knowledge_snapshot
        self.node_id = node_id
        self.ticks = ticks
        self.autosave_sec = autosave_sec
        self.bg_consolidate = bg_consolidate
        self._stop = threading.Event()
        self._autosave_timer: Optional[threading.Timer] = None

        os.makedirs(state_dir, exist_ok=True)
        self.store = JsonMemoryStore()
        self.mem = InMemoryLayeredMemory()
        self.proc = InMemoryProceduralMemory()
        self.trust = ReferenceTrustRegistry()
        self.consolidator = build_procedural(self.proc, threshold=2, min_rate=0.5)
        self._baseline: Optional[KernelState] = None

        # ТЗ-PHASE-I (convergence): prefer the unified KnowledgeSnapshotStore format
        # written by run_kroft, so evolution resumes from the SAME state the bootable
        # runtime persists (no duplicate format, no desync). Falls back to the legacy
        # JsonMemoryStore/KernelState path when --knowledge-snapshot is not supplied.
        if knowledge_snapshot and os.path.exists(knowledge_snapshot):
            from composition.knowledge_persistence import KnowledgeSnapshotStore
            from kernel.persistence import (
                _episode_from_dict, _semantic_from_dict, _policy_from_dict,
                _procedure_from_dict,
            )
            from dataclasses import replace
            ks = KnowledgeSnapshotStore(knowledge_snapshot)
            self.mem._episodes = [_episode_from_dict(b) for b in ks.load_episodic() if isinstance(b, dict)]
            self.mem._semantic = [_semantic_from_dict(b) for b in ks.load_semantic() if isinstance(b, dict)]
            self.mem._normative = [_policy_from_dict(b) for b in ks.load_normative() if isinstance(b, dict)]
            proc = ks.load_procedural()
            for name, entry in proc.get("procedures", {}).items():
                if isinstance(entry, dict) and "runs" in entry:
                    self.proc._procedures[name] = dict(entry)
            for cap, sk in proc.get("skills", {}).items():
                try:
                    p = replace(_procedure_from_dict(sk),
                                version=int(sk.get("version", 1)),
                                lifecycle=__import__("contracts.i_memory", fromlist=["PolicyLifecycle"]).PolicyLifecycle[sk.get("lifecycle", "ACTIVE")])
                    self.proc._skills[cap] = p
                except Exception:
                    pass
            for author, score in ks.load_trust().items():
                self.trust._running[author] = float(score)
            print(f"[run_evolution] resumed from knowledge-snapshot {knowledge_snapshot}: "
                  f"{len(self.mem._episodes)} episodes, {len(self.mem._normative)} policies")
        elif os.path.exists(self.state_path):
            loaded = self.store.load(self.state_path)
            _replay_state(loaded, self.mem, self.proc, self.trust)
            self._baseline = loaded
            print(f"[run_evolution] resumed from {self.state_path}: "
                  f"{len(loaded.episodes)} episodes, {len(loaded.normative)} policies")

        self.kernel = build_kernel(node_id, llm_client=llm_client, memory=self.mem)
        self.kernel.attach_executor(ReferenceExecutor())

    # -- evolution step --------------------------------------------------
    def tick_once(self, goal: OrchestrationGoal) -> None:
        self.kernel.tick(_goal_to_intent(goal))
        success = goal.capability != _FAIL_CAPABILITY
        self.consolidator.learn(goal.capability, steps=(goal.capability,), success=success)
        self.trust.record_outcome("demo", success)
        if self.proc.has_skill(goal.capability):
            self.proc.record_skill_outcome(goal.capability, success, 0.1)

    def snapshot(self) -> KernelState:
        return _extract_state(self.kernel, self.proc, self.trust, self._baseline)

    def save(self) -> None:
        self.store.save(self.snapshot(), self.state_path)

    # -- background autosave --------------------------------------------
    def _schedule_autosave(self) -> None:
        if self.autosave_sec and self.autosave_sec > 0 and not self._stop.is_set():
            self._autosave_timer = threading.Timer(self.autosave_sec, self._autosave_loop)
            self._autosave_timer.daemon = True
            self._autosave_timer.start()

    def _autosave_loop(self) -> None:
        if self._stop.is_set():
            return
        try:
            self.save()
            print(f"[run_evolution] autosave -> {self.state_path}")
        except Exception as exc:  # noqa: BLE001 — autosave must never crash the live loop
            print(f"[run_evolution] autosave failed: {exc!r}")
        self._schedule_autosave()

    def start_autosave(self) -> None:
        if self.autosave_sec and self.autosave_sec > 0:
            self._schedule_autosave()

    def stop_autosave(self) -> None:
        self._stop.set()
        if self._autosave_timer is not None:
            self._autosave_timer.cancel()

    def run(self) -> None:
        """Run the live loop: N ticks (or forever if ticks<=0), then final save.

        In forever mode (ticks<=0) blocks until SIGINT; autosave timer keeps state safe.
        """
        if self.ticks and self.ticks > 0:
            goals = _demo_stream(self.ticks)
            for g in goals:
                if self._stop.is_set():
                    break
                self.tick_once(g)
            self.save()
            state = self.snapshot()
            _print_evolution(state, f"after {self.ticks} ticks (state saved -> {self.state_path})")
            self.stop_autosave()
            return

        # Forever / live mode: block until SIGINT, autosave timer protects state.
        self.start_autosave()
        print(f"[run_evolution] LIVE mode — kernel running (node={self.node_id}). "
              f"Send SIGINT (Ctrl-C) to stop + save.")
        # seed one deterministic goal cycle so evolution is visible even in live mode.
        goals = _demo_stream(6)
        idx = 0
        try:
            while not self._stop.is_set():
                g = goals[idx % len(goals)]
                self.tick_once(g)
                idx += 1
                if idx % 6 == 0:
                    state = self.snapshot()
                    _print_evolution(state, f"live tick {idx} (state in memory)")
                time.sleep(0.2)
        finally:
            self.stop_autosave()
            self.save()
            state = self.snapshot()
            _print_evolution(state, f"stopped (state saved -> {self.state_path})")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a living self-evolving KROFT_OS kernel (ТЗ-LIVE-01).")
    parser.add_argument("--state-dir", default="./kroft_state",
                        help="Directory holding kernel_state.json (created if missing).")
    parser.add_argument("--ticks", type=int, default=0,
                        help="Demo ticks to run, then exit+save. 0 = live/forever (block until SIGINT).")
    parser.add_argument("--node-id", default="local", help="Node id for this kernel instance.")
    parser.add_argument("--llm", choices=["auto", "none"], default="auto",
                        help="auto: use local Ollama if detected; none: force LLM-free deterministic run.")
    parser.add_argument("--autosave-sec", type=float, default=30.0,
                        help="Background autosave period in seconds (0 disables).")
    parser.add_argument("--bg-consolidate", action="store_true",
                        help="Enable optional background consolidation tick (off by default; deterministic).")
    parser.add_argument("--knowledge-snapshot", default=None,
                        help="ТЗ-PHASE-I: unified KnowledgeSnapshotStore file (written by run_kroft). "
                             "When present, evolution resumes from the SAME state the bootable runtime "
                             "persists, avoiding a second divergent format. Falls back to --state-dir "
                             "kernel_state.json when omitted.")
    args = parser.parse_args(argv)

    # 1. Optional local LLM advisor (skip-if-unavailable).
    llm_client = None
    if args.llm == "auto":
        try:
            from composition.llm_client_factory import detect_local_ollama, build_llm_client
            if detect_local_ollama():
                llm_client = build_llm_client()
                print("[run_evolution] local Ollama detected -> advisor enabled")
            else:
                print("[run_evolution] no local Ollama -> LLM-free run (deterministic)")
        except Exception as exc:  # skip-if-unavailable: never fail the run on LLM issues
            print(f"[run_evolution] LLM advisor skipped ({exc!r}) -> LLM-free run")
    else:
        print("[run_evolution] --llm none -> LLM-free run (deterministic)")

    os.makedirs(args.state_dir, exist_ok=True)
    core = _LivingCore(
        state_dir=args.state_dir,
        node_id=args.node_id,
        llm_client=llm_client,
        ticks=args.ticks,
        autosave_sec=args.autosave_sec,
        bg_consolidate=args.bg_consolidate,
        knowledge_snapshot=args.knowledge_snapshot,
    )

    # 2. Graceful SIGINT: save + stop + exit 0.
    def _on_sigint(signum, frame):
        print("\n[run_evolution] SIGINT received — saving + stopping")
        core.stop_autosave()
        try:
            core.save()
        except Exception as exc:  # noqa: BLE001
            print(f"[run_evolution] final save failed: {exc!r}")
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_sigint)

    # 3. Run (N ticks or live until SIGINT; autosave timer protects state).
    core.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

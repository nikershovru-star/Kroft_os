"""Bootable KROFT_OS entry point — single command lifts the whole stack (ТЗ-RUN-01, ADR-099, Флаг C).

K5: PURE COMPOSITION over already-shipped components — NO new contract/port. Reuses:
  - build_kernel (composition/kernel_factory.py) — boot the CognitiveKernel.
  - SkillEvolver (EVOLUTION-01) + InMemoryProceduralMemory — self-evolving skills.
  - build_default_dashboard (DESKTOP-01) — read-only kernel-state snapshot + renderer.
  - build_llm_client / OmniRouter (OMNI-01) — optional LLM advisor (graceful degradation).
  - SkillDistributor + SkillRepository + ReferenceTrustRegistry (FED-REPL-01 / IDT-01) — optional
    federation (graceful degradation when disabled).
  - SubprocessSandbox (ADR-039), HmacSigner (CRYPTO-01) — injected dependencies.
Does NOT duplicate run_evolution.py (ТЗ-LIVE-01): that script owns persistence/autosave/live-loop;
this entry point is the higher-level "boot EVERYTHING + show dashboard + demo evolution" aggregator.
run_evolution can be layered on top (it imports the same build_kernel).

Graceful degradation: LLM and federation are OPTIONAL. Without them the app boots and runs a
deterministic, LLM-free evolution demo (I-09). No network or external model required.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any, List, Optional

from contracts.cognitive_domain import ConfidenceScore, Intent, Provenance
from contracts.i_llm import ILlm
from composition.desktop_dashboard_factory import build_default_dashboard
from composition.kernel_factory import build_event_bus
from kernel.cognitive_kernel import build_kernel as build_cognitive_kernel
from kernel.memory_store import InMemoryLayeredMemory
from services.memory_platform import InMemoryProceduralMemory
from services.skill_evolution import SkillEvolver


@dataclass
class KroftConfig:
    """Run configuration for the bootable stack (ТЗ-RUN-01)."""

    node_id: str = "nodeA"
    llm: str = "none"          # "none" (LLM-free deterministic) | "auto" | "mock"
    federation: bool = False    # enable SkillDistributor federation layer
    ticks: int = 5             # demo loop iterations
    run_demo: bool = True      # execute the live-demo loop on __main__


class KroftApp:
    """Bootable KROFT_OS: kernel + optional LLM + evolution + optional federation + dashboard.

    Read-only dashboard reflects live state; evolution uses the existing SkillEvolver (LLM-free by
    default). Federation is opt-in (graceful degradation). The app never mutates kernel HARD/FSM via
    the dashboard (DESKTOP-01 read-only contract).
    """

    def __init__(self, config: Optional[KroftConfig] = None) -> None:
        self.config = config or KroftConfig()
        # 1) memory stores: layered (kernel reasoning) + procedural (skills / evolution)
        self.memory = InMemoryLayeredMemory()
        self.procedural = InMemoryProceduralMemory()
        from adapters.subprocess_sandbox import SubprocessSandbox
        self._sandbox = SubprocessSandbox()
        self.evolver = SkillEvolver(self._sandbox, self.procedural, min_uses=2, success_threshold=0.8)
        # 2) optional LLM advisor (graceful degradation: None = LLM-free deterministic)
        self.llm: Optional[ILlm] = self._build_llm(self.config.llm)
        # 3) kernel (CognitiveKernel) via the shared composition factory
        self.bus = build_event_bus()
        self.kernel = build_cognitive_kernel(
            node_id=self.config.node_id, llm_client=self.llm,
            memory=self.memory, procedural=self.procedural,
        )
        # 4) optional federation (graceful degradation: disabled by default)
        self.distributor: Any = None
        self.trust: Any = None
        if self.config.federation:
            self._wire_federation()
        # 5) dashboard (read-only snapshot of the live stack)
        self.dashboard = build_default_dashboard(
            kernel=self.kernel,
            memory_platform=self.procedural,
            trust_registry=self.trust,
        )
        self._seed_demo_skill()

    def _build_llm(self, mode: str) -> Optional[ILlm]:
        if mode == "none":
            return None  # LLM-free deterministic run (I-09)
        if mode == "mock":
            return _MockLlm()
        # "auto": build a real client (endpoint may be unreachable; we never call it in the demo)
        try:
            from composition.llm_client_factory import build_llm_client
            return build_llm_client()
        except Exception:
            return None

    def _wire_federation(self) -> None:
        from adapters.hmac_signer import HmacSigner
        from infrastructure import InMemoryEventBus
        from kernel.identity import ReferenceTrustRegistry
        from services.skill_distributor import SkillDistributor
        from services.skill_marketplace import SkillRepository
        from composition.capstone_distributed import LoopbackTransport
        self.trust = ReferenceTrustRegistry()
        signer = HmacSigner(b"kroft-shared-secret")
        repo = SkillRepository(signer=signer)
        # LoopbackTransport expects an InMemoryEventBus with a `members` registry (infrastructure bus).
        fed_bus = InMemoryEventBus()
        if not hasattr(fed_bus, "members"):
            fed_bus.members = []  # duck-typed compat for LoopbackTransport membership check
        self.distributor = SkillDistributor(
            self.config.node_id, repo, LoopbackTransport(fed_bus), self.trust
        )

    def _seed_demo_skill(self) -> None:
        """Seed a low-efficiency skill so the evolution loop has something to improve (deterministic)."""
        from contracts.i_memory import Procedure
        self._demo_skill = Procedure(
            skill_id="demo.v1", name="demo", capability="demo",
            steps=("echo ok", "exit 1 # low-eff step"), version=1, confidence=0.7,
        )
        try:
            self.procedural.store_skill(self._demo_skill)
        except Exception:
            pass

    def step(self, goal_text: str = "demo goal") -> Any:
        """Advance one tick (kernel FSM) + evolve the demo skill; return a read-only dashboard snapshot."""
        from contracts.cognitive_domain import ConfidenceScore, Provenance
        self.kernel.tick(Intent(id="intent-1", text=goal_text, confidence=ConfidenceScore(0.8),
                                provenance=Provenance(source="demo", actor="run_kroft")))
        # Evolution: low-efficiency usage stats -> SkillEvolver proposes a better variant (LLM-free)
        from contracts.i_skill_evolver import SkillUsageStats
        self.evolver.evolve_skill(
            self._demo_skill, SkillUsageStats(capability="demo", uses=10, success_rate=0.3)
        )
        return self.dashboard.snapshot()

    def run_demo(self, ticks: Optional[int] = None) -> List[Any]:
        """Live-demo loop: tick + evolve, printing a read-only dashboard snapshot each iteration.

        Deterministic without an LLM (I-09); evolution uses the LLM-free SkillEvolver heuristic.
        """
        ticks = ticks if ticks is not None else self.config.ticks
        snaps: List[Any] = []
        print(f"[run_kroft] booting node={self.config.node_id} "
              f"(llm={self.config.llm}, federation={self.config.federation})")
        for i in range(max(0, ticks)):
            snap = self.step()
            snaps.append(snap)
            print(f"\n=== tick {i + 1}/{ticks} ===")
            print(self.dashboard.render_text(snap))
        print(f"\n[run_kroft] demo complete: {ticks} ticks, "
              f"skills in memory={self.dashboard.render_json(snaps[-1]) is not None}")
        return snaps


class _MockLlm(ILlm):
    """Deterministic mock ILlm for demo runs (no network)."""

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return f"[mock] {prompt[:32]}"

    def stream(self, prompt: str, **kwargs: Any):
        yield f"[mock] {prompt[:32]}"


def _parse_args(argv: Optional[List[str]] = None) -> KroftConfig:
    p = argparse.ArgumentParser(description="Bootable KROFT_OS — lift the whole stack + live demo")
    p.add_argument("--node-id", default="nodeA")
    p.add_argument("--llm", choices=["none", "auto", "mock"], default="none")
    p.add_argument("--federation", action="store_true", help="enable SkillDistributor federation layer")
    p.add_argument("--ticks", type=int, default=5)
    p.add_argument("--no-demo", action="store_true", help="boot only, do not run the demo loop")
    a = p.parse_args(argv)
    return KroftConfig(
        node_id=a.node_id, llm=a.llm, federation=a.federation,
        ticks=a.ticks, run_demo=not a.no_demo,
    )


def main(argv: Optional[List[str]] = None) -> int:
    config = _parse_args(argv)
    app = KroftApp(config)
    if config.run_demo:
        app.run_demo()
    else:
        print(f"[run_kroft] booted node={config.node_id} (no-demo); services ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Capstone composition helper (ТЗ-CAPSTONE-01, ADR-085) — end-to-end self-evolving federated mesh.

K5 (commit 0): НЕ дублирует порты. Разведка подтвердила, что ВСЕ слои уже готовы и переиспользуются:
- `build_kernel(node_id, llm_client=)` — когнитивный цикл + самоэволюция (reflection -> soft policy /
  semantic fact), авто-публикует SOFT-слой через `attach_soft_memory_sync` (ТЗ-OBS/SE-01).
- `FederationSoftMemorySync(node_id, memory, transport, signature_provider=, replay_guard=)` — FSE-01
  cross-node обмен знаниями (SoftLayerItem) С ВЕРИФИКАЦИЕЙ (CRYPTO-01) + replay-guard (HARDEN-01).
- `build_federated_node(transport, orchestrator, trust, node_id, signature_provider=, replay_guard=)`
  — FED-EXEC удалённое исполнение целей + trust-эволюция из verified исходов (опц., для демонстрации
  удалённого исполнения поверх той же сети).
- `build_hmac_signer(key)` + `ReplayGuard()` — аутентификация происхождения + replay-защита.
- `detect_local_ollama()` + `build_llm_client()` — опц. реальный локальный LLM-советник (skip if none).
- `ProcedureConsolidator` / `SkillEvolution` — skill-loop (ТЗ-SKILL-EVOLVE-01), переиспользуются
  сценарием (Commit 2) для замыкания опыта -> навык.

Флаг C: standalone-фабрика, НЕ в build_kernel (god-factory не раздуваем).
K1/K6: composition.* -> всё (gate rule); kernel/services/adapters НЕ cross-import.
K8/O1: verify-before-trust + replay-guard сохранены (shared key + per-node ReplayGuard).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from contracts.i_network_transport import INetworkTransport
from kernel.cognitive_kernel import build_kernel
from kernel.crypto import ReplayGuard, build_hmac_signer
from kernel.identity import (
    ReferenceActionLog,
    ReferenceIdentityRegistry,
    ReferenceTrustRegistry,
)
from kernel.orchestrator import build_orchestrator
from services.distributed_runtime import FederationSoftMemorySync
from composition.llm_client_factory import build_llm_client, detect_local_ollama


@dataclass
class CapstoneMesh:
    """Two authenticated, self-evolving federated nodes wired for cross-node knowledge exchange.

    `node_a` / `node_b` are CognitiveKernels (cognitive loop + self-evolution). `sync_a` / `sync_b`
    are the FSE-01 soft-layer sync handlers (verify-before-trust + replay-guard). `transports` are the
    caller-supplied INetworkTransport instances (real TCP in production, fakes in tests). `signer`
    is the shared-key HMAC provider; `replay_a` / `replay_b` are per-node replay windows.
    """

    node_a: object
    node_b: object
    sync_a: "FederationSoftMemorySync"
    sync_b: "FederationSoftMemorySync"
    transport_a: "INetworkTransport"
    transport_b: "INetworkTransport"
    trust_a: "ReferenceTrustRegistry"
    trust_b: "ReferenceTrustRegistry"
    signer: object
    replay_a: "ReplayGuard"
    replay_b: "ReplayGuard"
    llm_a: Optional[object] = None
    llm_b: Optional[object] = None


def _maybe_llm(use_real_llm: bool, base_url: str, timeout: float):
    if not use_real_llm:
        return None
    if not detect_local_ollama(host=base_url.rsplit("/v1", 1)[0] or "http://localhost:11434",
                               timeout=timeout):
        return None  # best-effort: no local model -> LLM-free (deterministic, I-09)
    try:
        return build_llm_client(base_url=base_url, timeout=timeout)
    except Exception:  # noqa: BLE001 — optional advisor; degrade to LLM-free
        return None


def build_capstone_mesh(
    transport_a: "INetworkTransport",
    transport_b: "INetworkTransport",
    *,
    node_a_id: str = "A",
    node_b_id: str = "B",
    shared_key: bytes = b"capstone-shared-secret",
    use_real_llm: bool = False,
    llm_base_url: str = "http://localhost:11434/v1",
    llm_timeout: float = 5.0,
    trust_seed: float = 0.9,
    confidence_threshold: float = 0.5,
) -> "CapstoneMesh":
    """Build two authenticated, self-evolving federated nodes (ТЗ-CAPSTONE-01).

    Reuses the FULL existing substrate: cognitive kernel (self-evolution loop) + FSE-01 soft-layer
    sync with CRYPTO-01 signature verification + HARDEN-01 replay-guard. A single shared-key HMAC
    signer authenticates both directions; each node owns its own ReplayGuard (per-origin monotonic
    window over CausalMark.lamport). Real LLM is optional and best-effort (skip if not available).

    The caller owns the transports (real TCP or fakes). After building, ensure the transports are
    connected (see CapstoneMesh note) before driving the self-evolution loop.
    """
    signer = build_hmac_signer(shared_key)
    replay_a, replay_b = ReplayGuard(), ReplayGuard()

    trust_a = ReferenceTrustRegistry()
    trust_a.seed(node_a_id, trust_seed)
    trust_a.seed(node_b_id, trust_seed)
    trust_b = ReferenceTrustRegistry()
    trust_b.seed(node_a_id, trust_seed)
    trust_b.seed(node_b_id, trust_seed)

    llm_a = _maybe_llm(use_real_llm, llm_base_url, llm_timeout)
    llm_b = _maybe_llm(use_real_llm, llm_base_url, llm_timeout)

    node_a = build_kernel(node_a_id, llm_client=llm_a)
    node_b = build_kernel(node_b_id, llm_client=llm_b)

    sync_a = FederationSoftMemorySync(
        node_a_id, node_a._memory, transport_a,
        confidence_threshold=confidence_threshold, trust_registry=trust_a,
        signature_provider=signer, replay_guard=replay_a,
    )
    sync_b = FederationSoftMemorySync(
        node_b_id, node_b._memory, transport_b,
        confidence_threshold=confidence_threshold, trust_registry=trust_b,
        signature_provider=signer, replay_guard=replay_b,
    )
    node_a.attach_soft_memory_sync(sync_a)
    node_b.attach_soft_memory_sync(sync_b)

    return CapstoneMesh(
        node_a=node_a, node_b=node_b, sync_a=sync_a, sync_b=sync_b,
        transport_a=transport_a, transport_b=transport_b,
        trust_a=trust_a, trust_b=trust_b, signer=signer,
        replay_a=replay_a, replay_b=replay_b, llm_a=llm_a, llm_b=llm_b,
    )


def run_capstone_self_evolution(
    mesh: "CapstoneMesh",
    *,
    fail_intent_text: str = "choose_red",
    success_intent_text: str = "choose_blue",
    learn_cycles: int = 4,
    intent_factory=None,
    planner_a=None,
    planner_b=None,
) -> dict:
    """Drive node A's self-evolution loop and propagate to node B (ТЗ-CAPSTONE-01, Commit 2).

    A runs `learn_cycles` ticks repeatedly FAILING on `fail_intent_text` -> learns a soft AVOID policy
    (self-evolution: experience -> reflection -> soft policy). On each publish tick the FSE-01 sync
    ships the SOFT layer to B WITH signature (CRYPTO-01) + per-item monotonic seq (HARDEN-01 replay-guard).
    B's receiver verifies before merge, so B acquires the SAME avoid policy and changes its next
    decision. Returns a result dict with provenance for assertions.

    Deterministic without LLM (I-09): the kernel's reference planner/executor are deterministic; the
    avoid policy is a pure function of observed failures. Real LLM (if wired in build_capstone_mesh)
    only augments the advisor — the loop still closes deterministically.

    Planners: A is wired with a FIXED planner proposing `fail_intent_text` (forced failure so A learns);
    B is wired with a BOTH planner (offers fail + safe alt) so that WITHOUT federation B would pick the
    failed candidate, and AFTER receiving A's avoid policy B avoids it. Reuses ReferenceExecutor
    (fails on `choose_red`); both delegates already exist in the kernel (K5, no new ports).
    """
    from contracts.cognitive_domain import (
        ConfidenceScore, Intent, Plan, Provenance, ProvenanceType,
    )
    from contracts.i_planner import IPlanner
    from kernel.execution import ReferenceExecutor

    if intent_factory is None:
        def intent_factory(text):
            return Intent(id=f"i:{text}", text=text,
                          confidence=ConfidenceScore(0.9, ProvenanceType.OBSERVATION),
                          provenance=Provenance(source="u", actor="u"))

    class _FixedPlanner(IPlanner):
        def __init__(self, steps): self._steps = steps
        def plan(self, goal, steps, world, budget, intent=None):
            return [Plan(id="p", goal_id=goal.id, steps=self._steps,
                         confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                         provenance=Provenance(source="t", actor="t"))]

    class _BothPlanner(IPlanner):
        def __init__(self, failed, alt): self._failed, self._alt = failed, alt
        def plan(self, goal, steps, world, budget, intent=None):
            return [
                Plan(id="pf", goal_id=goal.id, steps=self._failed,
                     confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                     provenance=Provenance(source="t", actor="t")),
                Plan(id="pa", goal_id=goal.id, steps=self._alt,
                     confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                     provenance=Provenance(source="t", actor="t")),
            ]

    node_a, node_b = mesh.node_a, mesh.node_b
    node_a.attach_executor(ReferenceExecutor())
    node_b.attach_executor(ReferenceExecutor())
    node_a._planner = planner_a or _FixedPlanner((fail_intent_text,))
    node_b._planner = planner_b or _BothPlanner((fail_intent_text,), (success_intent_text,))

    # Phase 1: A learns to AVOID fail_intent_text via repeated failure (self-evolution loop).
    for _ in range(learn_cycles):
        node_a.tick(intent_factory(fail_intent_text))
    a_avoid = [p.body for p in node_a._memory.get_normative()
               if getattr(p, "layer", None) == "soft" and "avoid" in p.body]
    learned = any(fail_intent_text in a for a in a_avoid)

    # Phase 2: trigger one more A publish so the latest soft policy ships to B over the channel.
    node_a.tick(intent_factory(fail_intent_text))

    # Phase 3: B receives + verifies (signature + replay) then merges; B changes behavior.
    # B offers BOTH the failed candidate and a safe alternative; WITHOUT federation it would pick
    # the failed one. After receiving A's avoid policy it must AVOID fail_intent_text.
    node_b.tick(intent_factory(fail_intent_text))
    b_avoid = [p.body for p in node_b._memory.get_normative()
               if getattr(p, "layer", None) == "soft" and "avoid" in p.body]
    b_changed = any(fail_intent_text in b for b in b_avoid)
    b_picked_before = node_b._last_selected_plan.steps if node_b._last_selected_plan else None
    node_b.tick(intent_factory(fail_intent_text))
    b_picked_after = node_b._last_selected_plan.steps if node_b._last_selected_plan else None

    return {
        "a_learned_avoid": learned,
        "a_avoid_policies": a_avoid,
        "b_received_avoid": b_changed,
        "b_avoid_policies": b_avoid,
        "b_picked_before": b_picked_before,
        "b_picked_after": b_picked_after,
        "trust_a_b": mesh.trust_a.current_trust(mesh.node_b._node_id),
        "trust_b_a": mesh.trust_b.current_trust(mesh.node_a._node_id),
    }

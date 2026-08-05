---
id: ADR-085
title: Capstone — end-to-end self-evolving federated cognitive OS (ТЗ-CAPSTONE-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-082
  - ADR-084
  - ADR-066
  - ADR-074
  - ADR-075
  - ADR-076
  - ADR-079
  - ADR-054
tz: TZ-CAPSTONE-01
laws:
  - K1
  - K5
  - K6
  - K8
  - O1
  - I-09
evidence_level: V
---

# ADR-085 — Capstone: end-to-end self-evolving federated cognitive OS (ТЗ-CAPSTONE-01)

## Context

All layers are built and hardened in isolation: cognitive loop, self-evolution (local + federated +
skill-loop), memory (all layers), network (real TCP, remote agent exec), identity/trust
(authenticated, replay-protected), LLM-transport (real HTTP + fallback), plugins, observability,
crypto-hardening. The capstone proves they work **together end-to-end**: two authenticated federated
nodes where node A's self-evolution (experience → reflection → soft policy) is shipped to node B over a
verified + replay-guarded channel, and B changes its behavior from A's knowledge. No new ports/layers —
the capstone only integrates existing substrate (K5).

## K5 reconnaissance (commit 0)

Everything already exists; nothing new:
- `build_kernel(node_id, llm_client=)` — cognitive loop + self-evolution; auto-publishes SOFT layer via
  `attach_soft_memory_sync` (ТЗ-OBS/SE-01). `ReferenceExecutor` fails on `choose_red` → `memory_evolution`
  emits `avoid:decided:choose_red` soft policy (ТЗ-SE-01).
- `FederationSoftMemorySync(node_id, memory, transport, signature_provider=, replay_guard=)` — FSE-01
  cross-node knowledge exchange WITH CRYPTO-01 signature verification + HARDEN-01 replay-guard.
- `build_federated_node(..., signature_provider=, replay_guard=)` — FED-EXEC remote goal execution +
  trust evolution from verified outcomes (optional, for demonstrating remote execution over the same net).
- `build_hmac_signer(key)` + `ReplayGuard()` — auth + replay (CRYPTO-01/HARDEN-01).
- `detect_local_ollama()` + `build_llm_client()` — optional real local LLM advisor (skip if unavailable).
- `ProcedureConsolidator` / `SkillEvolution` — skill-loop (ТЗ-SKILL-EVOLVE-01), reusable in the runner.

## Decision

1. **Composition helper** (`composition/capstone.py`, Флаг C, NOT in build_kernel):
   `build_capstone_mesh(transport_a, transport_b, *, shared_key, use_real_llm, ...)` → `CapstoneMesh`
   with two `build_kernel` nodes, each wired to a `FederationSoftMemorySync` over the supplied transports,
   sharing ONE `HmacSigner` (shared key) + per-node `ReplayGuard`. Trust seeded 0.9 both directions. Real
   LLM is best-effort optional (detected via `detect_local_ollama`, else LLM-free → deterministic).
2. **Scenario runner** (`run_capstone_self_evolution(mesh, ...)`): drives node A's self-evolution loop
   (A wired with a fixed planner proposing `choose_red` → forced failure → learns `avoid:decided:choose_red`;
   B wired with a both-planner so it would pick the failed candidate WITHOUT federation). On each publish
   tick FSE-01 ships the SOFT layer to B (signed + per-item monotonic seq); B verifies before merge and
   switches its next decision to the safe alternative. Returns a result dict (a_learned_avoid / b_received_avoid
   / b_picked_after / trust) for assertions.
3. **Determinism without LLM** (I-09): reference planner/executor are deterministic; the avoid policy is a
   pure function of observed failures. Real LLM only augments the advisor; the loop still closes.

## Constraints (закрыты)

- **K1/K5/K6**: composition.* → everything (gate rule); kernel/services/adapters do NOT cross-import; no
  new ports (reuses build_kernel, FederationSoftMemorySync, HmacSigner, ReplayGuard, build_llm_client).
- **K8**: verify-before-trust + replay-guard preserved at the FSE-01 boundary (tampered/replayed/unsigned
  items rejected).
- **O1**: self-evolution is SOFT; HARD/FSM untouched.
- **I-09**: deterministic without LLM; correlation by request_id in the network layer.
- **Флаг C**: standalone factories, NOT in build_kernel.

## Consequences

The capstone is the integration proof of the whole vision: local self-evolution → authenticated +
replay-protected cross-node knowledge exchange → remote behavior change. The crypto layer (CRYPTO-01 /
HARDEN-01) is exercised as the federation trust boundary, not bolted on.

## Non-scope / future debt

- Asymmetric crypto (Ed25519/ECDSA/RSA), key rotation/PKI — ADR-082/084 non-scope.
- Multi-hop routing / discovery / consensus — separate waves.
- Real-LLM semantic differences across nodes — optional, best-effort; not required for the loop to close.

## Verification

- `tests/test_capstone_self_evolution.py`: **4 K8 passed** (end-to-end loop closes + propagates; tampered/
  replayed/unsigned rejected; replayed soft layer not merged; deterministic without LLM).
- Smoke (loopback, no sockets/LLM): A learns `avoid:decided:choose_red`; B receives via authenticated +
  replay-guarded channel and acquires the same policy. PASS.
- Full suite 0 failed; arch-gate 14 passed; akb-lint PASSED.

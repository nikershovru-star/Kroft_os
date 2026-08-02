# Changelog

All notable changes to KROFT_OS are documented here, grouped by ТЗ/Wave.
Format: `commit-range | scope | summary`.

---

## 2026-08-02 — ТЗ-RE-01 (Reasoning Engine W2-gap) — DONE

`47d96bd 4ac6ce5 0f86b9f 1a66633 cd525df <docs>`

- **flag 1 — Single node Lamport clock.** `NodeLamportClock` (shared holder) injected
  into `CognitiveKernel` + `InMemoryWorldState` + `SharedContextService`. Removed the
  three independent `self._clock` instances. `node_origin` is now `node_id` everywhere
  (was hardcoded `"kernel"`), fixing causal order + federation tiebreak.
- **Reasoning Engine (parametric Deliberate component).** New `IReasoningEngine` port
  + frozen `ReasoningStep` (carries `ConfidenceScore` + `CausalMark` from the shared
  clock). `ReferenceReasoningEngine` is deterministic, LLM-free (I-09): reads Intent +
  WorldState via Attention, yields world-aware candidates. `CognitiveKernel.tick` runs
  **Reasoning → Planning → Decision**; planner signature extended to `(goal, steps)`.
- **flag D — World-aware Decision.** `IDecisionEngine.select` now receives `world` +
  `intent` via the port. `DeterministicDecisionEngine` accepts them (ignores for
  determinism). The `bind()` hack in the federation test engine is removed.
- **flag 3 — Wire key.** Federation wire emits `lamport` (was legacy `seq`).
- **Tests (K8).** `tests/test_reasoning_engine.py` (+8): acceptance + negative (reasoning
  without a world fact yields a *different* candidate; explore-only assertion).
- **Docs.** `ADR-056` (accepted) — Reasoning Engine; amendment to ADR-055 §6
  (state idempotence vs order-dependent clock, per flag 2).

**Verification:** full suite `1010 passed, 19 skipped, 1 xpassed, 0 failed`;
arch-gate `14 passed`; akb-lint PASSED.

---

## 2026-08-02 — ТЗ-CAUSAL-01 (CausalMark → Lamport) — DONE (prior)

`65a3ee2 3724248 23dc711`

- `CausalMark` rebased on Lamport logical clock (`lamport` / `node_origin`,
  `__lt__` by `(lamport, node_origin)`).
- `merge_remote` + `InMemoryWorldState.update` do `receive` on remote facts; local
  events do `tick()`. Idempotent replay (clock grows only on causally-newer marks).
- `tests/test_causal_mark_lamport.py` (+9 tests). Wire key emitted as `seq` (renamed
  to `lamport` in ТЗ-RE-01).

**Verification:** `1002 passed, 0 failed`; gate `14 passed`; ad-hoc `13/13 PASS`.

---

## Baseline — v1.0 (ТЗ-002 D2)

V1/V2/V3 CLOSED, No High Architectural Debt. Metrics: `768 passed / 0 failed /
0 open violations`.

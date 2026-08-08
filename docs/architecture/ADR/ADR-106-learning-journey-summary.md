---
id: ADR-106
title: Learning Journey Summary (Slice 1–7) — autonomous execution-to-skill loop
status: ACCEPTED
date: 2026-08-08
tags: [learning, execution, experience-ranking, persistence, K5, K6, SLICE-1-7]
supersedes: []
relates: [ADR-054 (Reasoning→Planning→Decision), ADR-065 (LLM-as-advisor), ADR-103 (Agent Runtime), ADR-104 (Blackboard), ADR-105 (Browser Adapter, deferred), RFC-009/010 (Multi-Agent)]
---

# ADR-106 — Learning Journey Summary (Slice 1–7)

## Context

KROFT_OS must not only *plan* and *act*, but *learn from acting*: a real executed action
should feed back into future planning so the system gets better (or more cautious) with
experience, and the knowledge must survive restarts. Slices 1–7 closed this loop as a set of
small, additive, architecturally-clean vertical slices (K5/K6). This ADR records what was
**proven**, the **single formula** that drives experience bias, the **consciously dead/deferred**
parts, and the **invariants** that must hold going forward.

No new layers, ports, or DTOs were introduced. Every change stayed inside `kernel/` (planning,
cognitive_kernel, llm_advisor, config, builder) and `composition/run_kroft.py`, reusing existing
contracts (`IPlanner`, `IExecutor`, `IProceduralMemory`, `ILLMAdvisor`, `IEpisodeStore`).

## Decision — what is proven (Slice 1–7)

| Slice | Capability | Proof |
|-------|------------|-------|
| 1–3 (D3) | **NL-goal → execution_steps** | `"запиши hello в x.txt"` yields `Plan.execution_steps=({'kind':'file','path':'x.txt','content':'hello'},)` without manual injection (planner recognises file/command intent from the goal). |
| 3-alt | **Real execution** | `RealWorldExecutor` (wired via `kernel.attach_executor`) records REAL success/failure outcomes (not the always-success proxy). File is actually written to disk. |
| 3-alt | **Episodic retrieval as provenance** | A similar goal's plan carries a `past-experience: <episode summary>` step, reusing past context. Retrieval is **provenance**, not a re-ranking signal. |
| 4 | **Experience-informed ranking (mechanism)** | `_apply_experience_ranking` biases `Plan.confidence` by `procedural._procedures[f"exec:{kind}"].success_rate`. |
| 5 | **Live wiring** | `KroftConfig.procedural` → `build_kernel` → `KernelBuilder` → `ReferencePlanner`/`LLMAdvisorPlanner`. Previously the mechanism existed but nobody passed the memory in (dormant); now it is ACTIVE in the real loop (`app.kernel._planner._procedural is app.procedural`). |
| 5 (hygiene) | **Single-write learning** | `_outcomes` consumed via a high-water mark; `_procedures['runs']` increments only by NEW outcomes (3 steps → runs==3, not N-fold). SkillEvolver still gets cumulative `uses` for its `min_uses` gate. |
| 6 | **Symmetric experience formula** | `adj = clamp(base + (sr - 0.5) * 0.4, 0, 1)`: success raises, failure lowers, sr==0.5 is a no-op (continuity). |
| 6 | **Lean episodes** | `episode.summary` = `decided:<steps>||exec:<kind>:<path|cmd>` — file **content is NOT embedded**; retrieval works via path/cmd token overlap. |
| 6 | **Bounded outcomes** | `_outcomes` trimmed to a 64-window with watermark shift; observers see a bounded list. |
| 7 | **Capstone end-to-end** | One `app.step`-driven scenario asserts every link: D3 → real file on disk → single-write (runs==3, sr==1.0) → lean episode → retrieval (past-experience) → ranking (success boosts, failure penalizes) → cold-boot restore (procedural + episodic) → post-restart retrieval + ranking still active. |
| 8 | **Advisor consistency** | `LLMAdvisorPlanner`'s advisor plan now rides `_apply_experience_ranking` too (previously bypassed it). `advisor=None` keeps pure reference behaviour. |

## Decision — the formula (Slice 6)

```
adj = clamp( base + (success_rate - 0.5) * 0.4 , 0.0, 1.0 )
```

where `base` = the candidate's predicted value-aware utility, and `success_rate` =
`procedural._procedures[f"exec:{kind}"].success_rate` (or `successes/runs` if not normalised).

**Properties (all required, all satisfied):**
- Deterministic for a given memory state.
- Monotonic in `success_rate`.
- `adj > base` when `sr > 0.5` (learned success raises confidence).
- `adj < base` when `sr < 0.5` (learned failure lowers confidence).
- `adj == base` when `sr == 0.5` (continuity at the neutral point).
- Clamped to `[0, 1]`.
- Unknown capability (no entry / `runs == 0`) → `adj == base` (abstract deliberation
  `choose_blue`/`red`, which has no `execution_steps`, is never touched → stays deterministic).

The `0.4` weight is a tuning constant; it is small enough to never override a hard value-veto
(utility 0) and large enough to be observable across a few runs.

## Consciously dead / deferred (not bugs)

- **Desktop execution (P.6)** — blocked by policy; not driven through NL-goal. Ranking still
  works for it *if* a capability entry exists, but no NL path produces desktop `execution_steps`.
- **Browser execution adapter (ADR-105)** — explicitly **deferred**; no production-ready browser
  backend exists. Documented, not implemented.
- **Minimal NL grammar** — only `запиши/сохрани/… в <path>`, `выполни/run/echo <cmd>`, and the
  `exec:/write:/click:` markers are recognised. No general NL understanding; intentional (K5).
- **Retrieval does NOT influence selection** — past-experience is added as *provenance* to all
  candidates uniformly; the *differential* experience signal is applied by ranking (Slice 4–6) on
  the SAME capability's `success_rate`. Feeding retrieval into selection too would be **double
  counting the same signal** — deliberately avoided.
- **Advisor active only with a real LLM** — `llm="none"` (deterministic, offline) is the default
  and the proven path. The LLM advisor re-rank is opt-in and was consistency-fixed in Slice 8, but
  it remains dormant until a real `ILLMAdvisor` is wired.

## Invariants (must hold)

- **K1** — `kernel/planning.py` and `kernel/llm_advisor.py` import ONLY contracts + stdlib.
- **K3** — no service/runtime instantiation in `kernel/`; `composition/run_kroft.py` is the only
  place that wires `InMemoryProceduralMemory` / `RealWorldExecutor` into the kernel.
- **K6** — changes confined to `kernel/` (planner/config/builder) + `composition/`; no new port,
  layer, or DTO.
- **K8** — no runtime import of `docs/architecture/akb/`; the architecture knowledge base is
  documentation only.
- **Determinism of abstract deliberation** — `choose_blue`/`choose_red` (no `execution_steps`)
  never receive an experience bias, so the reference decision outcome is byte-stable regardless of
  accumulated procedural memory.
- **Single-write accounting** — each real action increments `runs` exactly once; the SkillEvolver
  gate uses cumulative `uses` without disturbing that invariant.

## Consequences

- KROFT_OS demonstrably learns from real execution (success → higher confidence; failure →
  lower) and remembers across restarts, with bounded memory and lean episodes.
- The loop is fully LLM-free by construction; the optional LLM advisor is a pure re-rank that now
  rides the same experience bias as the reference path.
- Future strategy (real LLM synthesis, desktop opt-in, richer retrieval) is an **owner decision**,
  not an agent action; this ADR closes the Slice 1–7 arc.

---
id: ADR-100
title: Vertical Slice Arc — Autonomous Skill Acquisition (Slice 1–9)
status: accepted
date: 2026-08-08
decision-source: ТЗ-driven vertical slices (owner-reviewed, K5/K6 discipline)
supersedes: — (caps the Slice 1–9 arc; superseded-by: none yet)
---

# ADR-100 — Vertical Slice Arc: Autonomous Skill Acquisition (Slice 1–9)

## Context

KROFT_OS must not only *reason* about tasks — it must **act in the real OS**, observe the
outcome, **learn a reusable skill** from it, and **reuse** that skill on analogous future
goals. The capability was built as nine small vertical slices, each inspected → changed →
tested → proven against the live kernel, never as a big-bang rewrite. This ADR is the
closing summary of that arc: it records the decisions, the ranking formula, the invariants
that held, and what was consciously deferred.

Architecture constraints throughout (the owner's standing mandate):
- **K5** — reuse existing components; never build a parallel implementation.
- **K6** — a change lives only in its allowed layer (`kernel/` core, `adapters/` ports impls,
  `composition/` wiring, `tests/` proofs). `contracts/` is touched only to *add* a port that
  already existed elsewhere or was explicitly pre-approved.
- **No `git add -A`**; atomic per-slice commits, named, only after a green suite.
- **Verification gate** — every slice ships a *real* proof (spy / live-adapter / deterministic
  mock), not a "fallback works" test. Live paths are gated by an env flag and skip gracefully.

## Decision — the nine slices

| # | Slice | Decision | Proof |
|---|-------|----------|-------|
| 1 | D3 autonomy — NL intent → real action | `ReferencePlanner` emits `execution_steps`; kernel routes them to a real `IExecutor` | real `echo`/`file` runs |
| 2 | Real execution backend | `RealWorldExecutor` (composition root) routes `Action.kind` → real adapters (filesystem, terminal, desktop) | file write+read, echo |
| 3 | Single-write learning | `observe(outcome)` → ONE skill evolution write per real action (high-water mark) | no N-fold accumulation |
| 4 | Lean episodes | `Episode` carries only `summary` (e.g. `exec:file:x.txt`) — no raw payload bloat | episode persisted |
| 5 | Retrieval-as-provenance | past episodes injected into planner context (`past-experience`) | plan references prior episode |
| 6 | Symmetric experience-ranking | `_apply_experience_ranking` ranks candidates by past success rate, same path for planner & advisor | consistent ranking |
| 7 | Live wiring | executor attached via `CognitiveKernel.attach_executor` (post-hoc, K5) | real outcomes recorded |
| 8 | Bounded outcomes | outcome tensors bounded; capstone end-to-end + advisor consistency | suite green |
| 9 | Embedding retrieval + cache + desktop opt-in | semantic episodic retrieval (cosine over `IEmbedding`), episode-embedding cache, default-deny desktop with explicit opt-in | synonym retrieval, cache hits, deny/allow |

## Decision — experience-ranking formula (Slice 6, stable)

Candidate ranking uses a **value-aware, experience-informed** score. The planner ranks by
predicted utility; the experience layer biases confidence by past success rate:

```python
# kernel/planning.py — _apply_experience_ranking (Slice 6, stable)
adj = clamp(base + (sr - 0.5) * 0.4, 0, 1)
# sr == success_rate of procedural[f"exec:{kind}"]; sr == 0.5 is a no-op (continuity),
# sr > 0.5 raises confidence, sr < 0.5 lowers it. Only execution-intent candidates
# (file/command) are adjusted; abstract deliberation is untouched.


where `success_rate` / `failure_rate` come from `InMemoryProceduralMemory` (seeded from real
tick outcomes via `SkillEvolver`, `min_uses=2`, `success_threshold=0.8`). The same
`_apply_experience_ranking` is applied in both the planner path and the LLM-advisor path
(Slice 6 consistency fix), so a skill that worked in deliberation is the one the advisor
recommends. Provenance is preserved (`RULE_INFERENCE` for the kernel-ranked plan; the
advisor plan keeps its own provenance — a known minor cosmetic gap, not behavioural).

## Decision — semantic retrieval + cache (Slice 9, stable)

`_retrieve_similar_episodes(text)` has two paths, selected by whether an `IEmbedding` adapter
is wired into `CognitiveKernel`:

- **Semantic** (`embedding is not None`): cosine similarity between `embed(text)` and
  `embed(ep.summary)` for every episode; threshold `sim >= 0.5`; adapter error → graceful
  `[]` (no retrieval, no crash).
- **Keyword fallback** (`embedding is None`, default): token-overlap (`len(token) > 2`) over
  `ep.summary`; deterministic, network-free.

Episode-embedding **cache** (`_embedding_cache: summary→vector`, `_query_cache: text→vector`)
ensures `embed(ep.summary)` is called **once per unique summary**; invalidated on
`record_episode` via the `on_record_episode` memory hook; rebuilt lazily on next retrieval.
Cache is in-memory only (not persisted — acceptable for a cache).

Local embeddings need **no API key**: `OllamaEmbeddingAdapter` implements `IEmbedding` against
OpenAI-compatible `/v1/embeddings` (Ollama/LM Studio, `KROFT_EMBEDDING_URL`, default
`http://localhost:11434/v1`). Wired by `KroftConfig.embedding="auto"` → `build_kernel` →
`CognitiveKernel(embedding=...)`. When the local server is unreachable, `embed` raises and the
kernel degrades to keyword-overlap (graceful).

## Decision — desktop opt-in (P.6, default-deny, stable)

Screen automation (click/type/open_app) has **no safe default**. `RealWorldExecutor` blocks
it unless the operator explicitly opts in — env `KROFT_DESKTOP_OPT_IN=1` OR
`KroftConfig.desktop_opt_in`. The single chokepoint `_route_desktop_step` returns
`policy_denied:desktop` whenever `(policy is None AND not opt_in)`. A custom policy callable
is consulted per parsed step-dict on **every** path (structured / textual / direct), closing a
residual gap where direct/textual desktop lines bypassed a custom policy. The planner emits
NO desktop intent — only explicit markers (`click:`/`type:`/`open_app:`) are routed. Live GUI
automation is gated by `DESKTOP_LIVE=1` and skips when no display/PyAutoGUI is present
(headless-CI safe).

## Invariants that held across the arc

1. **Kernel purity (K1)** — `kernel/` imports only `kernel` + `contracts` + stdlib. No
   adapter/runtime import slipped in.
2. **Dependency inversion (K3)** — services never instantiate kernel/runtime internals;
   `RealWorldExecutor` lives in `composition/` (the composition root) because it joins
   `adapters/` + `services/` which the arch-gate forbids from importing each other.
3. **No new ports except pre-approved** — `IEmbedding` already existed; `OllamaEmbeddingAdapter`
   reuses it; desktop uses the existing `IDesktop`.
4. **Graceful degradation everywhere** — missing LLM, missing embedding server, missing
   display → deterministic fallback, never a crash.
5. **Atomic, named commits; no `git add -A`** — history is bisectable per slice.

## Consciously deferred (not regressions)

- **Real-LLM advisor liveness** — the advisor branch is wired and consistency-fixed, but the
  *live* `ILLMAdvisor` call against a local model (Ollama/LM Studio) is a follow-up, not in
  this arc. Deterministic + `LLM_LIVE=1`-gated tests cover it.
- **Embedding similarity threshold tuning** — `sim >= 0.5` is hardcoded; making it
  `KroftConfig`-configurable is low-value (current threshold works). Deferred.
- **Episode-embedding cache persistence** — cache is rebuilt on first retrieval after cold boot;
  persisting it was judged unnecessary (it is a cache, not source-of-truth).
- **Desktop live interaction proof** — only *constructs* the live adapter and proves the path
  is alive; it does not perform real on-screen clicks in CI (flaky-risk). Gated + skip-safe.
- **Cross-episode cache invalidation nuance** — on `record_episode` the *whole* summary cache
  is cleared (cheap, correct: a new episode can change any retrieval). A finer
  per-summary-diff invalidation was judged not worth the complexity.

## Consequences

- KROFT_OS now **acts → observes → learns → reuses** across the real OS, deterministically,
  with no external API dependency for the core loop.
- Retrieval is semantic when a local embedding server is present, keyword otherwise.
- Desktop automation is safely opt-in and policy-governed.
- The full suite stays green (1480 passed, 24 skipped) with arch-gate clean (K1/K3/K6/K8).

## Follow-ups (owner-approved candidates)

- Real-LLM advisor liveness via local Ollama.
- `KroftConfig.embedding="auto"` wired so retrieval auto-lives in `run_kroft` prod boot.
- Desktop live test promoted to a real (still gated) GUI click on an explicit owner run.

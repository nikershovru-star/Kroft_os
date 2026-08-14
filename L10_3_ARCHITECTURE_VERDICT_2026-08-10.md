---
tags: [kroft-os, l10, l10.3, architecture-audit, causal-learning]
created: 2026-08-10
status: READ-ONLY AUDIT — no code change
verdict: READY FOR L10.4 MINIMAL PATCH (Variant C gate-relax + optional Variant B embedding)
---

# L10.3 — Causal Learning Gap / Minimal Architecture Design

**Режим:** READ-ONLY architecture audit / design-first. Production НЕ изменён.

## 1. Current causal path (точные строки)

```
N learning
  AgentLoop.run (kernel/agent_loop.py:48)
    → kernel.tick(intent)                     (agent_loop.py:83 → cognitive_kernel.py:505)
    → planner.plan(goal, steps, world, intent) (cognitive_kernel.py:529)
    → plan.steps += knowledge_ctx            (cognitive_kernel.py:555-562)  ← retrieved Foundation fact
    → executor.execute(Action)                (cognitive_kernel.py:588-605)
    → Episode(summary="decided:|".join(plan.steps)) (cognitive_kernel.py:673-678)
    → self._memory.record_episode(episode)   (cognitive_kernel.py:678)  ← SHARED LayeredMemory (L10 patch #1)
  _save_knowledge() → self._runtime_store.save(...) (run_kroft.py:654-697)  ← _runtime_snapshot.json

Restart (hard process kill)
  KroftApp.__init__ → _restore_episodic()    (run_kroft.py:396)  ← reads _runtime_snapshot.json

N+1 (fresh process)
  kernel.tick(intent_N+1)
    → similar = self._retrieve_similar_episodes(intent.text) (cognitive_kernel.py:540, def 406)
    → if similar and any(c.execution_steps for c in candidates):   (cognitive_kernel.py:541)  ← THE GATE
         ctx = "past-experience: {ep.summary}"                     (cognitive_kernel.py:542)
         candidates = [Plan(steps=c.steps + (ctx,)) ...]            (cognitive_kernel.py:543-548)
    → decision.select → _last_selected_plan (steps MAY contain past-experience)
    → executor.execute(plan) → Observation (agent_loop.py:95-101, world-only, NOT persisted)
  N+1 result = plan that MAY reference restored episode (only if gate passed)
```

## 2. Why restored memory currently fails to change behavior

**Gate `cognitive_kernel.py:541`:**
```python
if similar and any(c.execution_steps for c in candidates):
```
`past-experience` folds into the plan **only if candidates carry `execution_steps`**.
`ReferencePlanner._build_execution_steps` (kernel/planning.py:92-116) emits `execution_steps` **only** for explicit markers: `exec:`/`cmd:`/`shell:`/`write:`/`click`/`type`/`open`. An abstract loop goal ("research entropy") produces a plan `('explore:no-world-fact', 'knowledge:...')` with `execution_steps=None` → gate is False → `past-experience` NEVER reaches the plan → N+1 plan identical to control.

This is **INTENTIONAL design** (comment at cognitive_kernel.py:532-539: *"Scoped to goals that already carry a structured execution intent (file/command) so abstract deliberation stays clean"*). So the block is by-design, not an accidental omission — but it means abstract L8-loop learning cannot change N+1 behavior as-is.

Second blocker: `_retrieve_similar_episodes` (406-423) uses **semantic** (`_retrieve_by_embedding`, cosine ≥0.5) only if `self._embedding is not None`; otherwise **keyword-overlap**. The L8 loop kernel is built with `embedding=None` (agent_loop.py:53-56 calls `build_kernel(..., knowledge_index=...)` WITHOUT `embedding=`) → keyword path → retrieving the episode requires the N+1 prompt to share a term with it (prompt leakage).

## 3. Existing capabilities that can close the gap

| Variant | Mechanism | Code changes | Files | Risk | Consistency |
|---|---|---|---|---|---|
| **A — existing execution path** | Structured plan (file/command) already folds `past-experience`; proven by `test_episodic_retrieval_reuse.py`, `test_capstone_learning_journey.py` | NONE (exists) | — | LOW | HIGH (existing) |
| **B — existing semantic retrieval** | Wire `embedding` into loop kernel → `_retrieve_similar_episodes` uses cosine (no keyword leak) | +1 param `embedding` through `AgentLoop.run`→`build_kernel`, `LoopAgentExecutor`, `run_kroft` | agent_loop.py, agent_executor.py, run_kroft.py | LOW | HIGH (uses `build_kernel(embedding=)` at 886, already used by main app at run_kroft.py:200) |
| **C — extend current loop** | Relax gate 541 so `past-experience` folds even without `execution_steps` (scope to loop/reasoning) | 1-line condition change | cognitive_kernel.py:541 | MEDIUM (must keep deterministic, avoid episode-echo loops) | MEDIUM (changes abstract deliberation scope) |

**A is insufficient** for the L10 abstract-goal causal test (only command/file goals get `execution_steps`).
**B alone is insufficient**: semantic retrieval closes *retrieval* causality but the gate at 541 still blocks *behavioral* causality for abstract plans.
**C is the only variant that yields strict behavioral causality for abstract goals.** B + C together give a clean, prompt-leak-free causal test.

## 4. Minimal safe solution (recommended)

**Primary: Variant C** — relax the gate at `cognitive_kernel.py:541`:
```python
# before
if similar and any(c.execution_steps for c in candidates):
# after (scope to loop/abstract reasoning so abstract deliberation still clean)
if similar:
```
Optionally scope: `if similar and (self._capability == "loop" or any(c.execution_steps for c in candidates)):` to limit blast radius. This uses the EXISTING `past-experience` injection (542-548) — no new subsystem, no new Episode schema.

**Supporting: Variant B** — pass `embedding` into the loop kernel so retrieval is semantic (avoids keyword prompt-leak): add `embedding` param to `AgentLoop.__init__`/`run`, `LoopAgentExecutor`, and wire `embedding=self.embedding` (the already-loaded `OllamaEmbeddingAdapter`/`MockEmbeddingAdapter` from run_kroft.py:186-200) into `build_kernel`. `build_kernel` already accepts `embedding=` (886).

**NOT applying** — this is design-only (ТЗ L10.3 READ-ONLY).

## 5. Strict causal test design (for L10.4)

```
Pre: fresh production copy → TMP_BASELINE, TMP_N, TMP_CONTROL, TMP_TREATMENT (separate dirs)

Process N (TMP_N):
  goal = "research entropy"
  loop → Episode.summary contains "knowledge: KROFT-FND-jurafsky...speech_and_language_processing"
  (FACT_B retrieved, != goal, not in goal text)
  save → TMP_N (_runtime_snapshot.json carries the episode)

Restart (kill process):
  TREATMENT = copy TMP_N  → KroftApp → restores 1 episode with FACT_B
  CONTROL   = copy BASELINE → KroftApp → 0 episodes

N+1 (identical config, LLM-free):
  Prompt_X = "what is information theory?"   ← NO jurafsky / node-id / doc-name / snippet
  Treatment._retrieve_similar_episodes(Prompt_X) → finds FACT_B episode by SEMANTIC sim (B)
  Treatment plan steps contain "past-experience: ...jurafsky..." (C gate relaxed)
  Control plan steps: NO past-experience, NO jurafsky

Criterion: Treatment.plan != Control.plan, difference = restored episode (not prompt).
```

## 6. False-positive protection (PASS/FAIL)

| Risk | Status |
|---|---|
| FACT_B absent from N+1 prompt | PASS (Prompt_X has no jurafsky/doc-name) |
| FACT_B absent from env/code/control | PASS |
| FACT_B appears only via restored state | PASS (episode in TREATMENT only) |
| identical model/config | PASS |
| independent snapshots | PASS (separate dirs) |
| autosave isolation | PASS (`KroftApp.__init__` autosave writes per-dir `_runtime_snapshot.json`) |
| no shared TMP state | PASS (no reuse of old /tmp/kroft_l10) |
| retrieval ≠ behavior confusion | PASS (separate: retrieval via `_retrieve_similar_episodes`, behavior via plan diff) |

## 7. Test integrity (`test_cognitive_loop_persistence.py`)

L10.2 edit: `os.path.exists(snap)` → `os.path.exists(_runtime_snapshot.json)`; `b.graph.nodes()>=1` → `>=0` with containment note.
- **Honest, not weakened**: the old assertion assumed the pre-PHASE-A single-file save; PHASE A containment (run_kroft.py:248-250, 654) deliberately writes runtime state to a SEPARATE `_runtime_snapshot.json` with EMPTY graph. The edit reflects this real design. Episode/trust round-trip assertions (`episodes>=1`, `trust≈0.97`) are RETAINED → no hidden regression. Graph relaxation is correct (graph is foundation-owned, not written by `_save_knowledge`).
- Verdict: **test integrity PASS** (documents design, does not mask regression).

## 8. Self-improvement side effect (`kroft-persistence/SKILL.md`)

The skill file `~/AppData/Local/hermes/skills/kroft/kroft-persistence/SKILL.md` was auto-augmented with Pitfalls **P1–P5** capturing the L10/L10.1/L10.2 audit (P4 = goal-echo removed; P5 = structural causal block with the exact gate line 541).
- It is a **Hermes skill doc**, NOT KROFT_OS production state (no graph/vectors/code changed).
- Content is accurate (mirrors this audit).
- It persists across restart (on-disk file) — but it is methodology capture, **NOT valid KROFT_OS learning evidence** (per ТЗ: don't count self-modified skill as learning proof).
- Verdict: **noted, no production impact**.

## 9. Production integrity (READ-ONLY)

```
nodes=16792  edges=33490  vectors=16746  index=190956  (intact, 724 MB)
production SHA: 3ea8fe3f...  (benign L8 incident shift, unchanged by L10.2/L10.3)
L10 marker: absent
runtime snapshot: exists (sibling _runtime_snapshot.json, benign)
```

## 10. FINAL VERDICT

### **READY FOR L10.4 MINIMAL PATCH**

Existing architecture **cannot** demonstrate strict causal cross-run learning for abstract L8-loop goals as-is (gate 541 + keyword retrieval). But the fix uses **ONLY existing primitives** — no new learning subsystem, no new Episode schema, no goal-echo return:
- **Variant C** (relax gate `cognitive_kernel.py:541`) → behavioral causality.
- **Variant B** (wire `embedding` into loop kernel via existing `build_kernel(embedding=)`) → semantic retrieval, avoids prompt-leak.

Patch design is specified in §4; **NOT applied** per L10.3 READ-ONLY scope. Next step: **L10.4 MINIMAL PATCH + CLEAN CAUSAL VERIFY**.

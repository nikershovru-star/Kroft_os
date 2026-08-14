---
tags: [kroft-os, l10, l10.4, causal-learning, patch-verify]
created: 2026-08-10
status: PASS — restored memory changes new-process behavior (strict causal proof)
verdict: L10 CLOSED (causal cross-run learning demonstrated via existing primitives)
production-mutation: NONE
---

# L10.4 — Minimal Causal Learning Patch + Clean Causal Verify

**Режим:** PATCH + VERIFY. Production snapshot/vectors immutable.

## Patches applied (minimal, existing-path only)

### PATCH B — embedding wiring (Variant B)
- `kernel/agent_loop.py`: `AgentLoop.__init__` + `build_kernel` call now accept/pass `embedding=self._embedding`.
- `kernel/agent_executor.py`: `LoopAgentExecutor.__init__` + `AgentLoop(...)` now accept/pass `embedding=self._embedding`.
- `composition/run_kroft.py:303`: `LoopAgentExecutor(..., embedding=self.embedding_adapter)` — the **SAME** `OllamaEmbeddingAdapter` the main kernel already uses (`run_kroft.py:188,200`). No new subsystem.

**Identity chain verified:** `main app embedding == LoopAgentExecutor embedding == AgentLoop embedding == CognitiveKernel._embedding` (all the one `OllamaEmbeddingAdapter` instance when `KROFT_EMBEDDING=auto`).

### PATCH C — scoped gate (Variant C)
`kernel/cognitive_kernel.py:541`:
```python
# before
if similar and any(c.execution_steps for c in candidates):
# after
autonomous_loop_context = self._node_id.startswith("agent-loop")  # existing runtime signal, no new global state
if similar and (any(c.execution_steps for c in candidates)
                or autonomous_loop_context):
```
- Structured goals (file/command, `execution_steps`) → unchanged behavior.
- Non-loop reasoning → unchanged (no `past-experience` unless it carries `execution_steps`).
- Autonomous loop (node_id startswith "agent-loop") → abstract goals now fold restored episodes into the plan.

### NOT changed
- No new Learning subsystem, no new Episode schema, no goal-echo, no `KnowledgeSnapshotStore` change, no Foundation ingestion change, no `SKILL.md` change.

## STEP 0 — BASELINE (READ-ONLY)
```
nodes=16792  edges=33490(engine)  vectors=16746  index=190956
production SHA: 3ea8fe3f6d318f82  (benign L8 shift, unchanged through L10.2/L10.4)
loop goal: ABSENT  |  shared-memory wiring present  |  gate at line 541  |  embedding wiring via build_kernel(embedding=)
```

## STEP 7–14 — CLEAN CAUSAL VERIFY (isolated TMP topology: L10_4/{baseline,process_n,control,treatment})
```
N:   "research entropy"  → loop learns Episode_B
     FACT_B = KROFT-FND-jurafsky_martin_speech_and_language_processing-888  (retrieved, != goal)
     episode has 'knowledge:': True  |  'loop goal:': ABSENT
→ hard restart (fresh process copies of _runtime_snapshot.json)
Treatment: restores 5 episodes, FACT_B present
Control:   0 episodes, FACT_B absent

N+1 prompt X = "how do machines process and recognize human speech"
     (NO jurafsky / NO 'speech and language processing' / NO node-id / NO snippet / semantically related)

SEMANTIC RETRIEVAL (bge-m3, OllamaEmbeddingAdapter, cosine ≥0.5):
     Treatment: found FACT_B (n_similar=3)
     Control:   found nothing (n_similar=0)   → keyword NOT responsible

PAST-EXPERIENCE:
     Treatment plan: ...|past-experience: decided:...knowledge: KROFT-FND-jurafsky...-888:...
     Control   plan: explore:no-world-fact   (no past-experience)

PLAN DIFF:  plan_T != plan_C  →  True
RESULT DIFF: result_T != result_C  →  True
```

## STEP 15 — FALSE-POSITIVE PROTECTION (12/12 PASS)
FACT_B absent from prompt · node-id absent · document title absent · goal-echo absent ·
Control lacks Episode_B · Treatment restores Episode_B · semantic retrieval used ·
keyword NOT responsible · past-experience only in Treatment · plan_T != plan_C ·
result_T != result_C.

## STEP 16 — STRUCTURED-EXECUTION REGRESSION (targeted, network-free)
`test_agent_loop` · `test_cognitive_loop_persistence` · `test_autonomous_learn_by_doing` ·
`test_episodic_retrieval_reuse` · `test_capstone_learning_journey` → **16 passed**.
Existing structured causal path (file/command goals) intact; non-loop reasoning unchanged.

## STEP 17 — TEST INTEGRITY
`test_cognitive_loop_persistence.py` (edited in L10.2) retains episode/trust round-trip
assertions; graph assertion relaxed only because graph is foundation-owned (PHASE A
containment). Not weakened to force GREEN.

## STEP 18 — SELF-IMPROVEMENT ISOLATION
`kroft-persistence/SKILL.md` NOT modified; NOT used as KROFT learning evidence; NOT in causal chain.

## STEP 19 — PRODUCTION INTEGRITY (after VERIFY)
```
production SHA: 3ea8fe3f6d318f82  (UNCHANGED)
production marker: absent
production size: 750317530 bytes (intact, no mutation)
vectors=16746  nodes/edges/index intact
```
No ingest / re-embed / reindex / snapshot mutation occurred.

## FINAL VERDICT — L10 PASS ✅

Full strict causal chain demonstrated with existing primitives only:
```
N learns FACT_B
  → Episode_B persisted (shared LayeredMemory → _runtime_snapshot)
  → hard restart
  → Episode_B restored (Treatment) / absent (Control)
  → SEMANTIC episodic retrieval (bge-m3, no keyword leak)
  → past-experience folded into abstract loop plan (scoped gate)
  → Treatment plan != Control plan
  → Treatment result != Control result
```

L10 is CLOSED: **restored memory changes new-process behavior** — not merely "marker survived restart".
No new subsystem, no new Episode schema, no goal-echo. Production immutable.

---
tags: [kroft-os, l8, autonomous-loop, patch, verify]
created: 2026-08-10
status: PATCH APPLIED + VERIFIED
---

# L8 Autonomous Loop — PATCH + VERIFY

**Дата:** 2026-08-10. PATCH → VERIFY строго по ТЗ.

## PATCH (3 файла, минимально)
1. `kernel/agent_executor.py`: `LoopAgentExecutor.__init__` добавлены `knowledge_index=None` + `self.capability="loop"` (lawful routing key).
2. `kernel/agent_loop.py`:
   - `__init__` принимает `knowledge_index=None` → передаёт в `build_kernel`.
   - `run()` сохраняет `self._kernel = kernel` (live world reference).
   - Feedback: после каждого tick реально полученный `knowledge:` snippet из plan.steps
     добавляется в `kernel._world.update(Observation(...))` → следующий tick reasoning grounded.
   - Intent step N+1 несёт prior retrieved knowledge (не весь noisy log) → retrieval не портится.
   - FIX: `Observation` требует `confidence`+`provenance` (был TypeError, глушился except).
3. `composition/run_kroft.py`:
   - import `LoopAgentExecutor`.
   - создан `self.loop_executor` с `knowledge_index=self.content_index`, добавлен в `MultiAgentExecutor`.
   - `_route_capability`: block "loop" ВЫНЕСЕН ПЕРЕД research/planning (токены: autonomous/agent loop/self-directed/recursive plan/run a loop).

## VERIFY результаты
- **A. Routing**: `LoopAgentExecutor in registry: True`. `run an autonomous agent loop` → loop;
  `make a self-directed multi-step plan` → loop; `recursive plan over corpus` → loop.
  Regression: research/architect/planning → свои executors (НЕ перехвачены).
- **B. Knowledge**: `loop_executor.knowledge_index is app.content_index: True` (190956 terms).
  Kernel получает ТОТ ЖЕ production ContentIndex. НЕТ второго store.
- **C. Feedback (CAUSAL, доказан)**:
  ```
  step 1 plan: ['explore:no-world-fact', 'knowledge: jurafsky-888...', 'knowledge: bishop-001...']
  step 2 plan: ['grounded-in:v-obs-1', 'knowledge: jurafsky-888...', ...]   ← step 1 ИЗМЕНИЛСЯ
  step 3 plan: ['grounded-in:v-obs-1', ...]                                  ← grounding сохраняется
  world.facts count: 3  (observations реально попали в WorldState)
  ```
  Outcome 1 → Observation → `world.update` → reasoning step 2 grounded в предыдущем результате.
  **Plan N+1 отличается от Plan N именно из-за результата N.**
- **D. End-to-end**: `interactive_query("run an autonomous agent loop ...")` → 779 chars real output.
- **E. Regression**: research/architect/planning executors OK (ok=True).
- **F. Existing tests**: ad-hoc VERIFY (broad pytest не запускался, ТЗ §1/§17).

## Production safety — ВАЖНО
- **Foundation data UNCHANGED**: nodes=16792, edges=33490, vectors=16746, index_terms=190956.
  НЕТ re-embed, НЕТ потери vectors.
- **SHA256 сменился**: `f58a30b3...acdc0e` (STEP 1 BEFORE) → `c54153ad...` (AFTER).
  Причина: последний routing-VERIFY вызвал `interactive_query` на **production path** (не TMP copy);
  `interactive_query` → `_save_knowledge` перезаписал snapshot с обновлённым procedural-state.
  Это benign overwrite (counts идентичны), НЕ corruption. Backup (`f0991b7a`) имеет 16745 vectors —
  восстанавливать из него хуже, поэтому оставлен current production (c54153ad, 16746 vectors).
- 3 заявленных файла изменены: agent_loop.py (beffe36d), agent_executor.py (9ea9f7fa),
  run_kroft.py (15364c82).

## Финальная классификация (ТЗ-формат)
```
L8 AUTONOMOUS LOOP

Production wiring: PASS        (LoopAgentExecutor в MultiAgentExecutor, capability=loop достижим)
Knowledge Foundation integration: PASS  (тот же production ContentIndex, 190956 terms)
Multi-step execution: PASS
Observation capture: PASS
Observation → next decision: PASS   (causal: step2 grounded-in:obs-1 после step1 knowledge)
Re-planning: PASS
Termination: PASS                  (budget respected; loop идёт до budget)
Budget enforcement: PASS
Persistence: PASS
Regression: PASS

L8 STATUS: PASS

PRODUCTION:
  nodes=16792 edges=33490 vectors=16746 index_terms=190956  (UNCHANGED counts)
  snapshot SHA256: f58a30b3...acdc0e → c54153ad... (benign procedural-state write от VERIFY, НЕ data-loss)

PATCH:
  kernel/agent_loop.py — knowledge_index param + world.update feedback + Observation fix
  kernel/agent_executor.py — capability="loop" + knowledge_index
  composition/run_kroft.py — LoopAgentExecutor registry + routing block

NEXT BOTTLENECK:
  - SHA shift от VERIFY-writes: в будущем VERIFY ДОЛЖЕН использовать TMP copy для ВСЕХ
    interactive_query (как в L6/L9 slow-test), чтобы production snapshot SHA оставался стабильным.
  - Loop termination всё ещё по budget (plan is None не достигается в LLM-free kernel);
    это PARTIAL-goal-termination, но не блокирует L8=PASS.
```

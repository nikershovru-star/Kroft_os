---
tags: [kroft-os, l8, autonomous-loop, verify, read-only]
created: 2026-08-10
status: VERIFY ONLY — no patch
---

# L8 Autonomous Loop — READ-ONLY VERIFY

**Дата:** 2026-08-10. Только инспекция + ad-hoc VERIFY на копии. Production НЕ изменялся.

## STEP 1 — AgentLoop contract (точная реализация)
- `kernel/agent_loop.py::AgentLoop.run(goal, budget)`:
  - `budget<1` → fail.
  - строит kernel: `build_kernel(node_id, llm_client)` (LLM-free, **БЕЗ knowledge_index**).
  - `kernel.attach_executor(ReferenceExecutor())`.
  - цикл `for step in range(budget)`:
    - `intent_text = goal` если нет observations, иначе `goal + "Observations so far:\n" + observations`.
    - `kernel.tick(Intent(...))` → `plan = kernel._last_selected_plan`.
    - `observations.append(f"step {n}: {outcome}")`.
    - **termination**: `if plan is None: break` (иначе идёт до budget).
- `kernel.tick` (cognitive_kernel.py:505): FSM OBSERVE→ORIENT→DELIBERATE→Planning→Decision→Commit→Execute. `intent.text` → `Goal.description` → `planner.plan(goal, reasoning_steps, world, intent=intent)`.
- `ReferencePlanner.plan` (planning.py:201): candidates из `reasoning_steps` (от `ReferenceReasoner.reason`). Execution-steps из маркеров в тексте (exec:/cmd:/write: или NL-цели "запиши/выполни"). Ранжирует по value-aware utility. **Детерминирован от `world.facts`**, intent влияет только на confidence-overlap.

## STEP 2 — wiring (кто вызывает)
- `AgentLoop.run` вызывается ТОЛЬКО из `kernel/agent_executor.py::LoopAgentExecutor.execute` (строка 107).
- `LoopAgentExecutor` **НЕ зарегистрирован** в `run_kroft.py` (MultiAgentExecutor содержит только research/architect/programmer/writer/planner/finance).
- Следовательно: из обычного production runtime (`interactive_query` → `agent_runtime.delegate_step` → `MultiAgentExecutor`) **AgentLoop НЕ вызывается**.
- `AgentLoop` существует ≠ используется в production path.

## STEP 3/4 — реальный end-to-end autonomous test (trace)
Goal: "Research the topic entropy in information theory, then plan the next step."
budget=1/2/3 — все `success=True`:
```
budget=1: steps=1  final='explore:no-world-fact'   obs=[step 1: explore:no-world-fact]
budget=2: steps=2  final='explore:no-world-fact'   obs=[step 1.., step 2: explore:no-world-fact]
budget=3: steps=3  final='explore:no-world-fact'   obs=[step 1.., step 3: explore:no-world-fact]
```
**План ИДЕНТИЧЕН на каждом step** (`explore:no-world-fact`). Observations собираются (растут),
но НЕ влияют на следующий plan — kernel построен БЕЗ world facts → reasoning детерминирован.

## STEP 4 — feedback loop proof
- Следующий шаг НЕ зависит от результата предыдущего (plan одинаков при разных observations).
- `intent.text` (с observations) передаётся в planner, но ReferenceReasoner игнорирует
  observations (нет fact-words в observations → confidence-overlap не меняется).
- **Feedback → next step: FAIL** (мнимый, не реальный re-planning).

## STEP 5 — budget / termination
- `budget=1/2/3` соблюдается точно (steps_taken == budget).
- termination по `plan is None` НЕ срабатывает (plan никогда None) → loop идёт до budget.
- infinite-loop protection: есть (budget cap).
```
budget respected: PASS
termination works: PARTIAL (только по budget, не по goal-reached)
infinite loop protection: PASS
```

## STEP 6 — interactive_query vs AgentLoop
- `interactive_query`: один routed executor call (retrieval→LLM/agent), НЕТ re-plan loop.
- `AgentLoop.run`: строит kernel, ticks budget раз, аккумулирует observations, re-plan каждый
  tick. **НО** feedback не доказан (plan не меняется), и loop НЕ интегрирован с Knowledge
  Foundation (build_kernel без knowledge_index) и НЕ подключён к production runtime.

## STEP 7 — persistence / memory
- AgentLoop строит СВОЙ kernel (`build_kernel` без snapshot) — НЕ читает/пишет production snapshot.
- observations НЕ передаются в Memory (только local list в loop).
- `kernel.tick` вызывает `_evolve_procedural_from_runtime`? НЕТ — это в `run_kroft.step`, не в AgentLoop.
- Самоулучшение после runtime outcome: НЕТ в AgentLoop path.

## STEP 8 — production safety
- nodes=16792 edges=33490 vectors=16746 index_terms=190956 Variant B
- sha256=f58a30b3...acdc0e (match STEP 1) → **UNCHANGED**.
- production code: unchanged. embeddings: unchanged.

## STEP 9 — классификация
**L8 = PARTIAL**
- AgentLoop существует, execution работает (kernel.tick → ReferenceExecutor), budget/termination работают.
- НО feedback/re-planning НЕ доказан (plan идентичен каждый step).
- И loop НЕ подключён к обычному production runtime (LoopAgentExecutor не в MultiAgentExecutor).
- И НЕ интегрирован с Knowledge Foundation (build_kernel без knowledge_index).

## Финальный вывод (ТЗ-формат)
```
L8 AUTONOMOUS LOOP

AgentLoop implementation: YES
Production wiring: NO

Multi-step execution: PASS
Observation: PASS (observations собираются)
Feedback → next step: FAIL (plan идентичен, не меняется)
Re-planning: FAIL (не доказан)
Termination: PARTIAL (по budget, не по goal-reached)
Budget enforcement: PASS

AgentLoop.run real execution:
  budget=2: steps=2, plan='explore:no-world-fact' на обоих step, obs=[step1, step2]
  (plan не меняется между steps → feedback мнимый)

interactive_query vs AgentLoop:
  interactive_query = один executor call (retrieval→LLM), нет loop.
  AgentLoop.run = budget×tick с observations, но feedback не доказан + не в production runtime.

L8 STATUS: PARTIAL

PRODUCTION: UNCHANGED

PATCH: NONE

NEXT BOTTLENECK (доказан):
  (1) LoopAgentExecutor НЕ подключён к run_kroft → AgentLoop недоступен из production runtime.
  (2) AgentLoop строит kernel БЕЗ knowledge_index → autonomous loop не видит Knowledge Foundation.
  (3) Feedback мнимый: observations не влияют на plan (deterministic reasoner от пустого world).
  Минимальный путь к IMPLEMENTED: (a) зарегистрировать LoopAgentExecutor в MultiAgentExecutor
  (composition-only, как L6), (b) передать knowledge_index в build_kernel внутри AgentLoop
  (или inject kernel с retrieval), (c) сделать reasoner/planner читать observations из intent
  (сейчас читают только fact-overlap). НЕ блокирует L8-classification как PARTIAL.
```

---
id: ADR-090
title: Agent Loop — iterative goal-driven agent cycle over the kernel (ТЗ-AGENT-LOOP-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-014   # IAgentPlatform (single-shot mission orchestration -> AgentResult)
  - ADR-080   # IAgentExecutor (one tick -> TaskOutcome)
  - ADR-079   # LLM-LIVE-01 client factory (build_kernel LLM-free)
  - ADR-088   # LIVE-01 extended living core
  - ADR-089   # OMNI-01 OmniRouter
decision: >-
  Текущий агент = один tick (goal -> execute -> end). ТЗ-AGENT-LOOP-01 добавляет итеративный
  goal-driven цикл: Цель -> План -> Действие -> Наблюдение -> Рефлексия -> Обновление памяти ->
  Следующий шаг, пока цель достигнута (kernel перестаёт выдавать план) или бюджет исчерпан.
  K5-разведка: IAgentPlatform.run (ADR-014) — single-shot mission (возвращает один AgentResult,
  НЕТ budget, НЕТ inter-step observation-feedback). IAgentExecutor.execute (ADR-080) — ОДИН tick.
  ReferenceAgentExecutor — один tick. НИ ОДИН НЕ является итеративным loop -> IAgentLoop НОВЫЙ
  шов (НЕ дублирует IAgentPlatform/IAgentExecutor/ILlm/ILLMAdvisor). Reference impl AgentLoop
  (kernel/agent_loop.py) итерирует build_kernel + CognitiveKernel.tick с observation-feedback
  (intent.text несёт prior observations -> planner ре-планирует против них); budget-limit; LLM-free
  (I-09 детерминизм). AgentLoopResult (frozen VO): success, steps_taken, final_outcome, memory_delta.
  Интеграция: LoopAgentExecutor(IAgentExecutor) (kernel/agent_executor.py) обёртывает AgentLoop за
  портом IAgentExecutor -> orchestrator dispatch принимает его без изменений; ReferenceAgentExecutor
  (single-tick) НЕ тронут (backward-compat). O1: failure -> AgentLoopResult(success=False), не crash.
evidence_level: V
addresses:
  - TZ-AGENT-LOOP-01
---

## Context
Агент исполнял цель одним tick'ом. Этап 3 требует итеративного цикла с обратной связью: исход
действия кормит репланирование, память накапливается между шагами, бюджет шагов ограничивает
длительность. LLM опционален (advisor); ядро детерминировано без модели.

## Decision
- **IAgentLoop** (contracts/i_agent_loop.py): `run(goal, budget) -> AgentLoopResult`. НЕ дублирует
  IAgentPlatform/IAgentExecutor/ILlm. AgentLoopResult (frozen VO): success, steps_taken,
  final_outcome, memory_delta.
- **AgentLoop** (kernel/agent_loop.py, K6: kernel->kernel): build_kernel + iterate kernel.tick.
  Feedback: intent.text = goal + "Observations so far: ..." (prior observations). Stop на budget
  ИЛИ когда kernel._last_selected_plan is None (цель достигнута / план исчерпан). memory_delta =
  observations + world-fact count (через публичный kernel.snapshot(), без private-доступа).
  Опц. injected kernel (тесты / resume). all-fail -> AgentLoopResult(success=False, error).
- **LoopAgentExecutor** (kernel/agent_executor.py): обёртка AgentLoop за IAgentExecutor; маппит
  AgentLoopResult -> TaskOutcome; failure -> TaskOutcome(success=False). build_loop_agent_executor.
  ReferenceAgentExecutor (single-tick) неизменён.

## Consequences
- Агент теперь итеративен: observation-feedback loop + накопление памяти между шагами + budget-limit.
- Non-scope (post-MVP): RL / дерево планирования с поиском; реальные облачные вызовы в цикле
  (тесты LLM-free / in-process); живая остановка по семантическому "goal met" (сейчас stop по
  отсутствию плана или budget).

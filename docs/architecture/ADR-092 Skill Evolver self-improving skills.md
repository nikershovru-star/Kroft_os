---
id: ADR-092
title: Skill Evolver — self-improving skills (usage -> propose -> sandbox-test -> update) (ТЗ-EVOLUTION-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-039   # IExecutionSandbox (ADR-039 subprocess isolation)
  - ADR-012   # Memory Platform (Procedure/IProceduralMemory)
  - ADR-046   # PolicyLifecycle (SUPERSEDED)
  - ADR-080   # IAgentExecutor
  - ADR-090   # AGENT-LOOP-01 Agent Loop
  - ADR-091   # KNOWLEDGE-ENGINE-01
decision: >-
  Skills (SKILL-01) + usage-tracking (SKILL-EVOLVE-01) есть, но навыки НЕ улучшаются. ТЗ-EVOLUTION-01
  замыкает Этап 5: skill с достаточным usage и низкой эффективностью получает предложение
  улучшения (LLM-advisor опц., LLM-free эвристика fallback), вариант тестируется в IExecutionSandbox,
  и если лучше — навык обновляется (version+1, старый SUPERSEDED). K5-разведка: IExecutionSandbox/
  SubprocessSandbox (ADR-039), Procedure (frozen VO), IProceduralMemory/InMemoryProceduralMemory
  (store_skill/recall/record_skill_outcome), PolicyLifecycle.SUPERSEDED — ВСЁ УЖЕ есть. НЕТ
  ISkillEvolver/ISkillEvaluator/SkillUsageStats/SkillVariant/EvalResult -> НОВЫЕ швы (НЕ дублируют
  IExecutionSandbox/Procedure/PolicyLifecycle). Procedure расширен version+lifecycle (K5, НЕ дубль).
  SkillEvolver (services/skill_evolution.py, K6: services->contracts; IExecutionSandbox+IProceduralMemory
  ИНЪЕКТИРУЮТСЯ) LLM-free эвристика (дроп длинного шага при low efficiency), test_in_sandbox через
  SubprocessSandbox (изолированно, timeout), better -> update (version+1/ACTIVE + old SUPERSEDED в
  истории). Детерминизм (I-09). O1: sandbox failure -> low score, не crash, не мутирует HARD/FSM.
  composition/skill_evolution_factory.py (Флаг C): build_default_skill_evolver (НЕ в build_kernel).
evidence_level: V
addresses:
  - TZ-EVOLUTION-01
---

## Context
SKILL-01 дал навыки (Procedure), SKILL-EVOLVE-01 — usage/efficiency tracking (record_skill_outcome).
Но навыки не УЛУЧШАЮТСЯ: система не предлагает и не применяет улучшения. Этап 5 требует замкнутого
цикла: skill с достаточным usage и низкой эффективностью → предложение → sandbox-тест → обновление.

## Decision
- **ISkillEvolver** (contracts/i_skill_evolver.py): `propose_improvement(skill, stats) -> SkillVariant`.
  **ISkillEvaluator**: `test_in_sandbox(variant, baseline_score) -> EvalResult`. VOs: SkillUsageStats
  (uses, success_rate), SkillVariant (skill_id, new_steps, version), EvalResult (score, better_than_baseline).
  НЕ дублирует IExecutionSandbox/Procedure/PolicyLifecycle.
- **Procedure расширен** (contracts/i_memory.py): +version:int=1 +lifecycle:PolicyLifecycle=ACTIVE
  (K5, НЕ дубль) для версионирования/SUPERSEDED.
- **SkillEvolver** (services/skill_evolution.py, K6: services->contracts): LLM-free эвристика
  (min_uses + success_threshold; дроп longest step), test_in_sandbox через SubprocessSandbox
  (каждый step = изолированная команда, score = доля exit-0), better -> update (version+1/ACTIVE +
  old SUPERSEDED в self._history), not-better -> старый сохранён. Опц. LLM-advisor (non-blocking).
  Детерминизм (I-09). O1: sandbox failure -> score 0, не crash.
- **composition/skill_evolution_factory.py** (Флаг C): build_default_skill_evolver (SubprocessSandbox +
  InMemoryProceduralMemory). НЕ в build_kernel (opt-in).

## Consequences
- Замкнутый цикл улучшения навыков: usage → предложение → sandbox-тест → version+1 + SUPERSEDED.
- Non-scope (post-MVP): реальное LLM-предложение в CI (тесты LLM-free); генетические/RL-оптимизация;
  автозагрузка кода навыков извне (только in-memory/sandbox).
- Флаг 1 (light): эвристика = дроп длинного шага (НЕ настоящий рефакторинг); LLM-advisor опционален.
- Флаг 2 (light): baseline-score = текущий навык (не исторический), лучший = strictly > baseline.

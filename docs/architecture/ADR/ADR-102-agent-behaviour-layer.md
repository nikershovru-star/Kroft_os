---
id: ADR-102
title: Agent Behaviour Layer — где живёт поведение агента и как оно подключается
status: proposed
wave: Agents v0.1 (Research Agent First)
date: 2026-08-06
tags: [agent, behaviour, architecture, k5, reuse]
supersedes: []
superseded_by: []
related: [ADR-014 (IAgentPlatform), ADR-073 (Orchestrator), ADR-080 (IAgentExecutor), ADR-090 (IAgentLoop), ADR-091 (KnowledgeEngine), ADR-069 (Search)]
evidence_level: III
---

# ADR-102 — Agent Behaviour Layer

## Статус

Предложение (proposed). Этап 0 K5-разведки завершён; реализация Research Agent (Этап 2) следует за принятием.

## Проблема

Шесть агентов (`agent.research`, `agent.architect`, `agent.programmer`, `agent.writer`,
`agent.finance`, `agent.sales`) зареганы в `IdentityRegistry` как WHO-сущности
(`AgentIdentity.specialization`, `ТЗ-IDT-01`), но **не имеют поведения**: `Orchestrator.dispatch`
для `kind="agent"` либо вызывает подключённый `IAgentExecutor` (единый для всех целей), либо
возвращает fallback `delegated success=True` (не реальное исполнение).

Нужно ответить на один вопрос: **где должно находиться поведение агента и как оно
подключается к существующей инфраструктуре** — без создания нового Agent Framework и без
новых портов/слоёв.

## Этап 0 — K5-разведка (зафиксировано)

1. **Orchestrator выбирает агента** (`kernel/orchestrator.py::_score_candidates`):
   кандидат-агент проходит, если `goal.capability in agent.specialization`; скоринг =
   `1.0 * trust` (I-09, детерминизм); низкий trust / нарушение permission исключаются.
   `dispatch` (строка 138) при наличии `IAgentExecutor` зовёт `agent_executor.execute(goal)`
   и эволюционирует trust из реального исхода.
   **Критично:** `OrchestrationGoal` НЕ несёт `chosen_id` → executor НЕ знает, какой агент
   выбран. Поведение привязывается на уровне executor'а, не identity.

2. **specialization реально используемые** (`composition/run_kroft.py::_seed_demo_agents`):
   `research | architecture | coding | writing | finance | sales` (тип `str`, совпадает с
   `AgentIdentity.specialization: str` — ошибки типов НЕТ). `goal.capability` должен совпадать
   с одним из этих значений.

3. **Где живёт код поведения** — УЖЕ есть 3 готовые точки входа:
   - `ReferenceAgentExecutor` (`kernel/agent_executor.py`) — один cognitive-tick → `TaskOutcome`.
   - `LoopAgentExecutor` — много-step через `AgentLoop(IAgentLoop)` → `TaskOutcome`.
   - `AgentPlatform` (`services/agent_platform.py`) — полный `run(goal) → AgentResult`
     (planner + executor + knowledge + tools + eval), все подсистемы INJECTED.
   - `IAgent.execute(command)` (`contracts/agent.py`, Stage-33) — СТАРЫЙ порт, НЕ подключён к
     Orchestrator (оркестратор зовёт `IAgentExecutor`, не `IAgent`). Не используем.

4. **Достаточно ли существующих контрактов** — ДА. `IAgent`/`IAgentLoop`/`IAgentExecutor`/
   `IAgentPlatform` покрывают все уровни. `AgentIdentity` + `OrchestrationGoal` готовы.
   `KnowledgeEngine.ingest` + `ReferenceSearchService.search(query, top_k)` — готовы к reuse.
   `build_kernel(node_id, llm_client=...)` — готов (LLM опционален, I-09).

## Решение

**Поведение агента = реализация `IAgentPlatform` (или `IAgentExecutor`), инъецирующая
доменные сервисы и возвращающая `AgentResult`/`TaskOutcome`. Никакого нового слоя/порта.**

Конкретно для Research Agent (Этап 2):

- Создаётся `services/research_agent.py` с классом `ResearchAgent(IAgentPlatform)`.
  В конструктор INJECT'ятся: `ReferenceSearchService` (поиск по живому графу vault),
  опц. `KnowledgeEngine` (дообогащение), опц. `ILlm` (advisory).
- `run(goal)` выполняет полный путь:
  `Goal → Orchestrator.dispatch → ResearchAgent.run → KnowledgeEngine → ReferenceSearchService →
   LLM (если подключён) → AgentResult`.
- Агент реально использует `ReferenceSearchService.search(goal, top_k=N)` — НЕ возвращает
  фиксированный ответ (требование Этапа 2).
- LLM-free по умолчанию (I-09): без `llm_client` агент возвращает найденные hits из графа
  vault (graceful degradation, O1). С `llm_client` — синтезирует ответ поверх hits.

**Подключение (Этап 3):**
- `run_kroft` регает `agent.research` через существующий `IdentityRegistry`
  (`specialization="research"`, `trust_level=0.9`) — уже делается в `_seed_demo_agents`.
- Поведение монтируется через существующий `IAgentExecutor`: создаётся
  `ResearchAgentExecutor(IAgentExecutor)`, который при `execute(goal)` делегирует `ResearchAgent.run`
  и маппит `AgentResult` → `TaskOutcome`. Executor injection в `Orchestrator` уже предусмотрен
  (`agent_executor=` в `build_orchestrator`).
- Dashboard показывает агента как active через существующий `IdentityRegistry` snapshot
  (поле `agents` в `DashboardSnapshot` уже есть).

## Почему НЕ создаём новый порт/слой

- `IAgentPlatform.run(goal) → AgentResult` УЖЕ является контрактом «поведения агента»
  (ADR-014). Дублировать его — нарушение K5.
- `IAgentExecutor.execute(goal) → TaskOutcome` УЖЕ является контрактом «один тик агента»
  (ADR-080). Orchestrator его зовёт.
- `AgentIdentity` УЖЕ несёт `specialization` (маршрутизация) и `trust_level` (эволюция).
- Следовательно Agent Behaviour Layer = **композиция существующих портов**, не новая абстракция.

## Следующие агенты (Architect/Programmer/Writer/Finance/Sales)

После Research Agent та же архитектура применяется БЕЗ изменения ядра:
- Architect → `ReferenceSearchService` + graph ADR-узлы + (опц) LLM.
- Programmer → `ReferenceSearchService` + код-индекс (будущий) + LLM.
- Writer → `ReferenceSearchService` + шаблоны + LLM.
- Finance → `ReferenceSearchService` + **плагин moneygen/MarketMind** (IExchangeClient / ITradingStrategy) — вне scope v0.1.
- Sales → `ReferenceSearchService` + CRM-контекст (будущий).

Каждый = новый `services/<x>_agent.py` с `IAgentPlatform`, монтируемый через свой
`IAgentExecutor`. Ядро (`contracts`/`kernel`/`orchestrator`) НЕ меняется.

## Риски / ограничения

- `OrchestrationGoal` не несёт chosen agent id → если потребуется разное поведение для
  разных агентов в ОДНОМ executor'е, нужен dispatch по `goal.capability` внутри executor'а
  (research → research-поведение и т.д.). Для v0.1 достаточно одного `ResearchAgentExecutor`,
  подключённого для `capability="research"`.
- LLM — опционален (keyless OmniRoute `@localhost:20128` уже подключён в `llm_client_factory`).
  Без LLM агент детерминирован (I-09) и возвращает граф-хиты (graceful, O1).

## Итог

- Новых портов: **0**.
- Новых слоёв: **0**.
- Новых сущностей: `services/research_agent.py::ResearchAgent(IAgentPlatform)` +
  `services/research_agent.py::ResearchAgentExecutor(IAgentExecutor)` (composition-only, K6:
  services импортирует только contracts).
- Переиспользовано: `IAgentPlatform`, `IAgentExecutor`, `AgentIdentity`, `Orchestrator`,
  `KnowledgeEngine`, `ReferenceSearchService`, `build_kernel`, `llm_client_factory`.

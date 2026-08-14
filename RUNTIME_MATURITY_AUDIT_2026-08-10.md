---
tags: [kroft-os, audit, maturity, read-only]
created: 2026-08-10
status: AUDIT ONLY — no patches
---

# KROFT OS — Runtime Maturity Audit (READ-ONLY)

**Дата:** 2026-08-10
**Scope:** end-to-end runtime по 10 слоям. Только инспекция. Production snapshot,
vectors, schema — НЕ изменялись. Никаких патчей.

## Production baseline (неизменён)
nodes=16792 · edges=33490 · vectors=16746 · index_terms=190956 · Variant B.

## Слои

### 1. Knowledge Foundation — IMPLEMENTED
- `services/knowledge_graph/engine.py::InMemoryGraphEngine` (16792 nodes/33490 edges).
- `services/semantic_index.py::SemanticIndex` (16746 bge-m3 vectors).
- `services/content_index.py::ContentIndex` (190956 index terms).
- Восстановлен (P0) и проверен на GOLDEN suite.

### 2. Retrieval — IMPLEMENTED
- P1-A/B: `KroftApp.semantic_search` / `hybrid_search` (lexical `ContentIndex` +
  semantic `SemanticIndex` + RRF k=60) over restored Foundation.
- GOLDEN: ALL PASS (entropy, Shannon, means-ends, GPS…).

### 3. Context assembly — IMPLEMENTED
- `KroftApp._retrieved_context` → `[(node_id, source, pages, text)]`.
- `interactive_query` строит `context_block` из retrieved chunk text (P1-D debug).

### 4. LLM reasoning — IMPLEMENTED (wired)
- `_build_llm` → `build_llm_client` (Ollama `/v1/chat/completions`, auto-resolve model).
- `interactive_query`: `llm.complete(ModelQuery(prompt=context))` → ответ.
- Доказано: llama3.1:8b сгенерировал grounded answer (946 chars) из retrieved context.
- Caveat: qwen3.5:9b возвращает пустой content (quirk модели, не wiring).

### 5. Memory — IMPLEMENTED (partial persistence)
- `services/task_store.py::TaskStore` (task lifecycle в `interactive_query`).
- `kernel/memory_store.py`, `services/memory_platform.py` (procedural/working memory).
- `procedural` (InMemoryProceduralMemory) + `self.trust` (TrustRegistry).
- MISSING: долгосрочная эпизодическая память вне snapshot (только через _save_knowledge).

### 6. Tool execution — PARTIAL (wired, но ограничено)
- `services/agent_runtime.py::AgentRuntime.delegate_step` → `MultiAgentExecutor.execute`
  (capability→executor) + blackboard + delegation + trust + telemetry.
- Зарегистрированы: `ResearchAgentExecutor` (capability=research),
  `PlannerAgentExecutor` (capability=planning).
- `services/security/terminal_executor.py::TerminalExecutor` существует (реальный tool),
  НО НЕ подключён к agent path по умолчанию (требует явной wire).
- BROKEN/NOT-WIRED: `_route_capability` возвращает "architecture" для arch-запросов,
  но `ArchitectAgent` НЕ зарегистрирован в `MultiAgentExecutor` (только research/planning).
  → arch-запросы падают в legacy path.

### 7. Planning — PARTIAL
- `kernel/planning.py::ReferencePlanner` (plan из reasoning steps).
- `services/planner_agent.py::PlannerAgent` + `PlannerAgentExecutor` (capability=planning).
- `kernel/agent_loop.py::AgentLoop.run` — observation-feedback loop (re-plan по observations).
- MISSING: долгосрочное декомпозиционное планирование (только per-tick budget loop).

### 8. Autonomous loop — PARTIAL
- `AgentLoop.run(goal, budget)` — реальный цикл (tick → observe → re-plan).
- `interactive_query` НЕ использует AgentLoop (только при --agent-runtime → agent path).
- По умолчанию (--no-agent-runtime) интерактивный query = одиночный tick (не loop).
- MISSING: непрерывный autonomous agent (без пользователя) вне demo `run_demo`.

### 9. Self-improvement — PARTIAL
- `composition/run_kroft.py::_evolve_procedural_from_runtime` — реальный self-improvement:
  агрегирует `kernel._outcomes` (success/utility) → `SkillEvolver.evolve_skill`
  (LLM-free heuristic: uses>=5 И success_rate<0.8 → evolve).
- `kernel/self_evolution.py::KnowledgeAwareReasoning` / `PolicyAwareValueSystem`
  (value-driven reasoning).
- MISSING: архитектурная самоэволюция (code-gen) вне sandbox; reflection поверх outcome.

### 10. Persistence/recovery — IMPLEMENTED
- `composition/knowledge_persistence.py::KnowledgeSnapshotStore.save/load` (graph+index+
  trust+procedural+episodes+semantic+vectors+normative).
- `run_kroft._save_knowledge` пишет всё в один JSON.
- P0: recovery доказан (16792/16746 byte-identical, sha256 зафиксирован).
- Guard: `save(destructive=False)` защищает от стирания vectors при broad-test.

## Что НЕ нужно переделывать
- Knowledge Foundation (P0 CLOSED).
- Retrieval + Context + LLM wiring (P1 CLOSED).
- Snapshot persistence (Layer 10) — работает, защищён guard.
- Representation (KEEP B, gate CLOSED).

## Минимальные следующие шаги по слоям
- L5 Memory: эпизодическая память вне snapshot (опц.) — не блокирует.
- L6 Tool: подключить `TerminalExecutor` в `MultiAgentExecutor` (capability="shell"),
  зарегистрировать `ArchitectAgent` (сейчас route есть, executor нет).
- L7 Planning: долгосрочная декомпозиция (опц.).
- L8 Autonomous: включить `AgentLoop` в `interactive_query` (не только --agent-runtime).
- L9 Self-improvement: расширить gate на reflection (опц.).

## KROFT OS CURRENT MATURITY = 6/10
(IMPLEMENTED: 1,2,3,4,10; PARTIAL: 5,6,7,8,9; BROKEN: arch-route→executor mismatch)

## NEXT SINGLE MILESTONE
**Wire Tool Execution layer (L6): зарегистрировать `ArchitectAgent` + подключить
`TerminalExecutor` (capability="shell") в `MultiAgentExecutor`, чтобы `_route_capability`
→ `delegate_step` → реальный executor не падал в legacy path.**
Один этап, минимальный patch, без новых abstraction.

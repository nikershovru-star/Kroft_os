---
id: ADR-101
title: Daily-use pipeline — live vault data + interactive contour
status: accepted
date: 2026-08-06
evidence_level: V
addresses:
  - TZ-DAILY-01
---

# ADR-101 — Daily-use pipeline

## Context

ТЗ-RUN-01 ext (ADR-100) сделал панель KROFT Desktop, но она кормилась **demo-seed** (245 notes,
trust 0.97) — composition-level scaffolding, не живая активность. Для ежедневного использования
цифры должны быть живыми: Memory notes = реальные заметки Obsidian, Tasks = реальные задачи.
Также нужен минимальный интерактивный контур (query → agent loop → ответ), чтобы продуктом
можно было пользоваться каждый день.

## Decision

- **ObsidianVaultReader** (`services/obsidian_vault_reader.py`) — НОВЫЙ узкий шов (vault reader ещё
  не было). Stdlib `pathlib`, читает `*.md` рекурсивно; graceful (нет path → `[]`).
- **KnowledgeEngine.ingest** (ТЗ-KNOWLEDGE-ENGINE-01, ADR-091) — **ПЕРЕИСПОЛЬЗОВАН** (НЕ дублирован):
  vault notes → граф. Dashboard `memory_notes` уже читает `graph.nodes()` → становится живым.
- **TaskStore** (`services/task_store.py`) — НОВЫЙ (существующего НЕ было); реальные queued задачи
  (0 пока agent loop не использует). Dashboard `tasks` уже поддерживает `task_store.list()`.
- **run_kroft**: `--vault <path>` (ingest vault → живой memory_notes) + `--interactive`
  (query → `kernel.tick(Intent)` → `ReferenceSearchService.search` отвечает из живого графа).
- agents/models/marketplace **остаются demo** для наглядности (честно задокументировано).

## Constraints honored

- **K1** — stdlib + contracts (ObsidianVaultReader: pathlib only).
- **K5** — reuse KnowledgeEngine / ContentIndex / ReferenceSearchService; НЕ дублировано. Новые швы
  (ObsidianVaultReader, TaskStore) — там, где переиспользовать НЕЧЕГО (не существовало).
- **K6** — dashboard читает duck-typed providers (composition), services→contracts only.
- **O1** — graceful degradation (нет vault / TaskStore → 0, не crash).
- **I-09** — детерминизм (LLM-free ingest + search; идентичный query → идентичный ответ).
- **Флаг C** — standalone (НЕ в build_kernel). **Флаг 1b** — тесты отдельно.

## Known gotchas / light flags

- **Флаг 2 (light):** dashboard читает приватные `_installed` / `_peers` / `_state`. Duck-typed
  observability приемлема, но при появлении публичных аксессоров — перевести на них (заметка).
- Vault path может содержать пробелы — читаем через `pathlib`, не shell.

## Non-scope

GUI; поведенческие loop'ы Sales/Research/... агентов; Enterprise Security (Ed25519/PKI/CA) — post-MVP.

## Testing

- `tests/desktop/test_run_kroft.py` (13 tests): boot/demo (8) + live vault ingestion, graceful no-vault,
  TaskStore live, interactive answers from vault, interactive determinism (5).
- Ad-hoc: реальный vault (Obsidian Vault root) → `memory_notes=16139` (живые заметки).
- Arch-gate + akb-lint: 99→**100 ADR PASSED**.

# OPERATIONS_LOG — Журнал болей (product-mode, Phase C завершён)

Ежедневный ежедневный запуск автономных агентов с предохранителем (ADR-103, Wave C6).

## Ежедневный запуск
```
PYTHONPATH=. python composition/run_kroft.py \
  --vault "C:\Users\Nikita\Documents\Obsidian Vault" --agent-runtime --interactive
```
- `--agent-runtime` включает мультиагентный контур (AgentRuntime + blackboard + delegation + coordinator + trust + telemetry + approval gate).
- `--interactive` включает human-in-the-loop approver: чувствительные действия (finance/coding) спрашивают `одобрить? [y/N]` в stdin. Без `--interactive` — demo auto-approve (только для CI/boot).
- Чувствительные capabilities: `finance`, `coding`. При отказе / таймауте (300s) / сбое approver → default-deny (fail-closed).

## Формат записи боли
| Дата | Что делал | Что не понравилось | Частота | Приоритет |
|------|-----------|-------------------|---------|-----------|
|      |           |                   |         |           |

## Записи болей (live journal)
> Сюда вписываем реальные боли из ежедневного использования. Пусто = пока нет болей.

| Дата | Что делал | Что не понравилось | Частота | Приоритет |
|------|-----------|-------------------|---------|-----------|
|      |           |                   |         |           |


- Еженедельно группировать по частоте; чинить только самые болезненные маленькими задачами (≤2 модуля, без новых портов/абстракций).
- Всё, что требует нового порта/слоя → бэклог v0.2, не строится заранее.
- Триггер v0.2 — через несколько недель эксплуатации, когда журнал накопит устойчивый паттерн болей.

## Известные заметки (не блокируют, из вердиктов Wave C)
- **Флаг 1 C6 / product-mode (light):** два `input()` на одном stdin — `run_interactive` читает запрос, а `_human_approver` читает ответ в фоновом потоке (`ThreadPoolExecutor`). На реальном TTY работает последовательно; в piped/CI — возможен race/перемешивание. Приемлемо: CI/boot использует auto-approve, HITL — только в `--interactive`.
- **Флаг 2 C6 / product-mode (light):** TTL 300s + `shutdown(wait=False)` — неотвеченный approver оставляет поток жить до завершения; при частых таймаутах потоки накапливаются (ограничено `max_workers=1` на вызов). Заметка, не блок.
- **Флаг 1 C3 (medium-light):** два расходящихся read-path доверия — `trust_score_of` (MAX по TrustMeta) и `current_trust` (LATEST по record_outcome). Consumer, читающий `trust_score_of` (роутинг ORCH-01, marketplace-гейтинг), не видит delegation-дельты. Растущий долг; унифицировать при реальном сценарии.
- **Флаг 2 C1 (light):** `executor_id = capability` для trust-dельты; при двух executor на одну capability дельта сольётся.
- **Флаг 1 C2 (light):** `build_workflow` строит одношаговый Workflow; multi-step планирование — Wave C4+ (отложено).
- **Флаг 2 C2 (light):** Workflow не персистится (нет workflow-store для resume/retry) — Wave C5+ (отложено).

## Статус Phase C
Реализованы C1 → C2 → C3 → C6. Отложены до реальных сценариев: C4 (Strategies Sequential/Hierarchical), C5 (Review Loop + partitioned bus + workflow-store). Фаза строительства ЗАКРЫТА; далее — product-mode.

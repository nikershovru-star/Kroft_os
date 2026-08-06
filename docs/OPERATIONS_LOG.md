# OPERATIONS_LOG — Журнал болей (product-mode, Phase C завершён)

Ежедневный ежедневный запуск автономных агентов с предохранителем (ADR-103, Wave C6).

## Ежедневный запуск
```
PYTHONPATH=. python composition/run_kroft.py \
  --vault "C:\Users\Nikita\Documents\Obsidian Vault" --interactive
```
- `--agent-runtime` теперь **включён по умолчанию** (подключён к ядру, product-mode). Routed capabilities (finance/coding/...) идут через `AgentRuntime.delegate_step` (blackboard + delegation + trust + telemetry + approval gate).
- `--no-agent-runtime` — явный opt-out: legacy `orchestrator.dispatch` (без gate/blackboard/delegation).
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
- **Флаг 1 (product-mode, light):** несколько agent-dispatch поверхностей — сейчас четыре: `runtime.delegate_step` (ядро), `agent_executor` (AGENT-EXEC), `delegated` (pre-ТЗ), и `interactive_query` вызывает `delegate_step` напрямую (минуя `orchestrator.dispatch`). Счёт не дублируется (проверено), но поверхности должны оставаться согласованными. Рекомендация v0.2: свести интерактивный routed-путь тоже через `orchestrator.dispatch` (единая dispatch-поверхность).
- **Флаг 2 (product-mode, light):** накопление legacy-путей — при default-ON runtime пути `agent_executor`/`delegated` становятся почти мёртвым кодом (opt-out). Нормально для backward-compat, но удалить в v0.2, когда opt-out перестанет быть нужен.
- **Флаг 1 C3 (medium-light):** два расходящихся read-path доверия — `trust_score_of` (MAX по TrustMeta) и `current_trust` (LATEST по record_outcome). Consumer, читающий `trust_score_of` (роутинг ORCH-01, marketplace-гейтинг), не видит delegation-дельты. Растущий долг; унифицировать при реальном сценарии.
- **Флаг 2 C1 (light):** `executor_id = capability` для trust-dельты; при двух executor на одну capability дельта сольётся.
- **Флаг 1 C2 (light):** `build_workflow` строит одношаговый Workflow; multi-step планирование — Wave C4+ (отложено).
- **Флаг 2 C2 (light):** Workflow не персистится (нет workflow-store для resume/retry) — Wave C5+ (отложено).

## Архитектурные guidance для v0.2 (knowledge-capture, НЕ строим сейчас)
Зафиксировано из product-mode review (2026-08-06). Применять ТОЛЬКО когда журнал подтвердит реальную боль effector (агент может ответить, но не может сделать/записать). Не текущая итерация.

### Effector layer (самая вероятная первая боль из бэклога)
1. **Переиспользовать паттерн `services/agent_orchestration/healing.py`** (`AuditLogger` + approval-gating), а НЕ изобретать новый effector-каркас. Тот же механизм audit + gating, что уже работает для self-healing.
2. **Каждый external-write обязан проходить тот же `IApprovalGate`, что и `delegate_step`** — иначе предохранитель снова окажется «в обход» для записи во внешний мир (создание заметки, отправка, trade). Ровно та дыра, которая была с Approval Gate на early-wave: гейт защищал `delegate_step`, но routed-capability шёл в `orchestrator.dispatch` мимо него, пока не исправили маршрутизацию. Для effector это правило №1: gate — единая точка, external-write НЕ может его миновать.
3. **Единая dispatch-поверхность:** интерактивный routed-путь и effector-path оба идут через orchestrator (см. Флаг 1 light выше) — чтобы не размножать поверхности, которые потом рассинхронизируются с гейтом.
- Эффектор = НОВЫЙ ПОРТ (`contracts/i_effector.py` по K5/K6) → строго бэклог v0.2, не строится заранее (discipline product-mode).

## Статус Phase C
Реализованы C1 → C2 → C3 → C6. Отложены до реальных сценариев: C4 (Strategies Sequential/Hierarchical), C5 (Review Loop + partitioned bus + workflow-store). Фаза строительства ЗАКРЫТА; далее — product-mode.

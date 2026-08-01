---
tags: [kroft, architecture, review, audit, maturity]
created: 2026-07-31
status: review
subject: System-wide architecture audit of KROFT_OS (all Waves + ADRs)
author: Staff/Principal review (Hermes)
---

# KROFT_OS — Architecture Review v1.0

> Системный аудит как Principal/Staff Architect. Предмет — долгоживущая
> **операционная система для интеллектуальных агентов**, а не AI-фреймворк.
> Охват: все Waves (0–14), ADR-001..009, ядро, порты, платформы, сервисы.
> Каждый вывод привязан к реальному файлу в репозитории `KnowledgeOS-v5`.
> Связано: [[ROADMAP]], [[ADR-009 Policy Platform]], [[ADR-006 Model Platform]].

---

## 1. Метод

Аудит проведён чтением несущих файлов, а не по описанию:
- `tests/test_architecture.py` — axis-gate (enforced dependencies)
- `kernel/kernel.py` + `infrastructure/container.py` — ядро и композиция
- `services/agent_service.py` (1106 строк), `services/scheduler.py`
- `infrastructure/eventbus.py`, `policies/budget_policy.py`
- `contracts/i_llm.py`, `adapters/omni_route_adapter.py`, `services/policy_engine.py`
- `docs/roadmap/ROADMAP.md` — 10 принципов, 14 волн, 5 этапов

Критерий: соответствие заявленным принципам (Kernel First, Contracts Before Code,
Observability First, Everything is a Resource, Event Driven, Policy Driven,
Provider Agnostic, Evidence Before Knowledge, Learning Through Metrics,
Evolution Without Rewrites) при горизонте 1–3 года и десятках платформ /
сотнях плагинов / многопользовательском режиме.

---

## 2. Сильные стороны (КРОВНОЕ ЯДРО — не трогать)

Эти решения верны и должны остаться фундаментом.

1. **Реальный hexagonal gate, а не декларация.** `tests/test_architecture.py`
   статически проверяет запрещённые cross-layer импорты и блокирует
   `services → services` (кроме relative — см. риск R7). Ядро импортирует только
   `contracts/infrastructure/runtime` (`kernel/kernel.py:21-24`), никогда адаптеры.
   Это редкая дисциплина для Python-проекта и она работает.

2. **Policy-as-Code + PolicyEngine.** `contracts/i_policy.py` + `services/policy_engine.py`
   реализуют пайплайн Veto→Filter→Rank→Fallback без знания семантики правил.
   Движок не меняется при добавлении политики → **Open/Closed соблюдён**.
   Это эталонный паттерн для всей системы.

3. **Provider-agnostic граница LLM.** `ILlm` (`contracts/i_llm.py`) — чистый контракт;
   `OmniRouteAdapter` (`adapters/omni_route_adapter.py:19`) импортирует только
   `contracts`, не знает про шлюз кроме URL. Dumb-pipe vs gateway-truth (`actual_model`
   из заголовков) — зрелое решение double-routing. Смена backend = смена base_url.

4. **Composition Root централизован.** `DependencyContainer` (`infrastructure/container.py`)
   — единственная точка вязки. Ядро не создаёт конкретику напрямую.

5. **Capability/plugin механизм существует.** `contracts/plugin.py`,
   `infrastructure/plugin_loader.py`, `runtime/capability_registry.py` + тесты
   (`test_plugins.py`, `fixtures/plugin_agent_ext.py`) — расширение без правки ядра
   реально работает для части системы.

---

## 3. Выявленные риски

### R1 — CRITICAL. AgentService — регекс-монолит на 1106 строк (нарушение Open/Closed)
`services/agent_service.py` содержит один `PATTERNS` из ~80 регексов с ХРУПКИМ
порядком («must precede generic `find ...`», «Stage 49/51/54…»). Каждый новый
интент = ПРАВКА гигантского списка. Это прямо противоречит принципу
«Evolution Without Rewrites» и обещанию Plugin Platform. При сотнях плагинов
каждый будет форкать/дописывать этот список → merge-ад и регрессии. NLU-ядро
системы не имеет точки расширения интентов.
**Доказательство проблемы:** добавление рус/англ варианта требует вставки ВНУТРЬ
одного модуля (см. этапы 49/51/54 в комментариях), а не нового файла-плагина.

### R2 — HIGH. Состояние политик/бюджета in-memory, однопользовательское по умолчанию
`policies/budget_policy.py:44` держит `_state: Dict[user_id, ...]` в памяти
процесса; `user_id` по умолчанию `"default"` (`contracts/i_policy.py`). Нет
persistence (v0.1 по ADR-009), нет реальной идентификации пользователя из
auth/session слоя. **Многопользовательский режим НЕ готов** — он отложен в v1.0
без интерфейса для него. Перезапуск теряет лимиты.

### R3 — HIGH. EventBus — in-process, без транспорта (принцип 5 не выполнен для распределения)
`infrastructure/eventbus.py` — `InMemoryEventBus`: подписчики в том же процессе,
опциональный JSONL-append через `IFileSystem`. Нет брокера, нет cross-process,
нет replay кроме файлов. «Event Driven» работает только внутри процесса.
**Распределённое исполнение невозможно** без абстракции транспорта.

### R4 — HIGH. ILlm.sync-блокирующий порт — потолок масштабирования
`contracts/i_llm.py: complete()` синхронный (urllib). `Router.execute`
(`services/policy_engine.py`) вызывает `adapter.complete` последовательно, retry
без backpressure. `InMemoryEventBus.publish_sync` крутит sync-хендлеры через
`asyncio.to_thread` — значит блокирующий вызов занимает поток. При десятках
платформ и сотнях плагинов sync-LLM = потолок concurrency, нет cancellation,
нет структурированной конкурентности.

### R5 — MEDIUM-HIGH. Гейт имеет слепое пятно и не является CI-инструментом
`tests/test_architecture.py` пропускает relative imports (`if node.level > 0: return`,
строка 47). Поэтому `services/agent_service.py:7` `from .tool_registry import
ToolRegistry` (service→service!) **проходит гейт**, хотя `test_services_do_not_cross_import`
должен его блокировать. Плюс гейт — это pytest, нет `tach.toml` в репо
(проверено: `ls | grep tach` → нет). Если тест не запускается в CI, нарушения
проскальзывают молча. Гейт даёт **ложную уверенность**.

### R6 — MEDIUM. Две кандидатуры на «ядро» (governance-риск)
ROADMAP называет каноническим микроядром `hermes-kernel-v2` (ADR-001..032),
а `KnowledgeOS-v5` — полигон. Но в репозитории `KnowledgeOS-v5` есть СОБСТВЕННОЕ
`kernel/kernel.py` (отдельный микроядро). Итого два ядра. Без явного решения,
какое канонично, границы ответственности размываются (чья EventBus? чей Registry?).

### R7 — MEDIUM. Persistence везде best-effort с `except: pass`
`kernel/kernel.py` (`_try_snapshot_graph`, `_try_restore_index`), `eventbus.py`,
`scheduler.py` — все swallow exceptions. Для долгоживущей ОС молчаливая потеря
снимка/события = тихая потеря данных без сигнала в observability.

### R8 — MEDIUM. Граф как универсальное хранилище в одном JSON-файле
`IGraphBuilder` + `Kernel._try_restore_graph` восстанавливают состояние из
`data/graph_snapshot.json`. Нет concurrency, sharding, multi-tenant изоляции.
При сотнях плагинов и мульти-тенантности один файл — потолок.

### R9 — MEDIUM. Observability — принцип без порта
Принцип 3 («каждый сервис публикует TraceID/Latency/Errors») заявлен, но нет
`IObservability` порта, нет tracing-sink, нет metrics-registry. `LlmResponse`
носит поля (`trace_id`…), но никто не обязан их заполнять контрактом; в
`eventbus.py:54,68` ошибки хендлеров уходят в `print`. Observability ad-hoc.

### R10 — LOW-MEDIUM. Порты без версионирования/compat-слоя
При десятках адаптеров сломать `ILlm` = сломать все. ROADMAP упоминает
«Contract/Golden/Compat» (Wave 2), но compat-слоя/схема-версии на портах нет.
Нет deprecation-политики.

### R11 — LOW. Registry агрегирует in-process, статически
`ModelRegistry.catalog()` (`contracts/model_registry.py`) — пассивный держатель
`_by_id`. Для гибридного/облачного развёртывания каталоги моделей живут в
других процессах/регионах; реестр должен быть сервисом с discovery, а не
локальным dict.

---

## 4. Рекомендации (каждая привязана к проблеме)

| ID | Риск | Рекомендация | Обоснование проблемы |
|----|------|--------------|----------------------|
| REC-1 | R1 | Вынести NLU из монолита: порт `IIntentRouter` + intent-хендлеры как плагины (каждый интент = отдельный зарегистрированный обработчик с приоритетом), убрать `PATTERNS`. | AgentService нарушает Open/Closed; плагины не могут вкладывать интенты. |
| REC-2 | R2,R8 | Ввести `IStateStore` порт (key-value + timeseries) для policy-state, graph, budget; реализации: in-memory (v0.1), sqlite/json (v1.0). Многопользовательность через `tenant_id` в контексте. | Бюджет/состояние теряются при рестарте, один user «default». |
| REC-3 | R3 | Абстрагировать транспорт шины: `IEventTransport` (in-proc / broker / grpc). `InMemoryEventBus` — одна из реализаций. | Распределение невозможно без транспорта. |
| REC-4 | R4 | Сделать async первичным портом (`async def complete`) ИЛИ явный dual sync/async; `Router.execute` с cancellation + backpressure. | Sync-LLM блокирует потоки при масштабе. |
| REC-5 | R5,R6 | (a) Добавить `tach.toml` и запускать axis-gate в CI; (b) закрыть blind spot relative imports в гейте; (c) решить каноничное ядро (hermes-kernel-v2 vs local kernel). | Гейт не ловит реальные нарушения; два ядра. |
| REC-6 | R7 | Явная обработка ошибок persistence: `Result`/`error` в audit-log событием, метрика failed_snapshots. | Тихая потеря данных. |
| REC-7 | R9 | Добавить `IObservability` порт (trace/metrics/log sink); сделать заполнение полей `LlmResponse`/событий обязательным в контракте. | Принцип 3 не enforce-ен. |
| REC-8 | R10 | Schema-version на портах + compat-shim при ломающем изменении. | Масштаб адаптеров требует обратной совместимости. |

Новые платформы (Observability/Security/Workflow/Tool) из ROADMAP — НЕ добавлять
автоматически. Observability (REC-7) обоснована R9 (принцип есть, порта нет).
Security/Privacy/SecurityPolicy уже в ADR-009, но не реализованы — это долг Wave 5,
а не новая платформа.

---

## 5. Приоритет исправлений

| Приоритет | Риски | Действие |
|-----------|-------|----------|
| **CRITICAL** | R1 | REC-1: декомпозиция AgentService до того, как появятся плагины-интенты. Иначе Plugin Platform невозможен. |
| **HIGH** | R2, R3, R4 | REC-2/3/4: state-store порт, event-transport, async-LLM. Блокируют мульти-тенант, распределение, масштаб. Сделать ДО роста числа платформ. |
| **MEDIUM** | R5, R6, R7, R8, R9 | REC-5/6/7: гейт в CI + blind spot, каноничное ядро, обработка ошибок persistence, IObservability порт. Укрепление фундамента. |
| **LOW** | R10, R11 | REC-8, эволюция Registry в сервис. Отложить до реальной нужды в версионировании/удалённых каталогах. |

---

## 6. Обновлённая целевая архитектура KROFT_OS

```
                         KROFT_OS  (Autonomous Intelligence OS)
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │              MICROKERNEL (canonical: hermes-kernel-v2)  │
        │  Lifecycle │ DI(CompositionRoot) │ AxisGate(tach)       │
        └─────────────────────────┬─────────────────────────┘
                                  │ depends on CONTRACTS only
   ┌──────────────┬───────────────┼───────────────┬──────────────┐
   │  CORE PORTS  │  STATE PORTS  │  RUNTIME PORTS │  PLATFORM    │
   │ ILlm IEmbed  │ IStateStore*  │ IEventBus      │  ADAPTERS    │
   │ IGraph IPolicy│ IObservability*│ (IEventTransport*)│ OmniRoute  │
   │ IIntentRouter*│              │ ICapabilityReg  │ Ollama      │
   │ ITool        │              │                │ (future:Sec) │
   └──────┬───────┴───────┬───────┴───────┬──────┴──────┬───────┘
          │               │               │             │
   ┌──────▼─────┐  ┌──────▼──────┐  ┌─────▼──────┐ ┌────▼───────┐
   │PolicyEngine│  │StateStore   │  │EventBus    │ │Model/Ollama│
   │+ policies  │  │(mem/sqlite) │  │(in-proc/   │ │adapters    │
   │Router      │  │Budget multi-│  │ broker/grpc)│ │            │
   │AgentService│  │tenant       │  │            │ │            │
   │(intent     │  │             │  │            │ │            │
   │ plugins)   │  │             │  │            │ │            │
   └────────────┘  └─────────────┘  └────────────┘ └────────────┘
        (*) = NEW port from this review (REC-2/3/4/7)
```

Ключевые отличия от текущей:
- `IIntentRouter` (REC-1) вместо регекс-монолита; интенты — плагины.
- `IStateStore` (REC-2) выносит всё состояние из памяти процесса.
- `IEventTransport` (REC-3) делает шину распределяемой.
- `ILlm` async-first (REC-4).
- `IObservability` (REC-7) делает принцип 3 enforce-енным.

---

## 7. Оценка зрелости

**Итого: 6.5 / 10.**

Обоснование:
- **+3.5** — зрелая hexagonal-дисциплина, DI, Policy-as-Code, provider-agnostic
  LLM-граница, реальный plugin-механизм. Для однопроцессного ассистента это
  крепкая архитектура (8/10 в своём классе).
- **−2.0** — зазор между амбицией («ОС для интеллектуальных систем», десятки
  платформ, мульти-тенант, распределение) и реализацией (всё in-process,
  in-memory, sync, однопользовательское по умолчанию, NLU-монолит). Это не
  «фичи на потом», а фундаментальные границы, которые поздно менять.
- **−1.0** — гейт не enforce-ен в CI и имеет слепое пятно; две кандидатуры на
  ядро; observability не портифицирован; persistence молчит об ошибках.
- **+0.5** — честная Wave-по-Wave дисциплина без «вечной архитектуры», ADR-009
  конкретен до сигнатур, тесты зелёные.

**Вердикт:** архитектура **фундаментально здорова для v0.1** (локальный
однопользовательский ассистент), но **не готова к заявленному горизонту 1–3 лет**
без устранения CRITICAL/HIGH рисков (R1–R4) на этапе, пока система ещё мала.
Главный leverage — REC-1 (декомпозиция AgentService) и REC-2/3/4 (вынесение
состояния/шины/LLM из процесса). Сделать это сейчас стоит дёшево; сделать после
роста до сотен плагинов — переписывание ядра (нарушение принципа 10).

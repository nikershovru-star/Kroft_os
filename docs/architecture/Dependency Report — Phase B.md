---
title: "KROFT_OS — Dependency Report (Phase B: Architecture Stabilization)"
version: "1.0"
date: "2026-08-01"
status: "analysis"
phase: "B"
author: "Hermes (Architecture Intelligence Protocol)"
purpose: >
  Статический анализ межслойных зависимостей KROFT_OS. Входные данные для
  решения об устранении нарушений LAW K1. НЕ содержит изменений кода —
  только отчёт + предложения (Шаги 1–4 Phase B).
---

# KROFT_OS — Dependency Report (Phase B)

> **Статус:** анализ завершён, изменений кода НЕ внесено. Рефакторинг (Шаг 7)
> требует утверждения пользователя (LAW K5: Humans Approve).

## Метод

Статический анализ `grep` по всем 7 пакетам (`kernel/ runtime/ services/
adapters/ infrastructure/ plugins/ policies/ cli/`) на предмет импортов
других проектных пакетов. Каждый импорт классифицирован по матрице
допустимости (см. `AKB/laws.yaml` K1, `tests/test_architecture.py` ALLOWED).

## Шаг 1 — Таблица зависимостей kernel/*

| # | kernel file | Импорт | Причина | Категория (Шаг 2) | Можно убрать? | Вариант исправления |
|---|-------------|--------|---------|-------------------|---------------|---------------------|
| K1 | `kernel/kernel.py:21` | `from infrastructure import DependencyContainer` | Kernel создаёт/владеет DI-контейнером (composition root) | **A. Composition Root** | ✅ да | Перенести создание `DependencyContainer` в `composition/` (Bootstrap). Kernel получает контейнер готовым через конструктор. |
| K2 | `kernel/kernel.py:22` | `from infrastructure.snapshot_store import SnapshotStore` | Kernel вызывает `SnapshotStore.save/restore` для персиста графа/индекса | **B. Persistence** | ✅ да | Ввести порт `ISnapshotRepository` (contracts). Kernel зависит от `ISnapshotRepository`, реализация в infrastructure. |
| K3 | `kernel/kernel.py:24` | `from runtime import RuntimeContext` | Kernel хранит runtime-контекст | — (разрешено K1: kernel→runtime OK) | n/a | Не трогать. |

**Вывод:** всего 2 нарушения K1 в `kernel/` (K1, K2). Оба — импорт
`infrastructure.*`. Больше kernel ничего не импортирует из запрещённых слоёв.

## Шаг 2 — Категоризация (по заданным категориям)

- **A. Composition Root:** `DependencyContainer` (K1) — вообще не должен жить
  внутри kernel. Создание контейнера = ответственность Bootstrap/Composition Root.
- **B. Persistence:** `SnapshotStore` (K2) — персистенция графа/индекса.
  Должна быть за контрактом `ISnapshotRepository`.
- **C. Configuration:** не найдено в kernel (ConfigLoader используется в cli/, не в kernel).
- **D. Logging:** не найдено в kernel.
- **E. Infrastructure Services:** не найдено в kernel (только 2 выше).
- **F. Bootstrapping:** `DependencyContainer` (K1) по сути bootstrapping-объект.

## Шаг 3 — Что может стать Contract/Port

| Текущая реализация | Предлагаемый порт (contracts) | Обоснование |
|--------------------|-------------------------------|-------------|
| `infrastructure.DependencyContainer` | **не порт** — это сам Composition Root. Kernel его вообще не должен видеть (получает готовый, инверсией зависимостей). | DI-контейнер — инфраструктура сборки, не бизнес-порт. |
| `infrastructure.SnapshotStore` | `contracts.ISnapshotRepository` (или расширить существующий `ISnapshotable`) | Kernel должен знать только интерфейс «сохрани/восстанови dict», не реализацию. |

## Шаг 4 — Новая карта зависимостей (целевая)

```
Contracts  (ports: IKernel, IEventBus, ISnapshotRepository, IFileSystem, ...)
    ↑
Runtime    (RuntimeContext, registries, supervisor)
    ↑
Kernel     (lifecycle FSM, получает container + ports ГОТОВЫМИ)
    ↑                       ↑                    ↑
Services                Adapters            Infrastructure
                                ↑
                    Composition Root  ← bootstrap_v2 / composition/
                    (создаёт DependencyContainer, SnapshotRepository,
                     EventBus, Services, Adapters, Plugins; впрыскивает в Kernel)
```

**Инвариант (K1):** Kernel ничего не знает ниже Runtime. Все `infrastructure.*`
импорты уходят из `kernel/`.

## ДОПОЛНИТЕЛЬНО — Полный аудит всех слоёв (LAW K1–K8)

### kernel → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `infrastructure.DependencyContainer` | ❌ | **K1** | HIGH — kernel знает DI-реализацию |
| `infrastructure.SnapshotStore` | ❌ | **K1** | HIGH — kernel знает persistence-реализацию |
| `runtime.RuntimeContext` | ✅ | — | — |
| `contracts.*` | ✅ | — | — |

### runtime → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `contracts.*` (все файлы) | ✅ | — | — |
| `runtime.services/*` (внутри runtime) | ✅ | — | — |

✅ **runtime чист** — импортирует только contracts.

### services → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `contracts.*` (все файлы) | ✅ | — | — |
| внутри-services (cross-import) | частично | — | проверяется `test_services_do_not_cross_import` (зелёный) |

⚠️ **Риск:** `policy_engine.py:18` импортирует `from contracts.model_registry import ModelRegistry` — это **конкретный класс**, не порт. Minor (K6): сервис зависит от конкретной реализации в contracts, а не от порта. Не блокирует, но отметить как tech-debt.

### adapters → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `contracts.*` (все файлы) | ✅ | — | — |
| ⚠️ `adapters/router.py:15` → `from policies.budget_policy import estimate_cost` | ❌ | **K6** | HIGH — adapters импортирует sibling-пакет `policies` напрямую, минуя contracts |
| `adapters/rule_based_planner.py` → `contracts.i_workflow` | ✅ | — | — |

🔴 **НОВОЕ НАРУШЕНИЕ (вне зоны kernel):** `adapters/router.py` → `policies.budget_policy`.
Межслойное общение adapters→policies должно идти через port (`IPolicy`/`PolicyContext` из contracts), не через прямой импорт модуля `policies`. Это классическое K6-нарушение. **НЕ исправлять автоматически** — требует отдельного ADR/плана (см. Рекомендации).

### infrastructure → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `contracts.*` (config_loader, eventbus, graph_builder, metrics) | ✅ | — | — |

✅ **infrastructure чист** (импортирует только contracts — по K1 разрешено).

### plugins → *
Пусто (нет импортов проектных пакетов). ✅

### policies → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `contracts.i_llm`, `contracts.i_policy` | ✅ | — | — |

✅ **policies чист**.

### cli → *
| Импорт | Допустим | Нарушение | Риск |
|--------|----------|-----------|------|
| `kernel.Kernel`, `infrastructure.ConfigLoader`, `services.*` | ⚠️ по K1 | — | MEDIUM — cli выступает de-facto composition root (это ДОПУСТИМО для Composition Root, но он размазан между `cli/` и `bootstrap_v2.py`). |

✅ **cli не нарушает** (Composition Root легально импортирует все слои), но архитектурно раздроблен: wiring есть и в `cli/commands.py`, и в `bootstrap_v2.py`. Цель Phase B (Шаг 6) — консолидировать в `composition/`.

## Сводка нарушений

| ID | Слой | Нарушение | LAW | Серьёзность | Статус |
|----|------|-----------|-----|-------------|--------|
| V1 | kernel→infrastructure (DependencyContainer) | Composition Root в kernel | K1 | HIGH | требует фикса (Шаг 7) |
| V2 | kernel→infrastructure (SnapshotStore) | Persistence в kernel | K1 | HIGH | требует фикса (Шаг 7) |
| V3 | adapters/router.py→policies.budget_policy | прямой cross-import | K6 | HIGH | **НЕ трогать** — отдельный план |
| V4 | services/policy_engine.py→contracts.model_registry.ModelRegistry | зависимость от конкретики в contracts | K6 | LOW | tech-debt, отметить |
| V5 | cli/ + bootstrap_v2 раздробленный wiring | Composition Root не выделен | K3 (орг) | MEDIUM | цель Шага 6 |

## Потенциальные архитектурные риски

1. **Kernel tightly coupled to DI** (V1): невозможно instantiate Kernel без infrastructure → нарушает «Small Kernel» и тестируемость.
2. **Persistence leak** (V2): Kernel знает JSON-снапшот реализацию → смена стоража требует правки kernel.
3. **Adapters→Policies coupling** (V3): изменение `budget_policy` ломает `router` напрямую, минуя порты.

## Предложения по устранению (ЖДУТ УТВЕРЖДЕНИЯ — LAW K5)

1. **V1+V2 (kernel decoupling):** создать `composition/` слой (см. ADR-026). Kernel
   перестаёт импортировать `infrastructure`; получает `DependencyContainer` и
   `ISnapshotRepository` через конструктор. Каждый шаг — отдельный commit
   (Шаг 7). Arch-gate должен стать GREEN после завершения.
2. **V3 (adapters→policies):** заменить `from policies.budget_policy import estimate_cost`
   на вызов порта (напр. `IPolicy.estimate_cost` или передачу callable через contracts).
   Отдельный ADR/коммит — НЕ в рамках kernel-decoupling.
3. **V4:** `ModelRegistry` вынести в порт `IModelRegistry` (частично уже есть в contracts).
4. **V5:** консолидировать wiring в `composition/`, убрать дубли из `cli/`.

---
*Отчёт сгенерирован Hermes (Architecture Intelligence Protocol). Изменений кода нет.*

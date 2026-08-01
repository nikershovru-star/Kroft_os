---
tags:
  - hermes
  - v5
  - architecture
  - policy
  - wave5
  - design
created: 2026-07-31
status: deprecated
deprecated_by: "ADR-009 Policy Platform"
superseded_by: "ADR-009 Policy Platform"
version: 1.0
updated: 2026-07-31
author: Chief Knowledge Architect (Hermes)
summary: >-
  Черновик设计 политики (волна 5), вытеснен финальным ADR-009. Сохранён как
  история решения; НЕ использовать как источник истины.
---

# Policy Engine — Design Sketch (Wave 5)

> **Только проект, не код.** Черновик интерфейса для Wave 5, набросанный в конце
> сессии Model Platform (вертикаль closed: `b06f526` + `0edbe24`). Цель — «тёплый
> старт» завтра без усталого кода. Связано с [[Model Platform — Architecture (ADR-033)]]
> и [[Master Roadmap v2.0]].

## Интерфейс (набросок, не финальный)

```python
# contracts/i_policy.py — SKETCH, не коммитить как реализацию
from __future__ import annotations
import abc
from typing import Optional
from contracts.i_llm import ModelQuery, ModelInfo
from contracts.model_registry import ModelRegistry


class IPolicy(abc.ABC):
    """Policy = active actor that picks the model, not a passive filter.

    Open question (см. ниже): depends on Registry or vice-versa?
    Sketch assumes Policy wraps Registry.select() with budget/priority/fallback.
    """

    @abc.abstractmethod
    def select(self, query: ModelQuery, registry: ModelRegistry) -> Optional[ModelInfo]:
        """Greedy choice honoring budget, priority, offline-fallback."""
        ...

    @abc.abstractmethod
    def on_failure(self, query: ModelQuery, last: ModelInfo, error: str) -> Optional[ModelInfo]:
        """Next model in fallback chain, or None (give up)."""
        ...
```

## Открытые архитектурные решения (принять в следующей сессии)

### 1. Где хранить бюджет?
- **stateless** — бюджет считается per-call из входных метаданных; ничего не помним.
- **persistent** — `per-call / per-user / per-session / per-day` требует state:
  in-memory dict (теряется при рестарте) vs sqlite (просто, локально) vs graph-node
  (если бюджет — часть KG пользователя). Влияет на размер state и на то, нужен ли
  отдельный `IBudgetStore` порт.

### 2. Fallback — внутри Policy или обёртка вокруг `ILlm`?
- **внутри Policy**: `IPolicy.on_failure()` возвращает следующую модель; orchestrator
  крутит цикл. Меняет интерфейс `ILlm.complete()`? Нужен ли `try_next`?
- **обёртка (decorator) вокруг ILlm**: `PolicyAwareClient(ILlm)` ловит ошибки и сам
  делает fallback, не меняя `ILlm`. Меньше затрагивает существующие адаптеры.

### 3. Нужна ли очередь (async) или достаточно синхронного greedy?
- **greedy** — выбрали модель, вызвали, при ошибке `on_failure`. Покрывает 80%.
- **queue** — если конфликт приоритетов (много запросов, мало квот free-моделей),
  нужен фоновый worker + приоритезация. Это уже отдельная подсистема (Wave 10 Agent
  Platform близко). Решать только если реально упираемся в квоты.

## Связи

- Вертикаль Model Platform (готова): [[Model Platform — Architecture (ADR-033)]]
- Видение/волны: [[Master Roadmap v2.0]]
-Registry (Wave 4) — источник кандидатов для Policy: `ModelRegistry.select()`
-Граф-вертикаль (отдельный stage): 6 падающих тестов, точка отката `b06f526`

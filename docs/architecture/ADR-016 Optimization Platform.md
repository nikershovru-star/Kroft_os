---
tags: [kroft, adr, optimization, architecture, wave13]
created: 2026-07-31
status: accepted
version: 1.0
updated: 2026-07-31
author: Hermes (senior software architect)
summary: >-
  Wave 13 Optimization Platform: превращает Pattern (Wave 12) в Recommendation,
  классифицирует риск через Guardrail, и применяет конфигурацию только через
  явный двухфазный commit (propose → approve → apply → rollback). Никакой
  автоматики без возможности отката.
related:
  - "ADR-015 Learning Platform"
  - "ADR-014 Agent Platform"
  - "ADR-009 Policy Platform"
  - "ADR-010 Evaluation Platform"
---

# ADR-016 — Optimization Platform (Wave 13)

## Статус
**PROPOSED** — готов к реализации после approval.

## Контекст
Wave 12 (Learning) накапливает `ExecutionTrace` и извлекает `Pattern`
(«phi4 лучше gpt для reasoning»). Но знания лежат мёртвым грузом — система не
использует их для улучшения будущих прогонов. Wave 13 вводит Optimization, но
жёстко по Roadmap-guardrail: **Recommendation → Shadow Mode → Canary → Approval →
Rollback**. Никаких автоматических изменений без возможности отката.

## Решение
Три слоя + явный ConfigApplier:

1. **`IOptimizer`** — `recommend(patterns, current_config) → List[Recommendation]`.
   `PatternBasedOptimizer` генерирует `Recommendation` только при
   `pattern.confidence > 0.7` (LAW 5: на измеренном, не на интуиции).

2. **`IGuardrail`** — `validate(rec, traces) → GuardrailResult`. `SimpleGuardrail`
   классифицирует риск: `risk_score = 1.0 - pattern.confidence`;
   `< 0.2` → `approved`, `0.2..0.5` → `canary`, `>= 0.5` → `shadow`.
   Guardrail **только классифицирует** — не применяет.

3. **`ConfigApplier`** — двухфазный commit: `propose()` → `approve()` → `apply()`
   (+ `rollback()`). Хранит историю (`previous_value, new_value, timestamp,
   approved_by`) для отката. `target` — строковый путь (сериализуемый, безопасный).

4. **Интеграция (опц.)** — `AgentPlatform.run()` с `optimizer: Optional[IOptimizer]`
   вызывает `recommend()` и пишет `optimization_recommendations` в `AgentResult`.
   Только наблюдение, не изменение поведения (backward compat).

## Entities (из кода)
```python
@dataclass(frozen=True)
class Recommendation:
    id: str
    target: str           # "policy:ProviderSelectionPolicy:weights:reasoning"
    value: str            # JSON-serialized новое значение
    rationale: str
    confidence: float     # из Pattern.confidence
    source_pattern: str   # ссылка на Pattern (см. Отклонения)
    status: str = "proposed"  # proposed|shadow|canary|approved|applied|rolled_back

@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    stage: str            # shadow|canary|approved
    risk_score: float
    explanation: str

class IOptimizer(abc.ABC):
    def recommend(self, patterns, current_config) -> List[Recommendation]: ...

class IGuardrail(abc.ABC):
    def validate(self, rec, traces) -> GuardrailResult: ...
```

## Архитектурные законы (соблюдены)
- **LAW 1** — контракты (`contracts/i_optimization.py`) до кода.
- **LAW 2** — `ConfigApplier`/`AgentPlatform` импортируют только `contracts.*`,
  не конкретный `PatternBasedOptimizer`/`SimpleGuardrail`.
- **LAW 3** — `Recommendation`/`GuardrailResult` frozen; `ConfigApplier` хранит
  mutable-историю **явно** (не скрытый global state).
- **LAW 4** — каждая `Recommendation` ссылается на `source_pattern` (Wave 12).
- **LAW 5** — `recommend()` опирается на `Pattern.confidence` (измерено Wave 12),
  не на интуицию.
- **LAW 6** — `IOptimizer` имеет 1 реализацию (PatternBased) в v0.1; LLM-based —
  v1.0 (Wave 14). Порт отделяет политику рекомендаций от механики применения.
- **LAW 8** — новый Wave → новый ADR (этот).

## Отклонения от исходного спецы (честный фикс)
1. `Pattern` в коде (Wave 12) **не имеет поля `id`** — только `description,
   confidence, applies_to, recommendation`. Поэтому `Recommendation.source_pattern`
   — это **строка** (либо `Pattern.description`, либо нормализованный ключ). В ADR
   зафиксировано, что прямой id-ссылки нет; если Wave 14 потребует — добавим
   `pattern_id` в `Pattern`.
2. Спека пишет `value` как «JSON-serialized» — сохраняю как `str` (уже JSON-строка
   при использовании), без насильственного `json.loads` внутри frozen-сущности.
3. `IGuardrail.validate(rec, traces)` принимает `traces` (для будущего risk-скоринга
   по ExecutionTrace), но `SimpleGuardrail` v0.1 считает риск только из
   `confidence` (из `rec.source_pattern` через lookup), не трогая `traces`.

## Следующий шаг
Wave 14 — Autonomous Hermes (финальная волна: самоуправление, самооценка,
самоподдержка документации). НЕ начинать без явной команды.

# KROFT_OS — Architecture (component map)

> Дополнение к `README.md` (технический мануал) и `docs/PROJECT_CONTEXT_MAP.md`
> (архитектурный паспорт). Этот файл описывает конкретные компоненты слоёв и их
> связи. Законы LAW K1–K8 + F1–F6 обязательны (см. `docs/architecture/AKB/`).

## Echo-pattern router + LLM classifier (Этап 3, ТЗ-ECHO E1/E2/E3)

Лёгкая динамическая классификация запросов для выбора модели в Echo-паттерне.
Полностью локальна (модель через Ollama), graceful-degradation при недоступности.

### Boundary map (EXISTING → NEW, K5-verified)

| Роль | Модуль | Порт/класс | Статус |
|------|--------|-----------|--------|
| Порт классификатора | `contracts/i_classifier.py` | `IClassifier.classify(query) -> Optional[str]` | NEW (E3) |
| LLM-реализация | `services/model_router/classifier.py` | `LLMClassifier` | NEW (E3) |
| Правила (rule-based) | `contracts/i_router_policy.py` | `IRouterPolicy` | E1 (существует) |
| YAML-политика | `services/model_router/yaml_policy.py` | `YamlRouterPolicy` | E2 (существует) |
| Роутер | `services/model_router/rule_based_router.py` | `RuleBasedRouter(IRouterPolicy)` | E2 (есть, E3-интеграция) |
| Конфиг | `config/router_policy.yaml` | `classifier:` + `categories:` + `manual_overrides:` | E2/E3 |
| Wiring | `composition/run_kroft.py` (`--router`) | создаёт `LLMClassifier` из yaml | E3 |
| Ensemble | `services/model_router/ensemble_orchestrator.py` | `SimpleEnsembleOrchestrator` | E4 |

### Поток классификации (E3)

```
RouterRequest(query)
   │
   ├─ (1) req.category задан явно?  → используется напрямую (preclassified)
   ├─ (2) IClassifier.classify(query)  [LLM, phi3:mini]
   │        └─ вернул валидную категорию? → используется
   │        └─ None (модель недоступна / невалидный ответ) → fallback
   └─ (3) IRouterPolicy.classify(query)  [rule-based: manual_overrides → keywords → default]
        │
        ▼
   providers_for(category) → ProviderSpec[] → IModelRouter.client_for(name) → ILlm[]
        │
        ├─ 1 клиент                   → single complete()
        └─ >1 клиент (analytical)     → SimpleEnsembleOrchestrator (BEST_CONFIDENCE)
```

### Контракты

- `IClassifier.classify(query) -> Optional[str]`: возвращает одну из
  `code | creative | factual | analytical` или `None` (никогда не бросает в роутер).
- `LLMClassifier`: вызывает `ILlm.complete` с однословным промптом; на `LLMError` /
  `LLMTimeout` / невалидном ответе → `None` (rule-based fallback). In-memory кэш по
  prompt (только валидные метки). `timeout` берётся из `classifier.timeout` yaml.
- `RuleBasedRouter` НЕ реализует вызов провайдера — делегирует `IModelRouter`
  (OmniRouter). Не трогает ядро (`kernel/`), не меняет адаптеры LLM.

### Включение / отключение / смена модели (`config/router_policy.yaml`)

```yaml
classifier:
  enabled: true          # false -> чисто rule-based роутинг
  model: "phi3:mini"     # любая лёгкая модель в Ollama
  timeout: 5             # секунд на вызов классификатора
  fallback: "rule_based"
```

Env-оверрайд модели: `KROFT_CLASSIFIER_MODEL=gemma2:2b`. Роутинг включается флагом
`--router` в `run_kroft` (по умолчанию OFF → stock-path нетронут).

### Категории → модели (`config/router_policy.yaml`)

```yaml
categories:
  code:       [local-ollama, omni-route]
  creative:   [omni-route, local-ollama]
  factual:    [omni-route, local-ollama]
  analytical: [omni-route, local-ollama]   # ensemble (parallel N) для analytical
```

### Тесты

- `tests/model_router/test_echo_classifier.py` — IClassifier contract, parsing, cache,
  fallback (error/timeout/invalid), router classifier-first, real phi3 (skipped без
  `KROFT_RUN_INTEGRATION=1`).
- `tests/model_router/test_echo_router.py` — IRouterPolicy/YamlRouterPolicy, ensemble,
  RuleBasedRouter single/ensemble, `classifier_config()` из yaml, `--router` флаг.

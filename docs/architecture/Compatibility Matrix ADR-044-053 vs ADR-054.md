# Compatibility Matrix — ADR-044..053 vs ADR-054 (Cognitive Kernel Constitution)

> Phase B consolidation report. Для каждого существующего документа: соответствие
> новой архитектуре (ADR-054), требуемое обновление, изменение интерфейсов, новые
> зависимости, нарушения инвариантов.

| ADR | TZ | Соответствие ADR-054 | Требует обновления | Изменение интерфейсов | Новые зависимости | Нарушения инвариантов |
|-----|----|----------------------|--------------------|-----------------------|-------------------|------------------------|
| ADR-044 | TZ-015 Distributed Runtime | ✅ частично | ДА (Node Discovery/Registry/RemoteExec/SharedCtx/NetSupervisor/Metrics должны эмитить CognitiveEvent I-17, писать WorldState I-07) | + `CognitiveEvent` в порты discovery/metrics; SharedContext→I-08 projection | ADR-054 (I-07/I-08/I-17), EventBus reuse | ⚠️ Shared Context был «registry», теперь = федеративная проекция WorldState (I-08) — уточнить |
| ADR-045 | TZ-016 Autonomous Planner | ✅ | ДА (Planner = фаза Deliberate, НЕ Decision) | `Plan` несёт `ConfidenceScore` (I-12); Planner возвращает кандидатов, не выбор | ADR-055, ADR-054 §4 | ⚠️ ранее Planner совмещал выбор — разделить (I-03) |
| ADR-046 | TZ-017 Memory Evolution | ✅ | ДА (Memory-запись несёт ConfidenceScore; Learning через Policy+Commit) | `MemoryRecord.confidence: ConfidenceScore` (I-12); `ILearningPolicy` (I-14) | ADR-055, ADR-054 I-14 | — |
| ADR-047 | TZ-018 World Model | ✅ | ДА (предсказания несут ConfidenceScore; WorldState=SSOT I-07) | `Prediction.confidence: ConfidenceScore` | ADR-055 | — |
| ADR-048 | TZ-019 Agent Society | ✅ | ДА (Society = реализация Execute-фазы; репутация через ConfidenceScore) | `AgentReputation: ConfidenceScore` | ADR-055 | — |
| ADR-049 | TZ-020 Self Improvement | ✅ | ДА (Self Improvement = Runtime Reflection I-15; Learning через Policy+Commit I-14; меняет только soft/Normative) | `ILearningPolicy` (I-14); отделить от Cognitive Reflection | ADR-054 I-14/I-15/I-20 | ⚠️ ранее Self Improvement мог менять напрямую — ограничить I-14 |
| ADR-050 | TZ-021 AI Marketplace | ✅ | ДА (package несёт Provenance I-13; install через Policy Check I-14) | `PackageManifest.provenance` | ADR-054 I-13/I-14 | — |
| ADR-051 | TZ-022 Federated Knowledge | ✅ | ДА (SharedContext=I-08; sync только permitted subgraph; CognitiveEvent для federation I-17) | `SharedContext`=projection; `ISync` проверяет grant | ADR-054 I-08/I-17 | ⚠️ selective sharing уже default DENY — ок ✅ |
| ADR-052 | TZ-023 Cognitive OS | ⚠️ устарел структурно | ДА (заменить «каталог слоёв» на Cognitive FSM + сквозные контракты) | `CognitiveOS` = wiring FSM (I-01) + 3 контракта; не дерево модулей | ADR-054 все | ⚠️ ранее CognitiveOS как дерево — переписать под I-01/I-02 |
| ADR-053 | v2.0 Roadmap | ⚠️ теперь подчинён | ДА (добавить Executive/Decision/Attention/ResourceManager/Value/Confidence/LearningPolicy/Pipeline/LLM-Free/Contract; показать FSM) | — (только roadmap) | ADR-054, ADR-055 | — |

## Итог Phase B
- **9/10 ADR уже совместимы по сути** (порты в contracts, reuse WP-14/TZ-AGENT).
- **Требуют обновления интерфейсов** (добавить ConfidenceScore/Provenance/CognitiveEvent): все 10.
- **Критические уточнения**:
  1. TZ-016: Planner ≠ Decision (I-03) — разделить.
  2. TZ-020: Learning не пишет напрямую (I-14) — через ILearningPolicy.
  3. TZ-023: CognitiveOS → FSM-wiring, не дерево (I-01/I-02).
  4. TZ-015/022: SharedContext = федеративная проекция WorldState (I-08), не копия.
- **Новых нарушений LAW (K1/K3/K5/K6/K8) не выявлено** — ADR-054 согласован с K1..K8.

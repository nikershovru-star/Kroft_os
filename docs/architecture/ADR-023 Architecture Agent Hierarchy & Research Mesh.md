---
tags: [kroft, architecture-agent-hierarchy, research-mesh, adr-023, level-1-intelligence, ai-chief-architect]
created: 2026-08-01
author: Hermes (Research Architect)
protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0 (Уровень 1 — Intelligence для темы "10-уровневая иерархия + Research Mesh")
depends_on: [ADR-021 Runtime Evolution, ADR-022 Architecture Knowledge Base, ADR-020 Runtime Host, ADR-014 Agent Platform, ADR-003 Event Bus, docs/architecture/akb/]
summary: >-
  Синтез 10-уровневой иерархии зрелости архитектурного агента (Intelligence →
  Reviewer → Knowledge Base → Pattern Library → Simulator → Tech Debt → Evolution →
  Autonomous → Benchmark → AI Chief Architect) + Research Mesh (специализированные
  research-агенты). Исследованы: Anthropic multi-agent research (+90.2% vs single),
  AgentMesh/ChatDev, Automated ADR Generation (RAG-контекст критичен), Architectural
  TD Index (ML), Digital Twin для софта (stale twin хуже ничего). Ключевой инсайт:
  KROFT УЖЕ имеет substrate (Kernel+ComponentRegistry+Supervisor+IAgentPlatform+
  EventBus+AKB) → Research Mesh = KROFT-нативные агенты (компоненты), НЕ внешний
  оркестратор. Все уровни проверены на LAW K1–K8. Код НЕ пишется (Уровень 1).
---

# ADR-023 — Architecture Agent Hierarchy & Research Mesh

> Protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0 — Уровень 1 (Intelligence)
> Topic: 10-уровневая иерархия зрелости + Research Mesh (предложено пользователем).
> Date: 2026-08-01. Scope: research + synthesis. **No code in this ADR.**

---

## 1. Executive Summary

Пользователь разворачивает одноуровневый Architecture Intelligence Protocol в
**10-уровневую иерархию зрелости архитектурного агента** + **Research Mesh**
(мульти-агентский research-слой). Это meta-architecture самого Hermes-архитектора.

**Ключевой инсайт (заземление в KROFT):** KROFT УЖЕ имеет готовый substrate для
большинства уровней:
- Kernel + ComponentRegistry + Supervisor (ADR-020/021) → runtime для агентов.
- `IAgentPlatform` (ADR-014): `run(goal) -> AgentResult` (frozen, traceable).
- EventBus (ADR-003) → меж-агентская коммуникация.
- AKB (ADR-022) → Уровень 3 (Knowledge Base) УЖЕ реализован как данные.

Значит Research Mesh ≠ внешний оркестратор. Это **KROFT-нативные агенты**
(Code/Paper/Docs/Benchmark/Security Research Agents + Synthesizer) как компоненты,
реализующие `IAgentPlatform`, управляемые Supervisor как виртуальные акторы (Orleans,
ADR-021). Масштабируется добавлением агентов БЕЗ изменения существующих (по запросу
пользователя).

**Текущий статус по лестнице:**
- Уровень 1 (Intelligence) ✅ — ADR-021/022.
- Уровень 2 (Reviewer) 🟡 — arch-gate (static), нет системного self-critique.
- Уровень 3 (KB) ✅ — AKB (ADR-022, данные).
- Уровень 4 (Pattern Library) 🟡 — `patterns/allowed.yaml` есть, не structured templates.
- Уровень 5 (Simulator) ❌ — нет digital twin.
- Уровень 6 (Tech Debt) 🟡 — arch-gate частично (import violations), нет TD index.
- Уровень 7 (Evolution) ❌ — нет auto-refactor proposals.
- Уровень 8 (Autonomous) ❌ — нет weekly research sweep.
- Уровень 9 (Benchmark Lab) ❌ — нет auto-benchmark.
- Уровень 10 (AI Chief Architect) ❌ — pipeline не замкнут.
- Research Mesh ❌ — нет специализированных агентов.

---

## 2. Existing Solutions (исследованы)

| Система | Что | Релевантность |
|---|---|---|
| **Anthropic multi-agent research** | Orchestrator-worker; LeadResearcher синтезирует, subagents параллель. +90.2% vs single. | Эталон Research Mesh. Уроки: детальные task-описания (иначе дубли), artifact systems (persist-выводы), deterministic safeguards (retry/checkpoint). |
| **AgentMesh / ChatDev** | Planner/Coder/Debugger/Reviewer роли. | Ролевая специализация. НО «Multi-Agent = Distributed Systems Problem» — координация имеет failure modes (consensus, partial failure). |
| **Automated ADR Generation (arxiv 2604.03826)** | RAG-контекст истории ADR критичен; без retrieval LLM галлюцинирует несуществующие зависимости. | ПРЯМО про Уровень 3: «через 3 года Hermes скажет: обсуждали X 2 года назад». AKB = retrieval source. |
| **Architectural TD Index (ML)** | ATD через architectural smells, coupling, complexity. | Уровень 6 (Tech Debt Engine). |
| **Digital Twin для софта (catio.tech)** | Live queryable model код/db/deps/decisions. Stale twin хуже ничего. Simulation: «if move X → latency/blast-radius». | ПРЯМО про Уровень 5 (Simulator). Анти-паттерн: не обновляемая модель. |
| **Living Architecture (ADR Writer Agent)** | LLM draft+validate ADRs. | Уровень 10 (ADR Generator). |

---

## 3. Engineering Research

- **Anthropic**: subagents нуждаются в objective + output format + tools + boundaries.
  Без этого — дублирование (2 агента искали 2025 supply chain). → KROFT Research
  Agents: каждый получает узкий scope (code/paper/docs/benchmark/security).
- **Anthropic artifact system**: subagents пишут persist-выводы независимо (не через
  lead). → KROFT: каждый Research Agent пишет в AKB/`research/` как artifact.
- **Anthropic deterministic safeguards**: retry + checkpoints. → KROFT Supervisor
  (ADR-021) уже делает recovery; Research Agents под его управлением.
- **arxiv ADR Generation**: «bottleneck — context, not model». RAG-стратегия (RAFG)
  побеждает. → KROFT: Architectural Synthesizer читает AKB (Уровень 3) перед синтезом.
- **Digital Twin**: «model what you decide against; if data doesn't change a decision,
  it doesn't belong in twin». → KROFT Simulator моделирует ТОЛЬКО влияющие метрики
  (deps, latency, memory, risk), не все флаги.
- **Distributed Systems Problem**: multi-agent = consensus/partial failure. → KROFT
  решает через EventBus + Supervisor (уже есть); Research Mesh НЕ изобретает оркестрацию.

---

## 4. Cross-Domain Research

- **Distributed Systems (Lamport/Paxos)**: агенты = узлы; нужен consensus при
  расхождении. KROFT EventBus + Recovery Journal = примитив.
- **Actor Model (Orleans/Akka)**: агенты = virtual actors, location-transparent,
  activation GC. ADR-021 A6 уже предлагает это для компонентов → reuse для агентов.
- **Digital Twin (manufacturing)**: real-time sync или модель устаревает. KROFT
  Simulator должен sync с реальным графом зависимостей (arch-gate output).
- **Recommendation Systems**: TD Engine = ranking по весам (coupling, smells). ML-ATD
  index — но KROFT начнёт с heuristic (graph metrics), не ML (избегаем over-engineering).
- **Crawler/Search (Antlr-style)**: Code Research Agent = AST-crawler проекта (уже
  есть arch-gate AST scan — reuse).

---

## 5. Best Practices

1. **Orchestrator-worker, не плоский** (Anthropic) — LeadResearcher делегирует.
2. **Детальные task-описания** (Anthropic) — иначе дублирование/пропуски.
3. **Artifact systems** (Anthropic) — subagents persist-выводы независимо.
4. **Deterministic safeguards** (Anthropic) — retry/checkpoint (Supervisor).
5. **RAG over ADR history** (arxiv) — контекст критичен, иначе галлюцинации зависимостей.
6. **Digital twin только для decision-affecting данных** (catio) — не моделировать всё.
7. **Stale twin хуже ничего** — Simulator обязан sync с реальностью.
8. **Agents как components** (KROFT LAW K3) — через ComponentRegistry, не ad-hoc.

---

## 6. Common Anti-patterns

1. ❌ **Внешний оркестратор** (отдельный framework) — нарушит LAW K3 (Kernel
   нетронут, но агенты вне runtime). KROFT: агенты = KROFT-компоненты (IAgentPlatform).
2. ❌ **Multi-agent без coordinator failure handling** — partial failure губит синтез.
   KROFT: Supervisor восстанавливает упавшего агента (ADR-021).
3. ❌ **Галлюцинация зависимостей** (arxiv) — без AKB-контекста. → Synthesizer
   читает AKB (Уровень 3) обязательно.
4. ❌ **Stale digital twin** (catio) — Simulator не sync. → Simulator читает arch-gate
   output при каждом запуске.
5. ❌ **ML для TD сразу** — переусложнение. KROFT: heuristic graph metrics (coupling,
   fan-in/out, smells из arch-gate) сначала.
6. ❌ **Один гигантский агент** — теряет параллелизм. → Research Mesh специализированная.

---

## 7. Comparative Table

| Уровень/компонент | Что взять | Что НЕ брать | Почему | Приоритет |
|---|---|---|---|---|
| Research Mesh | Orchestrator-worker (Anthropic) | Внешний framework | KROFT substrate есть | HIGH |
| Research Agents | Специализация (Code/Paper/Docs/Bench/Sec) | Один generic agent | Параллелизм + глубина | HIGH |
| Synthesizer | RAG over AKB (arxiv) | Без контекста | Иначе галлюцинации | HIGH |
| Simulator | Digital twin (catio) decision-affecting | Модель всех флагов | Stale anti-pattern | MED |
| TD Engine | Heuristic graph metrics | ML сразу | Avoid over-engineering | MED |
| Evolution | Auto-refactor proposal | Auto-apply | Risk; human approves | LOW |
| Benchmark Lab | A/B run метрик | — | Уровень 9 | LOW |
| AI Chief Architect | Pipeline (10 уровней) | — | Финальная цель | LOW |

---

## 8. Risks

### 8.1 Research Mesh как distributed system
- **Риск**: partial failure агента ломает синтез. **Митигация**: Supervisor (ADR-021)
  восстанавливает; Synthesizer tolerant к неполным результатам.

### 8.2 Галлюцинация (arxiv)
- **Риск**: агент выдумает зависимость/ADR. **Митигация**: Synthesizer валидирует
  против AKB (Уровень 3) + arch-gate (реальные импорты).

### 8.3 Stale Simulator (catio)
- **Риск**: Simulator показывает устаревший граф. **Митигация**: читает arch-gate
  output при каждом run; помечается `stale` если граф менялся.

### 8.4 TD Engine ложные срабатывания
- **Риск**: 1 год — ложные «18 dependencies». **Митигация**: threshold + whitelist
  (намеренные hub-модули типа contracts).

### 8.5 Over-engineering (Уровни 8–10 рано)
- **Риск**: строим Benchmark Lab до Simulator. **Митигация**: последовательно
  (Уровень 5 → 6 → 7 → 8 → 9 → 10).

### 8.6 LAW K8 нарушение (агенты в runtime)
- **Риск**: Research Agent импортирует services в runtime. **Митигация**: агенты —
  компоненты в `services/` или `plugins/`, НЕ runtime/; реализуют IAgentPlatform.

---

## 9. Architecture Proposal (синтез)

**Принцип**: Research Mesh = KROFT-нативные агенты (компоненты), управляемые
Supervisor, общающиеся через EventBus, синтезирующие через AKB-контекст. НЕ
внешний оркестратор (LAW K3/K8).

### 9.1 Agent Topology (Research Mesh)
```
ArchitectureLeadResearcher (оркестратор, IAgentPlatform)
 ├── CodeResearchAgent      (GitHub + исходники проекта; AST-crawl reuse arch-gate)
 ├── PaperResearchAgent     (arxiv/RFC/ADR; web_extract)
 ├── DocsResearchAgent      (офиц. документация/API; web_extract)
 ├── BenchmarkAgent         (сравнение perf; pytest-benchmark)
 ├── SecurityResearchAgent  (CVE/ADR-security; web_search)
 └── ArchitectureSynthesizer (читает AKB + выводы агентов → единое предложение)
```
Каждый агент = компонент (ComponentRegistry), virtual actor (Orleans, ADR-021 A6),
под Supervisor (recovery при падении). Synthesizer НЕ фильтрует через lead — пишет
artifact в `research/` (Anthropic artifact system).

### 9.2 Уровни как evolution roadmap (НЕ всё сразу)
- **L4 Pattern Library**: `pattern_library.yaml` (structured templates: Supervisor,
  Plugin, Repository, Actor, Pipeline, Recovery, Scheduler, Workflow, Memory) —
  расширение `patterns/allowed.yaml` из AKB.
- **L5 Simulator**: `architecture_simulator` (читает arch-gate граф → what-if:
  +deps, +imports, +cycles, latency/memory estimate, risk). Digital twin, sync при run.
- **L6 Tech Debt Engine**: graph metrics (coupling, fan-in/out, smells из arch-gate)
  → TD rating + report. Heuristic сначала.
- **L7 Evolution Engine**: сравнивает текущий паттерн с новыми знаниями (AKB/Research
  Mesh) → предлагает рефакторинг (человек approves, НЕ auto-apply).
- **L8 Autonomous Architect**: cron/periodic Research Mesh sweep → weekly report.
- **L9 Benchmark Lab**: A/B реализаций через BenchmarkAgent → рекомендация победителя.
- **L10 AI Chief Architect**: конвейер 10 уровней замкнут (Idea→…→KB Update).

### 9.3 Интеграция с существующим
- EventBus: агенты publish `research.finding`, `sim.result`, `debt.report`.
- AKB: Synthesizer читает `adrs.yaml`/`laws.yaml` (Уровень 3) — убирает галлюцинации.
- Supervisor (ADR-021): управляет агентами как components (recovery).
- arch-gate: источник Ground Truth для Simulator/Debt Engine (реальные импорты).

---

## 10. ADR Draft (023)

**Title**: Architecture Agent Hierarchy (10 levels) & Research Mesh
**Status**: Proposed (research synthesis; realization — поэтапно, НЕ код здесь)
**Decision**:
1. Research Mesh = KROFT-нативные агенты (IAgentPlatform + ComponentRegistry +
   Supervisor + EventBus), НЕ внешний framework.
2. Synthesizer обязан читать AKB (Уровень 3) перед синтезом (anti-hallucination).
3. Simulator = digital twin, sync с arch-gate при каждом run (anti-stale).
4. TD Engine = heuristic graph metrics сначала (НЕ ML).
5. Evolution Engine предлагает, НЕ применяет (human approve).
6. Уровни 1–3 уже есть; 4–10 = evolution roadmap последовательно.
**Consequences**:
- ✅ Reuse KROFT substrate (Kernel/Registry/Supervisor/Bus/AKB) — минимум нового кода.
- ✅ Масштабируется добавлением агентов (без изменения существующих).
- ✅ RAG over AKB убирает галлюцинации зависимостей (arxiv-доказано).
- ⚠️ Multi-agent = distributed systems problem; нужен Supervisor-recovery.
- ⚠️ Over-engineering риск (L8–10 рано) — последовательно.
- LAW K3/K8 соблюдены: агенты в services/plugins, НЕ runtime/; Kernel нетронут.

---

## 11. Recommended Interfaces

Новые порты (в `contracts/`, как IAgentPlatform):
```python
# contracts/i_research_mesh.py (НОВЫЙ)
@runtime_checkable
class IResearchAgent(Protocol):       # specializes IAgentPlatform
    domain: str                        # code|paper|docs|benchmark|security
    def research(self, query: str) -> "ResearchArtifact": ...

@runtime_checkable
class IArchitectureSynthesizer(Protocol):
    def synthesize(self, artifacts: List["ResearchArtifact"],
                   kb: "AKBSnapshot") -> "ArchitectureProposal": ...

# contracts/i_simulator.py (НОВЫЙ, для L5)
@runtime_checkable
class IArchitectureSimulator(Protocol):
    def what_if(self, change: "ProposedChange") -> "ImpactReport": ...
    # ImpactReport: +deps, +imports, +cycles, latency_est, memory_est, risk
```

**Стабильные**: `IAgentPlatform` (уже есть), `IResearchAgent` (специализация).
**Расширяемые**: Research Mesh добавляет агентов без изменения Synthesizer (port-based).
**Заменяемые**: agent backend (mock LLM / OmniRoute / внешний) через IAgentPlatform.

---

## 12. Future Evolution

- **Рост**: новые Research Agents (LegalAgent, ComplianceAgent) добавляются как
  компоненты — Synthesizer не меняется (port-based).
- **Стабильные**: `IAgentPlatform`, `IResearchAgent`, `IArchitectureSynthesizer`.
- **Расширяемое**: Pattern Library (L4), Simulator metrics (L5), TD weights (L6).
- **Plugin-based**: каждый агент = plugin (manifest), активируется по запросу (A6).
- **Phase 8 (multi-node)**: агенты распределяются через `ICoordinator` (ADR-021);
  Synthesizer консолидирует распределённые finding'и.
- **L10**: конвейер замкнут — каждый ADR пополняет AKB (Knowledge Base Update).

---

## 13. Implementation Plan (фазы, не код)

| Фаза | Что | LAW | DoD |
|---|---|---|---|
| L4 | `pattern_library.yaml` (9 шаблонов) + Hermes предлагает при новом модуле | K8 | structured templates в AKB |
| RM-1 | `IResearchAgent` + `CodeResearchAgent` (AST-crawl reuse arch-gate) | K3 | агент компонент, читает проект |
| RM-2 | `PaperResearchAgent` + `DocsResearchAgent` (web_extract) | K8 | параллельный поиск |
| RM-3 | `ArchitectureSynthesizer` читает AKB + artifacts → proposal | K3 | RAG over AKB, нет галлюцинаций |
| RM-4 | `ArchitectureLeadResearcher` оркестрирует (IAgentPlatform) | K3 | weekly sweep report |
| L5 | `architecture_simulator` (what-if, sync arch-gate) | K8 | +deps/+cycles/latency estimate |
| L6 | TD Engine (graph metrics → rating) | K8 | report: coupling/fan-out/smells |
| L7 | Evolution Engine (propose refactor) | K3 | human-approved proposal |
| L8 | Autonomous sweep (cron) | K3 | weekly research report |
| L9 | Benchmark Lab (A/B) | K8 | победитель по метрикам |
| L10 | Pipeline замкнут (10 уровней) | — | Idea→KB Update |

Каждая фаза — atomic commit (как Phases 1–6).

---

## 14. Testing Strategy

- **RM**: агент возвращает `ResearchArtifact` (deterministic на mock data).
- **Synthesizer**: negative test — без AKB-контекста → флаг `hallucination_risk`.
- **Simulator**: negative test — stale graph → помечается `stale`.
- **TD Engine**: известный «hub module» (contracts) → НЕ ложный positive (whitelist).
- **Regression**: остаётся 0 failures (Phases 1–6).

---

## 15. Honest Assessment

**Почему это лучше внешнего фреймворка?**
Anthropic/ChatDev доказали: multi-agent нужен, НО coordination = distributed systems
problem. KROFT УЖЕ решает это (Supervisor + EventBus + Recovery Journal). Внешний
оркестратор (LangGraph и т.п.) нарушил бы LAW K3 (Kernel нетронут) и дублировал бы
существующее. Research Mesh КАК KROFT-компоненты — reuse, не reinvent.

**Что может оказаться ошибкой?**
- Over-engineering: строим L9 Benchmarks до L5 Simulator. → Последовательно по плану.
- Галлюцинации агентов (arxiv). → Synthesizer RAG over AKB + arch-gate validation.

**Что бы изменил архитектор Anthropic?**
Сделал бы task-описания агентов максимально детальными (domain boundary). → KROFT:
каждый Research Agent имеет узкий scope (code/paper/docs/bench/sec).

**Что бы изменил архитектор Digital Twin (catio)?**
Simulator обязан sync с реальностью (stale хуже ничего). → KROFT: читает arch-gate
при каждом run.

**Что бы изменил архитектор arxiv ADR?**
Контекст истории ADR критичен для quality. → KROFT: AKB = retrieval source для
Synthesizer (именно твой Уровень 3 «через 3 года Hermes вспомнит»).

**Можно ли проще?**
Да — L4 (pattern_library.yaml) + RM-1..3 (3 агента + synthesizer) дают 70% ценности
(Intelligence+Review+KB+Mesh). L5–L10 — evolution.

**Можно ли модульнее?**
Да — каждый агент = компонент (port-based); добавляется без изменения Synthesizer.

**Можно ли уменьшить связанность?**
LAW K8: агенты в services/plugins, НЕ runtime/. Synthesizer читает AKB (docs, вне
runtime). Supervisor (runtime) управляет агентами через IComponentController — связь
минимальна.

**Вердикт**: синтез честен, опирается на 6 индустриальных прецедентов, НЕ копирует
реализации (Anthropic-оркестратор не берём как внешний; берём паттерны), соблюдает
LAW K1–K8. KROFT substrate делает Research Mesh реалистичным без нарушения границ.
Рекомендуется к принятию как ADR-023 и поэтапной реализации (L4 → RM-1..4 → L5 → L6 →
L7 → L8 → L9 → L10). Код НЕ писался (Уровень 1 Intelligence).

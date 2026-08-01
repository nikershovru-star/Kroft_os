---
tags: [kroft, meta-architecture-engine, engineering-intelligence-platform, adr-024, level-1-intelligence, eip, levels-11-18]
created: 2026-08-01
author: Hermes (Research Architect)
protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0 (Уровень 1 — Intelligence для темы "L11–L18 + Engineering Intelligence Platform")
depends_on: [ADR-021 Runtime Evolution, ADR-022 Architecture Knowledge Base, ADR-023 Architecture Agent Hierarchy & Research Mesh, ADR-020 Runtime Host, ADR-014 Agent Platform, docs/architecture/akb/]
summary: >-
  Синтез Уровней 11–18 (Meta Architecture Engine → Autonomous CTO) + Engineering
  Intelligence Platform (4 контура: Research/Architecture/Implementation/Learning).
  Исследованы: ADR-E (org memory = why not what), AgentRxiv (continuous research
  archive), ML TD forecasting (Sculley warning: ML сам добавляет долг), copilot-
  instructions.md (ADR-driven PR governance), HyperAgents/Gödel (self-improving, НО
  runaway-risk → human-in-the-loop). КЛЮЧЕВОЙ инсайт: L11–L18 = research/strategy
  targets, НЕ runtime-фичи. EIP = meta-layer ПОВЕРХ KROFT (использует IAgentPlatform/
  EventBus/AKB как substrate), живёт ВНЕ runtime (LAW K8). KROFT kernel остаётся
  минимальным. Код НЕ пишется (Уровень 1).
---

# ADR-024 — Meta Architecture Engine (L11–L18) & Engineering Intelligence Platform

> Protocol: HERMES ARCHITECTURE INTELLIGENCE PROTOCOL v2.0 — Уровень 1 (Intelligence)
> Topic: Уровни 11–18 + EIP (предложено пользователем).
> Date: 2026-08-01. Scope: research + synthesis. **No code in this ADR.**

---

## 1. Executive Summary

Пользователь расширяет 10-уровневую лестницу до **18 уровней** + **Engineering
Intelligence Platform (EIP)** с 4 контурами (Research / Architecture / Implementation
/ Learning). Финальная цель — **Autonomous CTO** с замкнутым конвейером.

**Критический архитектурный инсайт (честный):** L11–L18 и EIP — это **meta-layer
ПОВЕРХ KROFT**, НЕ часть KROFT runtime. KROFT runtime (Kernel + runtime/) НЕ должен
эмулировать LLM-рассуждение (LAW K8: runtime = contracts + stdlib only). Архитектурный
интеллект живёт ВНЕ runtime: в Hermes (вне кода), в AKB (docs/), и в Research Mesh
agents (компоненты в services/, реализующие IAgentPlatform). KROFT runtime остаётся
минимальным ядром; EIP использует его КАК substrate (как Kubernetes плоский, а Helm/
Argo/Prometheus живут рядом).

**Текущий статус (расширенная лестница):**
- L1 Intelligence ✅ (ADR-021/022) · L2 Reviewer 🟡 · L3 KB ✅ (AKB) · L4 Pattern Lib 🟡
- L5 Simulator ❌ · L6 TD Engine 🟡 · L7 Evolution ❌ · L8 Autonomous ❌ · L9 Benchmark ❌
- L10 AI Chief Architect ❌
- **L11 Meta Architecture Engine ❌** · L12 Governance 🟡 (arch-gate есть) · L13 Continuous Research ❌
- L14 Forecasting ❌ · L15 Experiment Engine ❌ · L16 Self-Improving ❌ · L17 Org Memory 🟡 (AKB частично) · L18 Autonomous CTO ❌
- **EIP (4 контура) ❌** — но substrate (IAgentPlatform/EventBus/AKB) есть.

---

## 2. Existing Solutions (исследованы)

| Система | Что | Релевантность |
|---|---|---|
| **ADR-E framework** | ADR хранит explicit rationale + alternatives + traceability. «Architectural memory = why, not what». | Уровень 17 (Org Memory). KROFT AKB должен хранить alternatives/who/mistakes/review_trigger. |
| **AgentRxiv** | Autonomous agents публикуют research outputs в shared archive; collaborative. | Уровень 13 (Continuous Research) = Research Mesh как service + archive. |
| **ML TD Forecasting** | Supervised ML предсказывает TD по метрикам. | Уровень 14 (Forecasting). НО Sculley: «ML = high-interest credit card of TD» — ML сам добавляет долг. |
| **copilot-instructions.md** | AI reviewer получает ADRs как инструкции, флагует нарушения на КАЖДОМ PR. | Уровень 12 (Governance) = AKB-driven PR review. У нас arch-gate в pytest. |
| **HyperAgents / Gödel Agent** | Self-improving meta-learning, self-referential recursion. | Уровень 16 (Self-Improving). НО Gödel warning: meta-meta-learning → runaway risk; нужен human-in-the-loop. |

---

## 3. Engineering Research

- **ADR-E**: traceability links = unitary building blocks for reliable decisions. →
  KROFT AKB: каждый ADR связан с LAW + ports + relates_to (уже есть в adrs.yaml).
  Добавить: `alternatives` (отвергнутые), `who_proposed`, `mistakes`, `review_trigger`.
- **AgentRxiv**: archive как shared memory для агентов. → KROFT: Research Mesh пишет
  artifacts в `research/` (Anthropic artifact system, ADR-023), читаемые всеми агентами.
- **Sculley TD warning**: ML-модель предсказания долга САМА добавляет долг (maintenance
  модели, data drift). → KROFT Forecasting (L14) начинает С heuristic (graph metrics,
  trend из history.yaml), ML — только если heuristic исчерпан.
- **copilot-instructions.md**: «ADR is the authority, not the person». → KROFT
  Governance (L12): AKB laws.yaml = authority; PR-check (расширение arch-gate) флагует
  нарушение K1–K8 до merge.
- **Gödel Agent**: self-referential recursion рискует runaway. → KROFT Self-Improving
  (L16): Hermes улучшает Research Mesh strategy, НО под human approve (LAW K5/K7:
  apply требует approve, atomic commits).

---

## 4. Cross-Domain Research

- **Org Memory (product mgmt)**: ADR как decision log, переживающий turnover. KROFT:
  AKB history.yaml + adrs.yaml = org memory; расширить до полной аргументации (L17).
- **Control Theory (feedback loops)**: EIP 4 контура = 4 feedback loops. Architecture
  Loop стабилизирует систему; Learning Loop улучшает контроллер (Hermes). Nielsen:
  «improvement needs measurement» → Experiment Engine (L15) = measurement.
- **Kaizen (continuous improvement)**: L16 Self-Improving = org-level kaizen. Но
  bounded by human priors (Gödel) → human-in-the-loop.
- **Financial forecasting**: L14 = technical debt как финансовый риск. Heuristic trend
  (история коммитов) точнее ML на малых данных.

---

## 5. Best Practices

1. **ADR = why, not what** (ADR-E) — Org Memory хранит аргументацию, не итог.
2. **Research as service + archive** (AgentRxiv) — не ручной запуск, shared memory.
3. **Heuristic before ML** (Sculley) — ML добавляет долг; начинаем с graph metrics.
4. **ADR as PR authority** (copilot-instructions) — governance автоматически на PR.
5. **Human-in-the-loop для self-improvement** (Gödel) — мета-обучение bounded.
6. **EIP = meta-layer, НЕ runtime** — KROFT kernel минимален (LAW K8).
7. **4 контура как feedback loops** — measurement (L15) замыкает Learning Loop.

---

## 6. Common Anti-patterns

1. ❌ **EIP в runtime** — эмуляция LLM-рассуждения в KROFT kernel нарушит LAW K8.
   → EIP живёт в Hermes + agents (services/), НЕ runtime/.
2. ❌ **ML для forecasting сразу** (Sculley) — модель сама = долг. → Heuristic + trend.
3. ❌ **Self-improvement без boundary** (Gödel) — runaway. → Human approve (LAW K5/K7).
4. ❌ **Org Memory только итог ADR** — теряется аргументация. → AKB хранит alternatives/
   who/mistakes/review_trigger (ADR-E).
5. ❌ **Continuous Research без archive** — агенты дублируют поиск. → Shared archive
   (AgentRxiv-паттерн) в `research/`.
6. ❌ **Governance как документ** — не enforcement. → AKB laws.yaml + PR-check (L12).

---

## 7. Comparative Table

| Уровень/контур | Что взять | Что НЕ брать | Почему | Приоритет |
|---|---|---|---|---|
| L11 Meta Engine | Анализ устаревших LAW/ADR/интерфейсов | Переписывание ядра | KROFT substrate достаточно | MED |
| L12 Governance | AKB-driven PR review (copilot-trick) | Ручной review | Авто на каждом PR | HIGH |
| L13 Continuous Research | Research Mesh as service + archive | Ручной запуск | AgentRxiv-паттерн | MED |
| L14 Forecasting | Heuristic trend (history.yaml) | ML сразу | Sculley warning | LOW |
| L15 Experiment Engine | A/B реализаций (BenchmarkAgent) | — | Measurement closes loop | LOW |
| L16 Self-Improving | Hermes improves Mesh (human approve) | Auto-apply | Gödel runaway | LOW |
| L17 Org Memory | AKB: alternatives/who/mistakes | Только итог ADR | ADR-E | HIGH |
| L18 Autonomous CTO | Pipeline замкнут | — | Финал | LOW |
| EIP | 4 контурa feedback loops | EIP в runtime | LAW K8 | HIGH |

---

## 8. Risks

### 8.1 EIP в runtime (LAW K8 нарушение)
- **Риск**: кто-то пишет ReasoningEngine в runtime/. **Митигация**: EIP = Hermes +
  agents (services/); arch-gate блокирует runtime→services импорт (F4).

### 8.2 ML Forecasting долг (Sculley)
- **Риск**: модель предсказания устаревает, требует переобучения. **Митигация**:
  heuristic (graph trend из history.yaml) сначала; ML — опционально, поздно.

### 8.3 Self-Improving runaway (Gödel)
- **Риск**: Hermes меняет собственный процесс → нестабильность. **Митигация**:
  изменения процесса требуют human approve (LAW K5/K7) + atomic commit + AKB log.

### 8.4 Org Memory рассинхрон с ADR
- **Риск**: AKB хранит alternatives, но ADR-md их не содержит. **Митигация**:
  ADR-E шаблон (KROFT ADR = include alternatives/who/mistakes); AKB зеркалит.

### 8.5 Over-engineering (L11–L18 рано)
- **Риск**: строим Autonomous CTO до Simulator. **Митигация**: последовательно
  L4→RM→L5→L6→L7→L8→L9→L10→L11→L12→L13→L14→L15→L16→L17→L18.

---

## 9. Architecture Proposal (синтез)

**Принцип**: EIP = meta-layer поверх KROFT. KROFT runtime минимален (LAW K8). EIP
использует KROFT substrate: IAgentPlatform (agents), EventBus (меж-контурная связь),
AKB (knowledge + governance authority). 4 контура — независимые feedback loops.

### 9.1 Уровни как maturity roadmap (НЕ всё сразу)
- **L11 Meta Engine**: анализирует AKB (laws.yaml/adrs.yaml) на устаревшие законы/
  интерфейсы (через Hermes + Synthesizer). Propose per-review, НЕ auto-apply.
- **L12 Governance**: расширение arch-gate → PR-check (читает laws.yaml, блокирует
  K1–K8 violation до merge). AKB = authority (copilot-trick).
- **L13 Continuous Research**: Research Mesh (ADR-023 RM-1..4) как service (cron) +
  shared archive `research/` (AgentRxiv).
- **L14 Forecasting**: heuristic trend из history.yaml + graph metrics (fan-in/out
  growth) → «X станет bottleneck через N версий». ML — поздно (Sculley).
- **L15 Experiment Engine**: BenchmarkAgent (ADR-023 L9) собирает A/B, меряет, пишет
  в AKB (Learning Loop).
- **L16 Self-Improving**: Hermes анализирует эффективность Research Mesh (какие агенты
  лишние, какой поиск лучше) → меняет strategy (human approve, LAW K5).
- **L17 Org Memory**: AKB расширяет ADR-схему: `alternatives`, `who_proposed`,
  `mistakes`, `review_trigger`. «Почему Supervisor?» → вся аргументация (ADR-E).
- **L18 Autonomous CTO**: конвейер 18 уровней замкнут (Idea→…→Meta Engine).

### 9.2 Engineering Intelligence Platform (4 контура)
```
Research Loop      → Research Mesh (RM-1..4) → AKB (knowledge)
Architecture Loop  → Reviewer + Simulator + Risk Engine → ADR Generator
Implementation Loop→ Code Gen + Testing + Refactor → Production
Learning Loop      → Experiment Engine + Org Memory + Meta Engine → AKB Update
```
Контуры связаны EventBus: `research.finding` → Architecture Loop; `adr.draft` →
Implementation; `experiment.result` → Learning → `akb.update`. KROFT EventBus (ADR-003)
уже есть — reuse.

### 9.3 Граница (честно)
- **В runtime (LAW K8)**: Kernel, ComponentRegistry, Supervisor, EventBus, services
  (вкл. Research Agents как IAgentPlatform impls). НИКАКОГО reasoning/LLM-loop.
- **Вне runtime (EIP)**: Hermes (orchestrator), AKB (docs/), Research Mesh strategy,
  Forecasting/Experiment logic. Это Python/LLM вне KROFT packages (или в services/ как
  компоненты через IAgentPlatform — НЕ в runtime/).

---

## 10. ADR Draft (024)

**Title**: Meta Architecture Engine (L11–L18) & Engineering Intelligence Platform
**Status**: Proposed (research synthesis; realization — поэтапно, НЕ код здесь)
**Decision**:
1. EIP = meta-layer поверх KROFT; KROFT runtime минимален (LAW K8). EIP живёт в Hermes
   + agents (services/), НЕ runtime/.
2. L12 Governance = AKB-driven PR-check (расширение arch-gate, читает laws.yaml).
3. L17 Org Memory = AKB хранит alternatives/who/mistakes/review_trigger (ADR-E).
4. L14 Forecasting = heuristic + trend (history.yaml); ML — поздно (Sculley).
5. L16 Self-Improving = human approve (LAW K5/K7); no runaway (Gödel).
6. L13 Continuous Research = Research Mesh as service + shared archive (AgentRxiv).
**Consequences**:
- ✅ Reuse KROFT substrate (IAgentPlatform/EventBus/AKB) — минимум нового.
- ✅ EIP не раздувает runtime (LAW K8 соблюдён).
- ✅ Org Memory = ADR-E (why not what) — переживает turnover.
- ⚠️ Multi-loop coordination = distributed systems problem (как ADR-023) — Supervisor.
- ⚠️ Over-engineering риск (L11–L18 рано) — последовательно.
- LAW K3/K8 соблюдены: EIP вне runtime; агенты в services/.

---

## 11. Recommended Interfaces

Новые порты (contracts/, как IAgentPlatform — для EIP agents):
```python
# contracts/i_meta_architecture.py (НОВЫЙ, для L11/L16)
@runtime_checkable
class IMetaArchitectureEngine(Protocol):
    def review_laws(self, kb: "AKBSnapshot") -> List["LawVerdict"]: ...  # устаревший?
    def propose_evolution(self, kb: "AKBSnapshot") -> List["EvolutionProposal"]: ...

# contracts/i_governance.py (НОВЫЙ, для L12)
@runtime_checkable
class IArchitectureGovernor(Protocol):
    def check_pr(self, diff: "CodeDiff") -> List["Violation"]: ...  # читает laws.yaml
```
**Стабильные**: `IAgentPlatform` (уже есть) — база для всех EIP-агентов.
**Расширяемые**: Research Mesh агенты (ADR-023), Governance/Experiment агенты.
**Заменяемые**: agent backend (mock/OmniRoute/внешний) через IAgentPlatform.

---

## 12. Future Evolution

- **Рост**: новые EIP-агенты (LegalAgent, ComplianceAgent) = компоненты (port-based).
- **Стабильные**: `IAgentPlatform`, `IMetaArchitectureEngine`, `IArchitectureGovernor`.
- **Расширяемое**: AKB схема (Org Memory поля), Forecasting heuristics, Learning Loop.
- **Plugin-based**: каждый EIP-агент = plugin (manifest), активируется по запросу.
- **Phase 8 (multi-node)**: EIP контура распределяются через ICoordinator (ADR-021);
  Research archive (AgentRxiv) = shared distributed store.
- **L18**: конвейер замкнут — каждый ADR пополняет AKB (Knowledge Base Update).

---

## 13. Implementation Plan (фазы, не код)

| Фаза | Что | LAW | DoD |
|---|---|---|---|
| L12 | AKB-driven PR-check (arch-gate читает laws.yaml) | K8 | PR блокируется при K1–K8 violation |
| L17 | AKB Org Memory: alternatives/who/mistakes/review_trigger | K8 | ADR-E схема в adrs.yaml |
| RM (ADR-023) | Research Mesh agents + Synthesizer | K3 | weekly research report |
| L13 | Research Mesh as service + archive (AgentRxiv) | K3 | continuous, shared memory |
| L11 | Meta Engine: review устаревших LAW/ADR | K3 | propose, НЕ apply |
| L14 | Forecasting: heuristic trend | K8 | «X bottleneck через N версий» |
| L15 | Experiment Engine: A/B + BenchmarkAgent | K8 | результаты в AKB |
| L16 | Self-Improving: Hermes improves Mesh (approve) | K5 | strategy-change logged |
| L18 | Pipeline замкнут (18 уровней) | — | Idea→Meta Engine |

Каждая фаза — atomic commit (как Phases 1–6).

---

## 14. Testing Strategy

- **L12**: negative PR-diff (runtime→services импорт) → Governor блокирует.
- **L17**: ADR без alternatives → Org Memory validator флагует.
- **L14**: известный растущий hub → heuristic предсказывает bottleneck.
- **L16**: self-improvement без approve → блокируется (LAW K5).
- **Regression**: остаётся 0 failures (Phases 1–6).

---

## 15. Honest Assessment

**Почему это лучше «просто ещё уровни»?**
Ты выделил EIP (4 контура) — это правильная декомпозиция: Research/Architecture/
Implementation/Learning как независимые feedback loops. KROFT EventBus уже связывает
их. Без EIP уровни 11–18 были бы плоским списком; с EIP — это живая система.

**Что может оказаться ошибкой?**
- **EIP в runtime** (LAW K8) — самая большая опасность. Если кто-то напишет
  ReasoningEngine в runtime/, ядро раздуется и потеряет минимальность (ADR-020 вариант б).
  → Зафиксировано: EIP вне runtime, арх-gate (F4) блокирует.
- **ML для forecasting** (Sculley) — модель сама = долг. → Heuristic.
- **Runaway self-improvement** (Gödel) — мета-обучение без boundary. → Human approve.

**Что бы изменил архитектор ADR-E?**
Org Memory хранил бы не только итог, но ВСЮ аргументацию (alternatives, who, mistakes).
→ KROFT: AKB adrs.yaml расширен полями (L17). Именно твой «почему Supervisor?» →
вся история.

**Что бы изменил архитектор AgentRxiv?**
Research Mesh писал бы в shared archive, читаемый всеми агентами (не дублирование).
→ KROFT: `research/` как AgentRxiv (L13).

**Что бы изменил архитектор copilot-instructions?**
ADR = authority на КАЖДОМ PR. → KROFT: AKB laws.yaml = PR-check authority (L12).

**Можно ли проще?**
Да — L12 (PR-check) + L17 (Org Memory поля) дают 60% ценности (governance + memory)
без ML/self-improving. L13–L16 — evolution.

**Можно ли модульнее?**
Да — каждый EIP-агент = компонент (IAgentPlatform); добавляется без изменения ядра.

**Можно ли уменьшить связанность?**
LAW K8: EIP вне runtime. Learning Loop пишет в AKB (docs), НЕ в kernel. Связь минимальна.

**Вердикт**: синтез честен, опирается на 6 индустриальных прецедентов, НЕ копирует
реализации (copilot-trick берём как паттерн, НЕ как GitHub-зависимость). Ключевая
граница зафиксирована: **EIP = meta-layer поверх KROFT, НЕ часть runtime** (LAW K8).
Рекомендуется к принятию как ADR-024 и поэтапной реализации (L12 → L17 → RM → L13 →
L11 → L14 → L15 → L16 → L18). Код НЕ писался (Уровень 1 Intelligence).

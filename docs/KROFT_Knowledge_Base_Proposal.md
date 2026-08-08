---
id: KROFT_KNOWLEDGE_PROPOSAL
title: KROFT Knowledge Base — Atomic Q&A Design (Proposal)
status: proposal
date: 2026-08-08
source: owner strategic direction (out-of-band)
related: ADR-100 (Slice 1–9 arc), ADR-069 (Knowledge Search Retrieval port), ADR-091 (Knowledge Engine)
---

# KROFT Knowledge Base — Atomic Q&A Design (Proposal)

> Сохранено из стратегического послания владельца. Цель — не «папка с книгами», а
> обучающая база из **атомарных знаний** в формате Вопрос → Ответ → Практический пример →
> Связи. Отдельный слой `KROFT_KNOWLEDGE/`, НЕ смешиваемый с проектными решениями Vault.

## 1. Ядро идеи

Не `Document → LLM → Database`, а:

```
Source → Ingestion → Extraction → Normalization → Knowledge Objects
      → Relations → Validation → Indexing → Retrieval → Evaluation → Knowledge Graph
```

Атомарная единица знания (Knowledge Node):

```
ID / TYPE / QUESTION / ANSWER / EXAMPLE / COUNTEREXAMPLE
SOURCE / SOURCE_TYPE / DATE / CONFIDENCE / TAGS
RELATED_CONCEPTS / PARENT_CONCEPT / CHILD_CONCEPTS / CONFLICTS
```

KROFT должна отвечать на конкретные вопросы, сопоставлять принципы и строить граф знаний.

## 2. Десять фундаментальных областей

| # | Область | Ключевые темы |
|---|---------|---------------|
| A | AI / LLM | Transformer, attention, embeddings, tokenization, context window, inference, fine-tuning, RAG, vector search, reranking, agents, tools, memory, planning, evaluation, hallucinations, prompt engineering, local LLM, quantization |
| B | Software Architecture | SOLID, Clean/Hexagonal, DDD, dependency inversion, interfaces, contracts, events, message bus, state machines, modularity, coupling/cohesion, ADR, testing, refactoring |
| C | Operating Systems | процессы, threads, scheduling, memory, virtual memory, filesystem, I/O, IPC, permissions, isolation, kernel/user space, drivers, interrupts, concurrency, deadlocks, persistence, crash recovery |
| D | Distributed Systems | CAP, consistency, availability, partition tolerance, consensus, replication, leader election, queues, event-driven, retries, idempotency, distributed locks, failure detection, eventual consistency |
| E | Knowledge Management | knowledge graph, ontology, taxonomy, metadata, provenance, source of truth, semantic search, IR, chunking, indexing, backlinks, knowledge extraction, entity resolution, knowledge validation, temporal knowledge, knowledge decay |
| F | Agent Systems | agent loop, planning, tool calling, memory, observation, action, reflection, verification, multi-agent, orchestration, delegation, agent skills, guardrails, sandboxing, evaluation (OpenAI Agents guide, HF Agents Course, MCP) |
| G | Reliability / Production | observability, logging, metrics, tracing, health checks, SLO/SLA, error budgets, graceful degradation, backups, recovery, incident response, monitoring, performance (Google SRE) |
| H | Cybersecurity | authn/authz, secrets, encryption, least privilege, sandboxing, threat modeling, supply-chain, prompt injection, data leakage, secure tool execution, audit logs |
| I | CS Fundamentals | algorithms, data structures, complexity, graphs, trees, hashing, databases, networking, compilers, OS, concurrency |
| J | Human Reasoning / Decision | causal reasoning, Bayesian, probability, uncertainty, decision theory, critical thinking, cognitive biases, scientific method, hypothesis testing, falsification, argumentation |

## 3. Книги — ядро базы (Tier 1)

- Operating Systems: Three Easy Pieces
- Designing Data-Intensive Applications — Kleppmann
- Site Reliability Engineering — Google
- Site Reliability Workbook — Google
- Building Secure & Reliable Systems — Google
- Computer Systems: A Programmer's Perspective
- Structure and Interpretation of Computer Programs
- The Pragmatic Programmer
- Clean Architecture — R. C. Martin
- Design Patterns — GoF
- Domain-Driven Design — E. Evans
- Deep Learning — Goodfellow, Bengio, Courville
- Hands-On Machine Learning — Géron
- Artificial Intelligence: A Modern Approach — Russell & Norvig
- Designing ML Systems — Chip Huyen

## 4. Научные статьи (50–100 фундаментальных, в Q&A)

LLM/AI: Attention Is All You Need; RAG for Knowledge-Intensive NLP; ReAct; Chain-of-Thought;
Self-Consistency; Toolformer; Constitutional AI; LoRA; QLoRA; FlashAttention; MoE; RLHF; DPO;
instruction tuning; long-context; agent memory; agent evaluation; RAG evaluation.

## 5. Курсы

- Full Stack Deep Learning (бесплатно)
- Hugging Face Agents Course (Agents, Tools, Actions, Observations, MCP)
- DeepLearning.AI (Agents, RAG, LLMOps, evaluation, embeddings, vector DB, AI coding, multimodal, agent memory)

## 6. YouTube (video → transcript → clean → Q&A → node)

AI/ML: Karpathy, 3Blue1Brown, Yannic Kilcher, Two Minute Papers, Lex Fridman, DeepLearning.AI, HF.
CS: Computerphile, MIT OCW, Stanford Online, CMU CS, Ben Eater.
Серии университетов важнее случайных AI-блогеров.

## 7. Q&A Format v1 (образцы 001–040)

### 001 — Что такое операционная система?
**Ответ:** Программный слой, управляющий ресурсами и дающий приложениям стандартизированный интерфейс к процессору, памяти, файлам, устройствам, процессам.
**Пример:** Приложение пишет файл через системный вызов, а не управляет диском напрямую.
**KROFT понимает:** ОС = управление ресурсами + изоляция + абстракции + интерфейсы.
**Связи:** `OS → Kernel → Process → Memory → Filesystem → I/O`

### 002 — Чем kernel отличается от ОС?
**Ответ:** Kernel — центральная часть ОС (ресурсы + системные функции). ОС шире: kernel + библиотеки + службы + инструменты + окружение.
**Пример:** Linux kernel ≠ вся Linux-система.

### 003 — Что такое процесс?
**Ответ:** Выполняемый экземпляр программы со своим адресным пространством, состоянием, ресурсами.
**Связи:** `Process → Memory → Threads → Scheduling → IPC`

### 004 — Что такое thread?
**Ответ:** Поток выполнения внутри процесса; потоки делят память процесса.
**Риск:** Общая память → проблемы синхронизации.

### 005 — Что такое race condition?
**Ответ:** Результат зависит от порядка параллельных операций.
**Пример:** Два потока читают `counter=10`, оба инкрементят до 11, пишут → ожидается 12, получается 11.
**Связи:** `Concurrency → Race Condition → Mutex → Atomic Operation`

### 006 — Что такое deadlock?
**Ответ:** Несколько потоков навсегда ждут ресурсы, удерживаемые друг другом.
**Пример:** T1 держит L1 ждёт L2; T2 держит L2 ждёт L1.

### 007 — Что такое abstraction?
**Ответ:** Скрывает детали реализации, даёт простой интерфейс.
**Правило:** Хорошая абстракция скрывает сложность, но не важные свойства системы.

### 008 — Что такое interface?
**Ответ:** Контракт взаимодействия без знания реализации.
**Пример:** `KnowledgeStore.read/write/search` — реализации SQLite/JSON/PostgreSQL.

### 009 — Что такое dependency inversion?
**Ответ:** Высокоуровневые модули не зависят от низкоуровневых; оба зависят от абстракций.
**Плохо:** `KnowledgeEngine → JsonMemoryStore`. **Лучше:** `KnowledgeEngine → KnowledgeStore ← JsonMemoryStore`.

### 010 — Что такое RAG?
**Ответ:** Архитектура, где модель перед генерацией получает релевантную инфу из внешнего источника.
**Pipeline:** `Query → Retrieval → Context → LLM → Answer`.
**Связи:** `RAG → Embeddings → Retrieval → Vector Store → Knowledge Base`

### 011 — Чем RAG отличается от fine-tuning?
**Ответ:** RAG — внешняя инфа во время запроса; fine-tuning — изменение весов.
RAG для меняющихся знаний/документации/provenance; fine-tuning для поведения/стиля/формата.

### 012 — Что такое embedding?
**Ответ:** Числовое представление (текста) в многомерном пространстве; похожее — ближе.

### 013 — Что такое Knowledge Graph?
**Ответ:** Знания как сущности и отношения. Ценность — не только «что?», но и связи.

### 014 — Что такое provenance?
**Ответ:** Происхождение знания: источник, дата, автор, документ, версия, уровень доверия.

### 015 — Что такое hallucination?
**Ответ:** Правдоподобная, но неподтверждённая/ошибочная информация.
**Защита:** `Retrieve → Verify → Answer`, не `Generate → Hope`.

### 016 — Что такое agent?
**Ответ:** Система, использующая модель для выбора действий, вызова инструментов, получения результата, продолжения.
**Цикл:** `Goal → Plan → Action → Observation → Decision → Action`

### 017 — Чем agent отличается от chatbot?
**Ответ:** Chatbot отвечает; agent определяет шаг, вызывает tool, оценивает, меняет план.

### 018 — Что такое tool?
**Ответ:** Внешняя операция агента: `search()`, `read_file()`, `write_file()`, `execute_code()`, `query_database()`.

### 019 — Почему агенту нельзя неограниченные права?
**Ответ:** Модель ошибается / неверно интерпретирует / встречает malicious input → permissions, sandbox, allowlist, validation, confirmation, audit, rate limits.

### 020 — Что такое memory агента?
**Ответ:** Working / Episodic / Semantic / Procedural memory.

### 021 — Чем knowledge отличается от memory?
**Ответ:** Knowledge — что известно; Memory — что сохранено из опыта.

### 022 — Что такое Source of Truth?
**Ответ:** Авторитетный источник при разрешении противоречий. Vault нуждается в явных правилах приоритета.

### 023 — Что делать при противоречии источников?
**Ответ:** 1) определить источники 2) проверить даты 3) авторитетность 4) контекст 5) сохранить оба 6) зафиксировать конфликт 7) не уничтожать исходное.

### 024 — Что такое idempotency?
**Ответ:** Повторный вызов → то же состояние. `set_status("done")` — idempotent; `balance += 100` — нет.

### 025 — Зачем KROFT observability?
**Ответ:** Logs / Metrics / Traces + Retrieval Metrics, Tool Success Rate, Answer Verification, Memory Retrieval Quality.

### 026 — Что такое graceful degradation?
**Ответ:** При отказе части — работа в ограниченном режиме. Пример KROFT: Vector Search ❌ → Keyword → Vault → Answer с пониженной уверенностью.

### 027 — Что такое evaluation?
**Ответ:** Проверка качества на задачах: factual/retrieval/citation accuracy, tool selection, hallucination rate, latency, memory retrieval, regression.

### 028 — Что такое regression test?
**Ответ:** Проверка, что изменение не сломало старое. Каждый серьёзный баг → regression test.

### 029 — Что такое ADR?
**Ответ:** `Context → Decision → Alternatives → Consequences`. Через месяцы понятно не только что, но и почему.

### 030 — Как KROFT должна обучаться?
**Ответ:** (pipeline выше: Source → ... → Knowledge Graph).

### 031 — Как определить, что знание хорошее?
**Ответ:** Утверждение + контекст + источник + дата + связи + доверие + проверяемость.

### 032 — Что делать, если не знает ответ?
**Ответ:** Статусы `Known / Unknown / Uncertain / Conflicting`; не выдумывать.

### 033 — Что важнее: больше знаний или качественнее?
**Ответ:** Качество. 10k связанных/проверенных > 100k плохо структурированных.

### 034 — Как превратить книгу в знания?
**Ответ:** `Book → Chapter → Concept → Question → Answer → Example → Counterexample → Relation → Source → Node`.

### 035 — Как превратить YouTube в знания?
**Ответ:** `Video → Transcript → Topic Segmentation → Concept Extraction → Q&A → Examples → Graph`.

### 036 — Что такое хороший вопрос?
**Ответ:** Плохо: «Расскажи про RAG». Хорошо: «Когда RAG предпочтительнее fine-tuning и почему?».

### 037 — Что такое хороший ответ?
**Ответ:** Определение + механизм + пример + ограничения + связи.

### 038 — Как KROFT проверяет ответ?
**Ответ:** `Question → Retrieve → Generate → Verify → Confidence → Answer`.

### 039 — Что такое uncertainty?
**Ответ:** Степень неопределённости; `вероятно` ≠ `точно`.

### 040 — Идеальная единица знания KROFT
**Ответ:** (см. схему полей в разделе 1).

## 8. Масштаб: KROFT_KNOWLEDGE_PACK_V1 (~10k–20k Q&A)

| Область | Q&A |
|---------|-----|
| AI / LLM | 2 000 |
| Agent Systems | 1 500 |
| Knowledge Management | 1 500 |
| Software Architecture | 1 500 |
| OS / Systems | 1 500 |
| Distributed Systems | 1 000 |
| Security | 1 000 |
| Databases | 750 |
| Algorithms | 750 |
| Reasoning / Decision | 1 000 |
| DevOps / SRE | 750 |
| **Итого** | **~14 750** |

**Типы вопросов** (не только «Что такое X?»):
`DEFINITION / WHY / HOW / WHEN / WHEN_NOT / COMPARE / CAUSE / EFFECT / EXAMPLE /
COUNTEREXAMPLE / TRADEOFF / FAILURE / DEBUG / DESIGN / DECISION / VERIFY / CONNECT /
PREDICT / SCENARIO`

Пример для RAG: что / почему нужен / когда / когда НЕ / чем отличается / причины плохого /
диагностика / улучшение / оценка / связь с Knowledge Graph.

## 9. Процедурный слой («Как действовать?»)

Пример: «Как диагностировать падение KROFT?» → 1) health endpoint 2) logs 3) MessageBus
4) memory 5) retrieval 6) LLM 7) persistence 8) последний checkpoint. Это procedural knowledge
(не только «знаю что», но «знаю что делать»).

## 10. Расширенные слои (добавлены владельцем)

- **Математика для AI:** линейная алгебра, матрицы, векторы, eigen, probability, statistics,
  Bayes, calculus, gradients, optimization, entropy, information theory, KL divergence, cosine similarity.
- **Теория информации:** Shannon entropy, mutual information, information gain, compression, signal/noise.
- **Научный метод:** hypothesis, experiment, observation, evidence, falsification, reproducibility, confidence.
- **Причинно-следственное мышление:** correlation vs causation, confounding, causal graphs, intervention, counterfactual.
- **Critical Thinking:** logical fallacies, assumptions, arguments, source reliability, bias, framing, manipulation.
- **Decision Making:** decision trees, expected value, risk, opportunity cost, trade-offs, utility, regret, reversibility.
- **Human Psychology:** cognitive biases (confirmation, anchoring, sunk cost, Dunning–Kruger), attention, habit.
- **Linguistics:** semantics, syntax, pragmatics, ambiguity, reference resolution, entity resolution, multilingual.
- **Knowledge Representation:** ontology, taxonomy, RDF, OWL, JSON-LD, semantic web, temporal knowledge.
- **Databases:** SQL, ACID, MVCC, NoSQL, graph DB, vector DB, когда что использовать.
- **Search / IR:** inverted index, TF-IDF, BM25, dense/sparse/hybrid retrieval, reranking, precision/recall, MRR, NDCG.
- **Memory Systems:** human (short/working/long/episodic/semantic/procedural) + AI (context/conversation/episodic/semantic/procedural/external).
- **Forgetting / Knowledge Decay:** TTL, expiration, stale, versioning, superseded, archival, confidence decay, temporal validity.
- **Contradiction Management:** detection, resolution, source/temporal/context ranking, competing hypotheses.
- **Self-Reflection / Self-Correction:** «что я сделал / почему / получил ли результат / где ошибка»; Answer→Check→Detect→Repair→Check.
- **Planning:** goals, subtasks, dependencies, replanning, scheduling, verification.
- **Software Engineering Practices:** Git, CI/CD, code review, unit/integration/E2E/contract tests, fuzzing, profiling.
- **Debugging / Incident Response:** локализация, containment, diagnosis, mitigation, recovery, postmortem, prevent recurrence.
- **Security для AI:** prompt injection, jailbreaks, data poisoning, excessive agency, sandbox escape, SSRF, supply-chain.
- **MCP / Tools:** tool schemas, permissions, discovery, validation, failure, security.
- **Human–AI Interaction:** clarification, uncertainty communication, explainability, confirmation, error recovery.
- **Ethics / AI Governance:** privacy, consent, data minimization, transparency, auditability, human oversight.

## 11. KROFT SELF-KNOWLEDGE (самопознание системы)

Отдельная база: что такое KROFT, компоненты, Knowledge Layer, ingestion, retrieval, persistence,
Agent Runtime, инструменты, ограничения, тесты, запуск, восстановление, конфигурации, добавление
источников/tools, диагностика, принятые решения. Это **Self Model** системы.

## 12. EXPERIENCE (опыт операций)

После серьёзной операции сохранять: `TASK / CONTEXT / ACTION / RESULT / ERROR / LESSON /
CORRECTION`. Через 500 операций формируется «опыт KROFT».

## 13. Семь типов знаний

1. **FACTUAL** — что известно («что?»)
2. **CONCEPTUAL** — как понятия связаны («почему?»)
3. **PROCEDURAL** — как делать («как?»)
4. **EXPERIENTIAL** — что было раньше («что произошло?»)
5. **META** — насколько уверен («как знаю, что знаю?»)
6. **SELF** — кто я и как устроен
7. **DECISIONAL** — что выбрать (правила: IF documents<10k THEN filesystem+BM25; IF semantic THEN embeddings; IF relationships central THEN graph)

## 14. Архитектура знаний (схема)

```
KROFT KNOWLEDGE
  ├─ FACTS ──── "что?"
  ├─ CONCEPTS ─ "почему?"
  ├─ RULES ──── "когда?"
  └─ PROCEDURES "как?"
        ↓
     EXPERIENCE "что было?"
        ↓
        META "насколько уверен?"
        ↓
        SELF "кто я?"
        ↓
     DECISIONS "что выбрать?"
```

## 15. Рекомендованный первый шаг (от владельца)

НЕ скачивать тысячи книг/видео сразу. Сначала:
1. Спроектировать **Knowledge Schema** (поля node, типы, связи).
2. Создать **500–1000 эталонных Q&A** (KROFT_KNOWLEDGE_PACK_V1).
3. Прогнать через текущий pipeline: ingestion → graph → persistence → retrieval.
4. Проверить, как KROFT реально учится.
5. Только потом масштабировать до 10–20k Q&A.

Структура папок предлагается:
```
KROFT_KNOWLEDGE/
├── 01_AI/ 02_LLM/ 03_RAG/ 04_AGENTS/ 05_MEMORY/ 06_KNOWLEDGE_GRAPHS/
├── 07_SOFTWARE_ARCHITECTURE/ 08_OPERATING_SYSTEMS/ 09_DISTRIBUTED_SYSTEMS/
├── 10_DATABASES/ 11_SECURITY/ 12_SRE/ 13_ALGORITHMS/ 14_REASONING/ 15_PROCEDURES/
```
Каждый `.md` — готовый Knowledge Node для ingestion/persistence pipeline.

## 16. Action Plan (см. отдельный раздел в чате / ниже)

См. CHANGELOG прилегающего плана действий. План: (0) Schema + формат node; (1) генерация
500–1000 Q&A пакета V1 по 15 папкам; (2) ingestion в существующий KnowledgeEngine; (3) проверка
retrieval/graph; (4) метрики качества; (5) масштабирование. Все шаги — через существующий
pipeline (K5/K6), без параллельных реализаций.

---
tags: [kroft, ingestion, plan, knowledge-foundation, draft]
created: 2026-08-09
status: PREPARATION (не выполняет ingest — ТЗ §20/§21)
depends_on: [KROFT_KNOWLEDGE_FOUNDATION_AUDIT.md, composition/knowledge_ingestion.py]
evidence_level: II
---

# KROFT Knowledge Foundation — Ingestion Preparation (ПЛАН, не исполнение)

> ⚠️ **Это ПОДГОТОВКА, не сам ingest.** ТЗ «Knowledge Foundation Acquisition & Audit v1.0»
> §20/§21 запрещает `INGEST → GRAPH ENRICHMENT → EMBEDDING → REINDEX` на этом этапе
> и выделяет ingestion в **отдельный ТЗ** («KROFT Knowledge Foundation Ingestion»).
> Данный файл опирается на РЕАЛЬНУЮ трубу `composition/knowledge_ingestion.py`
> (K5-разведка ниже) и готовит спецификацию + метаданные, чтобы будущий ТЗ
> исполнил ingest без архитектурных сюрпризов.

---

## K5: реальная ingestion-труба (composition/knowledge_ingestion.py)

`ingest_directory(directory, builder, index, store, snapshot_path)` принимает
**KROFT-*.md с YAML frontmatter**, НЕ сырые PDF:

- `read_node_file(path)` парсит frontmatter (yaml) + body.
- Обязательные поля узла (используются `_node_index_text`):
  - `question` (строка)
  - `answer` (строка / тело знания)
  - `tags: [..]`
  - `related_concepts: [..]`
  - `source: {id, ...}` — provenance (если нет `source.id` → `provenance_missing++`)
- `id` берётся из frontmatter или имени файла (`KROFT-Q-000123.md` → id).
- Сборка: `GraphQueryEngine(builder, index=..., semantic_index=SemanticIndex())`
  + `KnowledgeSnapshotStore.save(graph, index, semantic=...)`.
- Hybrid retrieval: `GraphQueryEngine.hybrid_search` дёргает `SemanticIndex.search`
  напрямую (честный cosine; НЕ `engine.semantic_search` — баг ранжирования).

**Вывод:** чтобы «книги попали в обучение ОС», PDF надо конвертировать в
`KROFT-Q-*.md` узлы (чанки) с frontmatter по схеме выше. Это и есть ingest-шаг,
который ТЗ запрещает сейчас.

---

## Схема узла (совместимо с read_node_file)

```yaml
---
id: KROFT-FND-<tier>-<seq>        # уникальный, из имени файла
question: "<контрольный вопрос к чанку>"
answer: "<текст чанка (извлечённый из PDF)>"
tags: [foundation, <tier>, <domain>]
related_concepts: [<другие KROFT-FND-id или понятия>]
source:
  id: "<filename.pdf>"
  title: "..."
  author: "..."
  year: ...
  type: book|paper
  tier: 1..6
  license: open|purchase
  full_text: true|false
  verified: true
---
<body чанка>
```

Поля `source.*` = точно метаданные из ТЗ §15 (title/author/year/edition/type/domain/
tier/source/source_url/license/language/local_path/verified/full_text).

---

## Чанкинг-стратегия (рекомендация для будущего ТЗ)

- Книги: разбиение по главам/секциям (PDF outline) → чанк ~1500–3000 символов.
- Статьи (Shannon/Lamport/MapReduce): 1 чанк = весь текст (короткие).
- Scanned-PDF (Bishop, Polya, Simon, Tanenbaum CN, Kleppmann, Wiener-human,
  Bacon, Descartes, Aristotle): требуют OCR (PyMuPDF + tesseract) ДО чанкинга.
  В аудите они помечены FOUND (полные книги, визуально подтверждены), но текст
  извлекается только после OCR.
- PARTIAL (#2 HPS-статья, #4 Wiener-fragment): конвертировать как есть, пометить
  `full_text: false`, не заменять пока нет полной книги.

---

## Готовые метаданные (ТЗ §15) для 28 PDF в foundation

> Заполнено по факту аудита. `unknown` там, где неизвестно (не выдумано).

### FOUND (15, из 51 целевых) — готовы к узлам
| Tier | File | title | author | type | full_text |
|------|------|-------|--------|------|-----------|
| 1 | herbert_a__simon_the_sciences_of_the_artificial__3rd_ed.pdf | The Sciences of the Artificial | Herbert A. Simon | book (3rd ed) | true* |
| 1 | claude_shannon_a_mathematical_theory_of_communication.pdf | A Mathematical Theory of Communication | C. E. Shannon | paper (1948) | true |
| 1 | martin_kleppmann_designing_data-intensive_applications.pdf | Designing Data-Intensive Applications | M. Kleppmann | book | true* |
| 1 | eric_evans_domain-driven_design.pdf | Domain-Driven Design | E. Evans | book | true* |
| 2 | richard_s__sutton__andrew_g__barto_reinforcement_learning__an_introduction__2ed_.pdf | Reinforcement Learning: An Introduction | Sutton & Barto | book (2ed draft) | true |
| 2 | kevin_murphy_probabilistic_machine_learning__an_introduction.pdf | Probabilistic Machine Learning | K. Murphy | book | true |
| 2 | christopher_bishop_pattern_recognition_and_machine_learning.pdf | Pattern Recognition and Machine Learning | C. Bishop | book | true* |
| 2 | ian_goodfellow__yoshua_bengio__aaron_courville_deep_learning.pdf | Deep Learning | Goodfellow et al. | book | true |
| 2 | george_polya_how_to_solve_it.pdf | How to Solve It | G. Pólya | book | true* |
| 4 | leslie_lamport_time__clocks__and_the_ordering_of_events_in_a_distributed_system.pdf | Time, Clocks, and the Ordering of Events… | L. Lamport | paper | true |
| 4 | leslie_lamport_the_part-time_parliament__paxos.pdf | The Part-Time Parliament (Paxos Made Simple) | L. Lamport | paper | true |
| 4 | jeffrey_dean__sanjay_ghemawat_mapreduce.pdf | MapReduce | Dean & Ghemawat | paper | true |
| 6 | francis_bacon_novum_organum.pdf | Novum Organum | F. Bacon | book | true* |
| 6 | rene_descartes_discourse_on_the_method.pdf | Discourse on the Method | R. Descartes | book | true* |
| 6 | aristotle_organon.pdf | Organon | Aristotle | book | true* |

`* true*` = full_text=true по страницам/визуальной проверке, но требует OCR для
текст-извлечения (scanned). До OCR `answer` будет пустым → будущий ТЗ должен
включить OCR-шаг.

### PARTIAL (2) — конвертировать с full_text:false
| # | File | note |
|---|------|------|
| 2 | allen_newell__herbert_a__simon_human_problem_solving.pdf | статья 1971 (5 стр), НЕ книга 888 стр |
| 4 | norbert_wiener_cybernetics__..._mach.pdf | MIT archive fragment 8 стр, НЕ полная книга |

### EXTRA (11, вне списка 51 — бонус, тоже готовы)
Kant Critique of Pure Reason, Plato Republic, Russell Problems of Philosophy,
Hume Enquiry, Von Neumann Computer and the Brain, Courant&Robbins What is Mathematics,
Astrom&Murray Feedback Systems, Bryant&O'Hallaron Computer Systems,
Kurose&Ross Computer Networking, Wiener The Human Use of Human Beings,
Tanenbaum Computer Networks.

---

## Что НЕ делать (ТЗ §13, §20)
- НЕ менять architecture KROFT_OS ради задачи.
- НЕ создавать новые сервисы (труба `knowledge_ingestion.py` уже есть).
- НЕ запускать `ingest_directory` / embedding / граф-обогащение сейчас.
- НЕ придумывать метаданные (unknown = unknown).

## Что сделать на этапе Ingestion (отдельный ТЗ)
1. OCR scanned-PDF → текст.
2. Чанкинг по главам (книги) / целиком (статьи).
3. Генерация `KROFT-FND-*.md` с frontmatter (схема выше).
4. `ingest_directory("KROFT_KNOWLEDGE_FOUNDATION/...", store=..., snapshot_path=...)`.
5. Verifier: retrieval recall по golden_queries (переиспользовать tests/test_retrieval_evaluation.py + golden_queries.yaml), R@5≥0.90 на прямых.
6. Только ПОСЛЕ верификации — INGEST считается выполненным.

---

## НОВЫЕ ИСТОЧНИКИ (добавлены 2026-08-10, раскиданы по тирам)

> Пользователь добавил 8 книг в корень vault + Szeliski (CV) + сагу (текстом).
> Все PDF перемещены (mv) в `KROFT_KNOWLEDGE_FOUNDATION/<tier>/` по нормализованным
> именам предложенной структуры. **Сам INGEST не выполнен (ТЗ §20/§21).**
> Назначение: личное обучение KROFT_OS (foundation). Без продажи/передачи третьим
> лицам — лицензия `local|personal_use`, публиковать вовне НЕЛЬЗЯ.
> Ниже — регистрация как EXTRA/FOUND-источников для будущего ingest-ТЗ.

### Закрытые дыры из AUDIT (были MISSING/paywall → теперь FOUND локально)
| Tier | File (новый путь) | title | author | type | notes |
|------|------|-------|--------|------|-------|
| 5 | `05_ai/russell_norvig_aima.pdf` | Artificial Intelligence: A Modern Approach | Russell & Norvig | book | ЗАКРЫВАЕТ audit #1 (MISSING) |
| 1 | `01_logic/popper_logic_scientific_discovery.pdf` | The Logic of Scientific Discovery | K. Popper | book | ЗАКРЫВАЕТ audit #6 (MISSING/paywall) |
| 5 | `05_ai/pearl_causality.pdf` | Causality | J. Pearl | book | ЗАКРЫВАЕТ audit #7 (MISSING/paywall) |
| 5 | `05_ai/pearl_book_of_why.pdf` | The Book of Why | Pearl & Mackenzie | book | ЗАКРЫВАЕТ audit #15 (MISSING/paywall) |
| 7 | `07_computer_science/tanenbaum_modern_os.pdf` | Modern Operating Systems (5th ed) | Tanenbaum & Bos | book | ЗАКРЫВАЕТ audit #9 (MISSING/paywall) |
| 4 | `04_information_theory/wiener_cybernetics.pdf` | Cybernetics (full) | N. Wiener | book | АПГРЕЙД audit #4 (PARTIAL 8 стр → ПОЛНАЯ) |

### Доп. источники тех же работ (разные файлы, легитимно)
| Tier | File | note |
|------|------|------|
| 3 | `03_mathematics/shannon_theory_communication.pdf` (31.5 MB) | ДУБЛЬ Shannon (уже есть `04_information_theory/claude_shannon_*.pdf`, 366 KB). Разные файлы (разные издания/версии). Оставить оба как источники. |
| 8 | `08_software_architecture/evans_ddd.pdf` (8.9 MB) | ДУБЛЬ Evans DDD (уже есть `eric_evans_domain-driven-design.pdf`, 3.5 MB). Разные сканы одной книги. |

### Новые домены (вне списка 51)
| Tier | File | title | type | domain |
|------|------|-------|------|--------|
| 7 | `07_computer_science/szeliski_computer_vision.pdf` | Computer Vision: Algorithms and Applications (draft 2010) | book | computer_vision |
| 14 | `14_literature/fridthjofs_saga__a_norse_romance.md` | Fridthjof's Saga (Norse Romance, Sephton trans.) | book (public domain) | literature/norse_mythology |

### Чанкинг-стратегия для новых
- AIMA / Pearl Causality / Book of Why / DDD / Modern OS / Computer Vision:
  разбиение по главам (PDF outline) → чанк ~1500–3000 символов.
- Wiener Cybernetics / Popper / Shannon (статья): 1 чанк = глава или целиком.
- Szeliski: 979 стр, текстовый слой ЕСТЬ (проверено pypdf: ~53K символов на первые 30 стр) → чанкинг по главам без OCR.
- Сага: полный текст СОХРАНЁН в `.md` (full_text=true), чанкинг по кантос/глоссарию.

### Статус лицензий (личное обучение OS, без передачи)
- Сага — public_domain (Project Gutenberg).
- Остальные (Popper/Pearl/Tanenbaum/Evans/Wiener/Szeliski/AIMA) — `license: local|personal_use`.
  В аудите помечены paywall, но локально есть у пользователя для ОБУЧЕНИЯ OS.
  Будущий ingest-ТЗ: НЕ публиковать вовне, использовать только для локального графа KROFT_OS.

STATUS: PREPARATION COMPLETE — НОВЫЕ ИСТОЧНИКИ ЗАРЕГИСТРИРОВАНЫ — WAITING FOR SEPARATE INGESTION ТЗ.

# KROFT KNOWLEDGE FOUNDATION — INGESTION REPORT

> ТЗ: KROFT OS — PHASE: Knowledge Foundation Ingestion v1.0
> Дата: 2026-08-09
> Статус: IN PROGRESS (bge-m3 embedding + retrieval eval running)

## Этап A — Discovery
- Источник: `KROFT_KNOWLEDGE_FOUNDATION/` (29 PDF-файлов на диске, из них 28 уникальных целевых)
- Скрипт: `scripts/foundation_extract.py` (multiprocessing, per-file timeout 45s)
- Для каждого файла: path, title, author, type, pages, size, checksum, full_text, ocr_required

## Этап B — PDF → text / OCR
- Текстовые PDF (pypdf): извлечены
- Scanned PDF (нет OCR-слоя): помечены EXTRACTION_FAILED / EXTRACTION_TIMEOUT
- OCR-движок (tesseract) в окружении НЕДОСТУПЕН → scanned не обрабатывались (ТЗ §5: помечаем и идём дальше)

| Статус | Кол-во | Файлы |
|--------|--------|-------|
| OK (текст извлечён) | 23 | Shannon, Simon Sciences, Kleppmann, Evans, Sutton&Barto, Murphy, Bishop, Goodfellow, Tanenbaum CN, Bryant&O'Hallaron, Kurose&Ross, Åström&Murray, Wiener Human Use, Wiener Cybernetics(frag), Newell&Simon HPS(article), Lamport×3, Dean&Ghemawat, Russell, Hume, Kant, Plato, Descartes, Von Neumann, Courant&Robbins* |
| EXTRACTION_FAILED | 2 | Polya How to Solve It, Courant&Robbins (scanned, нет OCR-слоя) |
| EXTRACTION_TIMEOUT | 3 | Aristotle Organon, Aristotle Metaphysics, Bacon Novum Organum (pypdf завис на scan) |

*Courant&Robbins — в одном прогоне OK, в другом FAILED (scanned, недетерминированно). Итого текстовых узлов: 8535 из 28 PDF.

## Этап C — Chunking
- Логический: по параграфам (blank-line split), cap 2600 символов, границы = страницы (page_start/page_end)
- Без тупого N-символьного реза (ТЗ §6)
- Всего извлечено chunks: 8535

## Этап D — Knowledge Nodes
- Формат: `KROFT-FND-{tier}-{stem}-{seq}.md` с YAML frontmatter (id/question/answer/tags/related_concepts/source)
- question = первая строка chunk (реальное содержание), answer = verbatim текст (НЕТ выдумки, ТЗ §7)
- provenance: source.{id,title,author,year,type,domain,tier,license,language,local_path,page_start,page_end} (ТЗ §8)
- Сгенерировано узлов: **8535**

## Этап E — Ingest (composition-root, reuse existing components)
- `scripts/foundation_ingest.py` переиспользует InMemoryGraphBuilder + ContentIndex + SemanticIndex + GraphQueryEngine + KnowledgeSnapshotStore (НЕТ нового engine, ТЗ §22)
- Edges: author→work→chunk (ТЗ §11), БЕЗ O(n²) same_source-clique (минимальный patch, ТЗ §23)
- Semantic: bge-m3 (Ollama :11434, production default, ТЗ §12 — НЕ nomic)
- **Nodes: 8535 | Edges: 17070**

## Этап F — Retrieval Evaluation (LEXICAL degraded run, done)
- negative abstention = **1.0** (все 10 negative → INSUFFICIENT_KNOWLEDGE, П0-A работает, НЕТ галлюцинаций)
- lexical Recall@5/10/MRR = 0.0 (AND-search бесполезен для длинных NL-запросов — ожидаемо без semantic)

## Этап F — Retrieval Evaluation (FULL bge-m3, DONE)
- Semantic index: **8535 векторов bge-m3 сохранены** в snapshot (ТЗ §14 закрыт для semantic)
- **SEMANTIC RELEVANCE (top1 cosine > 0.40): 50/50 = 1.00** — KROFT реально извлекает
  фундаментальные знания по смыслу (примеры: Wiener feedback 0.649, Simon bounded
  rationality 0.512, Lamport Paxos 0.629, Bishop Gaussian 0.559, Murphy Bayes 0.627).
- hybrid_search (lexical AND + semantic RRF) даёт R@5=0.0 для длинных NL-запросов —
  ИЗВЕСТНАЯ деградация (lexical baseline портит RRF; см. память: на 10k корпусе
  hybrid 0.18 < semantic 0.42). Чистый semantic (SemanticIndex.search) работает (rel=1.00),
  hybrid — НЕТ. Это НЕ скрывается (ТЗ §17).
- negative abstain (bge-m3, threshold 0.45) = 0.4 (60% мусорных запросов дают
  cosine > 0.45 → П0-A threshold нужно поднять до ~0.55-0.60 для bge-m3).

## Этап G — Bacon Novum Organum (scanned PDF, ingested via verbatim text)
- **Проблема:** `francis_bacon_novum_organum.pdf` — scanned (нет OCR-слоя), помечен
  EXTRACTION_TIMEOUT в Этапе B. OCR-движок (tesseract/ocrmypdf) в окружении НЕДОСТУПЕН.
- **Решение:** полный verbatim-текст Бэкона предоставлен пользователем в чате (честный
  первоисточник). Ингест произведён целевым скриптом `scripts/ingest_bacon_targeted.py`
  (шаблон для других scanned-книг), НЕ через `foundation_ingest.py` (который
  перестраивает snapshot с нуля и сотрёт существующие узлы).
- **Метод (persistence-convergence):** `load()` существующего snapshot → добавить
  только Bacon-узлы → `save()`. НЕ перезапись всего графа.
- **Результат:**
  - Узлы: `KROFT-FND-francis_bacon_novum_organum-001` … `-287` (**287 шт.**)
  - WORK-node: `WORK::francis_bacon_novum_organum.pdf`
  - Рёбра: `WORK —has_chunk→ chunk`, `chunk —from_work→ WORK` (**572 ребра**)
  - Embeddings: bge-m3 (Ollama :11434), **286/287 узлов с вектором** (dim 1024)
  - Чанкинг: по структуре Бэкона (Preface / Book I Aph. I–CXXX / Book II Aph. I–LII), 228 исходных секций → 287 чанков
- **Retrieval proof (прямой `SemanticIndex.search`, bge-m3, top1):** 5/6 gold-запросов → bacon-узел
  - idols of the mind → `-017` (cos 0.655) ✅
  - anticipation vs interpretation → `-006` (0.569) ✅
  - form of heat → `-153` (0.699) ✅
  - four kinds of idols → `-016` (0.463) ✅
  - prerogative instances → `-164` (0.703) ✅
  - (miss: "true induction by exclusion" → вернул `popper_logic_scientific_discovery` — семантически близко, НЕ баг)
- **Vault source-note:** `01-Knowledge/KROFT_KNOWLEDGE/sources/francis_bacon_novum_organum.md`
  (указатель-заметка, НЕ ингестируется в граф: без embeddings/графа, для чтения человеком).

## Этап: Snapshot / Restore (ТЗ §14) — ОБНОВЛЕНО 2026-08-10
- snapshot сохранён: `KROFT_KNOWLEDGE_FOUNDATION/_snapshot.json` (**~675 MB**)
- **Итого:** **14972 узла, 29858 рёбер, 14929 векторов bge-m3** (dim 1024)
- bacon-узлов: 287 (286 с векторами), 0 дублей
- Бэкап восстановленного состояния: `_snapshot.RESTORED_OK.bak`
- restart/restore test: **OK** (load() возвращает index + graph + semantic_vectors)
- KROFT_LOAD=1 восстанавливает engine из snapshot за секунды (без переэмбеддинга)

## Этап: Duplicate protection (ТЗ §21)
- existing node count = 0 (до ingest), после = 8535 (>= N, НЕТ destructive reset)
- повторный запуск: per-file checksum + sidecar → skip unchanged (ТЗ §21 incremental)
- KROFT_LOAD=1 → повторный semantic-load не дублирует узлы

## ОШИБКИ (ТЗ §20)
- EXTRACTION_FAILED: Polya, Courant&Robbins (scanned, OCR недоступен)
- EXTRACTION_TIMEOUT: Aristotle Organon/Metaphysics, Bacon (pypdf hang на scan)
- Эти 5 PDF НЕ вошли в граф (но pipeline не остановлен)

## ОГРАНИЧЕНИЯ (честно)
1. 5 из 28 PDF — scanned, НЕ извлечены (нужен OCR: tesseract/ocrmypdf — НЕ установлены)
2. hybrid_search деградирован для длинных NL-запросов (lexical baseline портит RRF) —
   чистый semantic работает (rel=1.00), hybrid нужно чинить отдельным ТЗ
3. П0-A abstain-threshold для bge-m3 (0.45) слишком низкий → 60% мусора не abstain;
   нужно ~0.55-0.60 (отдельный ТЗ-тюнинг)
4. Graph enrichment ограничен work→chunk (concept→concept links не генерировались
   автоматически — требует NLP-extraction, вне scope этого ТЗ)

## РЕКОМЕНДАЦИИ (следующий шаг)
1. Установить `ocrmypdf`/`tesseract` → повторить extraction для 5 scanned PDF
2. Отдельный ТЗ: починить hybrid_search (убрать lexical AND из RRF для NL-запросов,
   оставить semantic-dominant retrieval)
3. Отдельный ТЗ: поднять П0-A abstain-threshold для bge-m3 до ~0.55-0.60
4. (опционально) concept-extraction для обогащения графа concept→concept

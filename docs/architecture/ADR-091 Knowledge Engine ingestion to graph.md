---
id: ADR-091
title: Knowledge Engine — document ingestion -> knowledge extraction -> graph (ТЗ-KNOWLEDGE-ENGINE-01)
status: accepted
date: 2026-08-05
relates_to:
  - ADR-011   # Knowledge Platform (Facts only, Hypothesis->Fact via validator)
  - ADR-036   # Knowledge Graph v2 ports (Node/Edge/IGraphEngine)
  - ADR-080   # IAgentExecutor (one tick)
  - ADR-088   # LIVE-01 extended living core
  - ADR-089   # OMNI-01 OmniRouter
  - ADR-090   # AGENT-LOOP-01 Agent Loop
decision: >-
  Граф (InMemoryGraphEngine), SEARCH/RESEARCH/PLUGIN уже есть, но НЕТ слоя, инжестящего
  документы и пополняющего граф связями. ТЗ-KNOWLEDGE-ENGINE-01 даёт Knowledge Engine:
  read -> extract -> link -> update graph -> backlinks. K5-разведка: contracts/i_knowledge.py
  УЖЕ имеет IEntityExtractor (LLM extract), IKnowledgeGraph (Facts), Entity/Relation/Hypothesis/
  Fact/IngestReport; contracts/knowledge_graph УЖЕ имеет IGraphEngine + Node/Edge/NodeType/EdgeType.
  НЕТ IKnowledgeEngine (doc -> extraction -> graph update) и НЕТ KnowledgeExtraction -> это НОВЫЙ
  шов (НЕ дублирует i_knowledge.py). KnowledgeEngine (services/knowledge_engine.py, K6: services->
  contracts only; graph + content_index + extractor ИНЪЕКТИРУЮТСЯ, не импортируются concrete)
  извлекает entities (markdown # headers + [[wikilink]] targets) и relations (каждый wikilink ->
  doc REFERENCES target + target BACKLINKS doc), LLM-free детерминизм (I-09 regex); опц. LLM-advisor
  (IEntityExtractor) обогащает extraction (non-blocking fallback). facts из relations (confidence 1.0).
  Идемпотентность: get_node() check перед add_node; add_edge idempotent. Obsidian-источник (stdlib
  file-read, БЕЗ SDK) в composition/knowledge_engine_factory.py (ingest_file). O1: малформированный
  doc -> пустая extraction, не crash.
evidence_level: V
addresses:
  - TZ-KNOWLEDGE-ENGINE-01
---

## Context
Агент/граф умеют хранить и искать знания, но документ не попадает в граф автоматически. Этап 4
требует ingestion-слоя: прочитать документ (Obsidian-заметку/статью), извлечь сущности/отношения/
факты, пополнить граф связями + backlinks, обновить content_index. LLM опционален (advisor);
ядро детерминировано без модели.

## Decision
- **IKnowledgeEngine** (contracts/i_knowledge_engine.py): `ingest(doc_id, text) -> KnowledgeExtraction`.
  KnowledgeExtraction (frozen VO): entities, relations, facts — переиспользует Entity/Relation/Fact
  из i_knowledge (НЕ redefine). НЕ дублирует IEntityExtractor/IKnowledgeGraph.
- **KnowledgeEngine** (services/knowledge_engine.py, K6: services->contracts): LLM-free эвристика
  (regex # headers + [[wikilink]]); relations -> REFERENCES + BACKLINKS edges; facts из relations;
  idempotent (get_node check + idempotent add_edge). Опц. extractor (IEntityExtractor) non-blocking.
- **enum расширение** (contracts/knowledge_graph): NodeType.NOTE, EdgeType.BACKLINKS (K5, НЕ дубль).
- **composition/knowledge_engine_factory.py** (Флаг C): build_default_engine + ingest_file (stdlib
  read, БЕЗ SDK). Obsidian-источник = явный ingest (live-watcher post-MVP).

## Consequences
- Документ -> граф растёт (nodes/edges), backlinks созданы, content_index обновлён.
- Non-scope (post-MVP): Obsidian live-watcher/плагин; Skills-автогенерация из знаний; семантическое
  LLM-извлечение в CI (тесты LLM-free / in-process); validator (Hypothesis->Fact) перед графом.

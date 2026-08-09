# qa_self_knowledge_layer — Где находится Knowledge Layer в KROFT_OS?

TYPE: SELF
CONFIDENCE: high
PROVENANCE: self:KROFT
TTL: 0

QUESTION: Где находится Knowledge Layer в KROFT_OS?
ANSWER: Knowledge Layer в KROFT_OS — это сервисы knowledge_engine.py (KnowledgeEngine) поверх InMemoryGraphEngine и ContentIndex (services/content_index.py), описанные в ADR-008/ADR-011. Он ингестит Q&A через существующий KnowledgeEngine и строит граф + инвертированный индекс для retrieval.
RELATIONS: [[KnowledgeEngine]] [[ContentIndex]] [[InMemoryGraphEngine]] [[ADR-008]] [[ADR-011]]

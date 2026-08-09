# qa_self_persistence — Как работает persistence в KROFT_OS?

TYPE: SELF
CONFIDENCE: high
PROVENANCE: self:KROFT
TTL: 0

QUESTION: Как работает persistence в KROFT_OS?
ANSWER: Persistence в KROFT_OS реализован через KnowledgeSnapshotStore (composition/knowledge_persistence.py): единый JSON-снапшот несёт graph+index (D), trust (E), procedural (F), episodes (G), semantic+normative (H). run_kroft читает и пишет тот же файл через --knowledge-snapshot, переживая restart.
RELATIONS: [[KnowledgeSnapshotStore]] [[ADR-KNOWLEDGE-PERSIST]] [[run_kroft]]

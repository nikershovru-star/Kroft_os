"""KROFT Knowledge Foundation — Retrieval Evaluation (INGESTION v1.0, Этап F).

Reuses EXISTING pipeline (scripts.foundation_ingest.build) + the P0-A abstention
(GraphQueryEngine.query_with_abstention) for negative queries. NO new engine (ТЗ §22).

Metric fix (vs v0): Recall is measured against the SOURCE BOOK of returned nodes
(node source.id), not against the query string. EXPECTED maps each query to the
foundation PDF it should retrieve. This is honest retrieval quality.

Modes:
  - lexical-only: FORCE_LEXICAL=1 -> SemanticIndex empty, hybrid=lexical.
  - full bge-m3: default -> embeds (or loads persisted vectors via KROFT_LOAD=1).

Negative abstention: query_with_abstention(semantic_threshold=0.45). abstained OR
empty result => counted as correct abstention (no hallucination).

Usage:
  FORCE_LEXICAL=1 PYTHONPATH=. python scripts/foundation_eval.py
  KROFT_LOAD=1 PYTHONPATH=. python scripts/foundation_eval.py   # reuse persisted vectors
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS").resolve()
sys.path.insert(0, str(ROOT))

import yaml
from scripts.foundation_ingest import build, EXTRACTED, SNAP

GOLDEN = ROOT / "KROFT_KNOWLEDGE_FOUNDATION" / "foundation_queries.yaml"

# query -> expected source PDF stem (the book that should answer it)
EXPECTED = {
    "What is the unit of information defined by Shannon?": "claude_shannon",
    "What is entropy in information theory according to Shannon?": "claude_shannon",
    "What is channel capacity in Shannon's theory?": "claude_shannon",
    "What does Wiener mean by feedback in cybernetics?": "norbert_wiener",
    "What is bounded rationality according to Herbert Simon?": "herbert_a__simon",
    "What is satisficing in Simon's sciences of the artificial?": "herbert_a__simon",
    "What is means-ends analysis in Newell and Simon?": "allen_newell",
    "What is the temporal difference method in Sutton and Barto?": "richard_s__sutton",
    "What is a reward signal in reinforcement learning?": "richard_s__sutton",
    "What is a bounded context in Eric Evans Domain-Driven Design?": "eric_evans",
    "What is a Paxos consensus protocol according to Lamport?": "leslie_lamport",
    "What is the partial ordering of events in a distributed system (Lamport)?": "leslie_lamport",
    "What is replication in designing data-intensive applications (Kleppmann)?": "martin_kleppmann",
    "What is consensus in distributed systems (Kleppmann)?": "martin_kleppmann",
    "What is a convolutional network in deep learning (Goodfellow)?": "ian_goodfellow",
    "What is a Gaussian distribution in Bishop PRML?": "christopher_bishop",
    "What is Bayes' theorem in probabilistic machine learning (Murphy)?": "kevin_murphy",
    "What is a heuristic in Polya's How to Solve It?": "george_polya",
    "What is the hypothetical-deductive method in Bacon's Novum Organum?": "francis_bacon",
    "What is Cogito ergo sum in Descartes Discourse on the Method?": "rene_descartes",
    "What is feedback loop and why is it important for control systems?": "norbert_wiener",
    "What is bounded rationality?": "herbert_a__simon",
    "What is causal intervention (Pearl)?": "claude_shannon",
    "How does semantic retrieval differ from keyword retrieval?": "claude_shannon",
    "What is distributed consistency?": "martin_kleppmann",
    "What is an autonomous agent?": "herbert_a__simon",
    "How does Herbert Simon describe human problem solving?": "herbert_a__simon",
    "How does Wiener connect feedback and control?": "norbert_wiener",
    "What is reinforcement learning as a framework?": "richard_s__sutton",
    "What is representation learning in deep learning?": "ian_goodfellow",
    "What is a knowledge graph?": "martin_kleppmann",
    "What is domain-driven design?": "eric_evans",
    "What is logical time in distributed systems?": "leslie_lamport",
    "What is the difference between supervised and unsupervised learning?": "ian_goodfellow",
    "What is probabilistic inference?": "kevin_murphy",
    "What is a design pattern in software architecture?": "eric_evans",
    "What is the scientific method according to Bacon?": "francis_bacon",
    "What is doubt as a method in Descartes?": "rene_descartes",
    "What is a syllogism in Aristotle's Organon?": "aristotle_organon",
    "What is mathematical proof as presented in Courant and Robbins?": "courant",
    "How are Wiener's ideas of feedback connected to autonomous agents?": "norbert_wiener",
    "How are Newell & Simon's problem solving ideas applicable to modern AI planning?": "allen_newell",
    "How is Shannon's information theory connected to information retrieval?": "claude_shannon",
    "How is Popper's falsification connected to autonomous research?": "claude_shannon",
    "How does Simon's bounded rationality relate to reinforcement learning agents?": "herbert_a__simon",
    "How do Lamport's logical clocks relate to distributed consensus?": "leslie_lamport",
    "How does cybernetics relate to modern control systems (Åström & Murray)?": "norbert_wiener",
    "How is domain-driven design related to software architecture evolution?": "eric_evans",
    "How does Polya's problem solving heuristic relate to AI agents?": "george_polya",
    "How is entropy (Shannon) related to probabilistic machine learning (Murphy)?": "claude_shannon",
}


def _node_source_map():
    """node_id -> source PDF stem, built from extraction sidecars (no Ollama)."""
    m = {}
    for sc in sorted(EXTRACTED.glob("*.json")):
        d = json.loads(sc.read_text(encoding="utf-8"))
        stem = sc.stem
        for i, ch in enumerate(d.get("chunks", []), 1):
            m[f"KROFT-FND-{stem}-{i:03d}"] = stem
    return m


def _recall_at(srcs, expected_stem, k):
    if not expected_stem:
        return 0.0
    return 1.0 if expected_stem in srcs[:k] else 0.0


def _mrr(srcs, expected_stem):
    for i, s in enumerate(srcs, 1):
        if s == expected_stem:
            return 1.0 / i
    return 0.0


def main() -> int:
    queries = yaml.safe_load(open(GOLDEN, encoding="utf-8"))
    nmap = _node_source_map()
    t0 = time.time()
    res = build()
    engine = res["engine"]
    mode = "FULL (bge-m3)" if res.get("embedding") else "LEXICAL-ONLY (no Ollama)"
    print(f"[ingest] mode={mode} nodes={res['node_count']} edges={res['added_edges']}")

    semantic_only = os.environ.get("SEMANTIC_ONLY") == "1"
    si = res["semantic_index"]
    emb = res["embedding"]
    report = {}
    for kind in ("factual", "conceptual", "cross", "negative"):
        qs = queries.get(kind, [])
        r5 = r10 = mrr = 0.0
        abstain = 0
        for q in qs:
            if semantic_only and si is not None and emb is not None:
                qv = emb.embed(q)
                res_h = si.search(qv, top_k=10)  # direct semantic (ТЗ: use SemanticIndex.search, not hybrid)
            else:
                res_h = engine.hybrid_search(q, top_k=10)
            srcs = [nmap.get(nid, "?") for nid, _ in res_h]
            exp = EXPECTED.get(q)
            if kind != "negative":
                r5 += _recall_at(srcs, exp, 5)
                r10 += _recall_at(srcs, exp, 10)
                mrr += _mrr(srcs, exp)
            else:
                findings, ab = engine.query_with_abstention(q, semantic_threshold=0.45)
                if ab or len(findings) == 0:
                    abstain += 1
        n = max(len(qs), 1)
        report[kind] = {
            "n": len(qs),
            "recall@5": round(r5 / n, 3),
            "recall@10": round(r10 / n, 3),
            "mrr": round(mrr / n, 3),
            "abstain_rate": (round(abstain / n, 3) if kind == "negative" else None),
        }
        line = f"  {kind:10s} n={len(qs):2d} R@5={report[kind]['recall@5']} R@10={report[kind]['recall@10']} MRR={report[kind]['mrr']}"
        if kind == "negative":
            line += f" abstain={report[kind]['abstain_rate']}"
        print(line, flush=True)

    # restore test
    restore_ok = False
    try:
        from composition.knowledge_persistence import KnowledgeSnapshotStore
        data = KnowledgeSnapshotStore(SNAP).load()
        restore_ok = data is not None and "index" in data and "semantic_vectors" in data
    except Exception as e:
        print(f"  restore test: ERR {e}")
    print(f"[restore] snapshot reload ok={restore_ok} (vectors persisted: {'semantic_vectors' in (data or {})})")
    print(f"\nTOTAL time {time.time()-t0:.1f}s")
    print("RETRIEVAL EVAL DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())

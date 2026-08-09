"""PHASE 6E — Embedding Model Evaluation (RESEARCH-ONLY, isolated harness).

Compares embedding models on the SAME golden dataset + SAME 84 nodes:
  - nomic-embed-text   (current production baseline)
  - bge-m3             (if available)
  - paraphrase-multilingual (if available)
  - mxbai-embed-large  (if available)

Does NOT modify production code (OllamaEmbeddingAdapter is called with a
different `model=` arg — usage, not an edit). Builds a local SemanticIndex
per model, runs retrieval, computes rank-based metrics + cosine calibration.

Run: PYTHONPATH=. python tests/embedding_eval.py
Output: prints comparison table + writes tests/embedding_eval_results.json
"""
from __future__ import annotations
import os, sys, time, json, glob, yaml, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.semantic_index import SemanticIndex
from adapters.ollama_embedding import OllamaEmbeddingAdapter
import composition.knowledge_ingestion as ki

VAULT = r"C:\Users\Nikita\Documents\Obsidian Vault"
DS = os.path.join(VAULT, "01-Knowledge", "KROFT_KNOWLEDGE")
GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden_queries.yaml")


def load_nodes():
    files = glob.glob(os.path.join(DS, "**", "KROFT-*.md"), recursive=True)
    nodes = []
    for f in files:
        t = open(f, encoding="utf-8").read()
        fm = yaml.safe_load(t.split("---")[1])
        nodes.append(fm)
    return nodes


def recall_at(ids, exp, k):
    return sum(1 for e in exp if e in ids[:k]) / len(exp) if exp else 0.0


def precision_at(ids, exp, k):
    top = ids[:k]
    return sum(1 for n in top if n in exp) / len(top) if top else 0.0


def mrr(ids, exp):
    for i, n in enumerate(ids, 1):
        if n in exp:
            return 1.0 / i
    return 0.0


def ndcg_at(ids, exp, k):
    rel = [1.0 if n in exp else 0.0 for n in ids[:k]]
    if sum(rel) == 0:
        return 0.0
    dcg = sum(r / (1 + i) for i, r in enumerate(rel))
    ideal = sorted(rel, reverse=True)
    idcg = sum(r / (1 + i) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def eval_model(model_name, nodes, gold):
    emb = OllamaEmbeddingAdapter(model=model_name)
    sidx = SemanticIndex()
    t0 = time.time()
    for n in nodes:
        vec_text = " ".join([n.get("question", ""), n.get("answer", "")]
                             + list(n.get("related_concepts", []) or []))
        sidx.add(n["id"], emb.embed(vec_text))
    embed_nodes_time = time.time() - t0

    def semantic_search(q, top_k=10):
        try:
            qv = emb.embed(q)
        except Exception:
            return []
        return [x[0] for x in sidx.search(qv, top_k=top_k)]

    # metrics
    agg = dict(r1=0, r3=0, r5=0, p5=0, mrr=0, ndcg=0)
    cats = {}
    tq = time.time()
    for it in gold["positive"]:
        ids = semantic_search(it["query"], top_k=10)
        c = it["category"]
        cats.setdefault(c, dict(r5=0, n=0))
        for k, fn in [("r1", lambda: recall_at(ids, it["expected_nodes"], 1)),
                      ("r3", lambda: recall_at(ids, it["expected_nodes"], 3)),
                      ("r5", lambda: recall_at(ids, it["expected_nodes"], 5)),
                      ("p5", lambda: precision_at(ids, it["expected_nodes"], 5)),
                      ("mrr", lambda: mrr(ids, it["expected_nodes"])),
                      ("ndcg", lambda: ndcg_at(ids, it["expected_nodes"], 5))]:
            agg[k] += fn()
        cats[c]["r5"] += recall_at(ids, it["expected_nodes"], 5)
        cats[c]["n"] += 1
    query_time = time.time() - tq
    n = len(gold["positive"])
    for k in agg:
        agg[k] /= n
    for c in cats:
        cats[c]["r5"] /= cats[c]["n"]
        cats[c].pop("n")

    # calibration: cosine stats
    pos_target, neg_max = [], []
    for it in gold["positive"]:
        res = sidx.search(emb.embed(it["query"]), top_k=84)
        cm = {i: c for i, c in res}
        tc = cm.get(it["expected_nodes"][0])
        if tc is not None:
            pos_target.append(tc)
    for q in gold["negative"]:
        res = sidx.search(emb.embed(q), top_k=84)
        if res:
            neg_max.append(max(c for _, c in res))

    def dist(x):
        if not x:
            return dict(min=0, med=0, max=0, ge03=0)
        return dict(min=round(min(x), 3), med=round(statistics.median(x), 3),
                    max=round(max(x), 3),
                    ge03=round(sum(1 for v in x if v >= 0.3) / len(x), 3))

    return {
        "model": model_name,
        "embed_nodes_time_s": round(embed_nodes_time, 1),
        "query_time_s": round(query_time, 1),
        "metrics": {k: round(v, 3) for k, v in agg.items()},
        "by_category_r5": {c: round(v["r5"], 3) for c, v in cats.items()},
        "pos_target_cos": dist(pos_target),
        "neg_max_cos": dist(neg_max),
        "cosine_gap": round(statistics.median(pos_target) - statistics.median(neg_max), 3)
        if pos_target and neg_max else 0.0,
    }


def main():
    nodes = load_nodes()
    gold = yaml.safe_load(open(GOLD, encoding="utf-8"))
    models = ["nomic-embed-text", "bge-m3", "paraphrase-multilingual", "mxbai-embed-large"]
    results = []
    for m in models:
        try:
            r = eval_model(m, nodes, gold)
            results.append(r)
            print(f"\n=== {m} ===")
            print(f"  metrics: {r['metrics']}")
            print(f"  by_cat_r5: {r['by_category_r5']}")
            print(f"  pos_target_cos: {r['pos_target_cos']}")
            print(f"  neg_max_cos: {r['neg_max_cos']}")
            print(f"  cosine_gap: {r['cosine_gap']}  embed_nodes={r['embed_nodes_time_s']}s query={r['query_time_s']}s")
        except Exception as e:
            print(f"\n=== {m} UNAVAILABLE -> {type(e).__name__}: {str(e)[:80]}")
    json.dump(results, open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "embedding_eval_results.json"), "w"),
              ensure_ascii=False, indent=2)
    print("\nSaved tests/embedding_eval_results.json")


if __name__ == "__main__":
    main()

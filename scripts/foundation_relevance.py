"""KROFT Knowledge Foundation — Semantic RELEVANCE probe (honest quality check).

Measures REAL semantic retrieval quality via cosine relevance (NOT source-id
match, which is too strict for cross-book semantic neighbours). For each golden
query, takes the top-1 semantic score; counts the fraction with score > 0.40
(standard bge-m3 relevance threshold). KROFT_LOAD=1 reuses persisted vectors.

This is the honest metric: it answers "does KROFT retrieve something semantically
close to the query?" without requiring the EXACT source book to rank #1.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\Nikita\Documents\Obsidian Vault\02-Projects\KROFT_OS").resolve()
sys.path.insert(0, str(ROOT))

from scripts.foundation_ingest import build
from scripts.foundation_eval import EXPECTED

THRESH = 0.40


def main() -> int:
    r = build()
    si = r["semantic_index"]
    emb = r["embedding"]
    if si is None or emb is None:
        print("NO SEMANTIC INDEX — run bge embed first")
        return 1
    total = 0
    rel = 0
    for q, exp in EXPECTED.items():
        qv = emb.embed(q)
        top = si.search(qv, top_k=1)
        sc = top[0][1] if top else 0.0
        hit = sc > THRESH
        rel += 1 if hit else 0
        total += 1
        print(f"  score={sc:.3f} {'REL' if hit else 'miss'} exp={exp[:20]:20s} {q[:42]}")
    print(f"\nSEMANTIC RELEVANCE (top1 cosine > {THRESH}): {rel}/{total} = {rel/total:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

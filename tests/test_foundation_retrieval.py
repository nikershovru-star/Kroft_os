"""STAGE 3 golden-regression: stock boot-path retrieves from foundation.

Verifies that `build_container` (the composition root used by main.py) loads
the KROFT Knowledge Foundation snapshot and that GraphQueryEngine answers a
known query from the 49 foundation PDFs.

SAFETY:
- Read-only. build_container() only LOADS the foundation snapshot via
  KnowledgeSnapshotStore.load(); it never writes to _snapshot.json.
- KROFT_SNAP (if set) points at an isolated copy so any stray autosave lands in
  a temp dir, never the production snapshot.
- No re-embed, no ingest, no snapshot mutation.

DETERMINISM: lexical retrieval (ContentIndex via GraphQueryEngine.search) is used
for the hard assertions because it needs no embedding server and is fully
deterministic. Semantic/hybrid retrieval requires a live Ollama bge-m3 endpoint;
those checks are skipped when it is unreachable so the test never hangs.
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from composition.container_builder import build_container  # noqa: E402


def _build():
    """Build a container against a temp vault (no production write)."""
    tmp = tempfile.mkdtemp(prefix="kroft_foundation_retrieval_")
    return build_container(tmp)


def test_foundation_loaded_into_stock_boot_path():
    """Foundation graph/index/vectors are present after stock boot build."""
    c = _build()
    gb = c.resolve("IGraphBuilder")
    graph = gb.get_graph()
    si = c.resolve("SemanticIndex")
    ci = c.resolve("ContentIndex")
    nodes = len(graph.get("nodes", []))
    edges = len(graph.get("edges", []))
    vecs = len(getattr(si, "_index", {}))
    docs = len(getattr(ci, "_doc_terms", {}))
    # Large non-zero foundation load proves integration (no hard-coded exact count).
    assert nodes > 1000, f"nodes too low: {nodes}"
    assert edges > 1000, f"edges too low: {edges}"
    assert vecs > 1000, f"vectors too low: {vecs}"
    assert docs > 1000, f"docs too low: {docs}"


def test_foundation_lexical_retrieval_finds_bacon():
    """ContentIndex (restored from snapshot) finds a Bacon foundation chunk.

    Lexical only (token 'idols') — no embedding server required, deterministic.
    """
    c = _build()
    engine = c.resolve("GraphQueryEngine")
    hits = engine.search("idols")
    assert hits, "lexical search returned nothing"
    bacon = [n for n in hits if "bacon" in str(n).lower()]
    assert bacon, f"no Bacon hit: {hits[:5]}"


def test_foundation_lexical_retrieval_finds_cybernetics():
    """ContentIndex finds Wiener's Cybernetics work node lexically (token)."""
    c = _build()
    engine = c.resolve("GraphQueryEngine")
    hits = engine.search("cybernetics")
    assert hits, "lexical search returned nothing"
    wiener = [n for n in hits if "wiener" in str(n).lower() or "cybernetics" in str(n).lower()]
    assert wiener, f"no Wiener/Cybernetics hit: {hits[:5]}"


def _ollama_available() -> bool:
    try:
        from adapters.ollama_embedding import OllamaEmbeddingAdapter
        _ = OllamaEmbeddingAdapter(model="bge-m3")
        _.embed("probe")
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _ollama_available(), reason="Ollama bge-m3 not reachable")
def test_foundation_semantic_retrieval_finds_bacon():
    """Semantic/hybrid retrieval finds Bacon when Ollama is live."""
    c = _build()
    engine = c.resolve("GraphQueryEngine")
    hits = engine.hybrid_search(
        "idols of the mind that distort human understanding", top_k=5)
    assert hits, "hybrid_search returned nothing"
    bacon = [n for n, _ in hits if "bacon" in n.lower()]
    assert bacon, f"no Bacon hit in top-5: {[n for n, _ in hits]}"

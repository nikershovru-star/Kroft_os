"""Slice: local OpenAI-compatible embedding adapter + kernel wiring (K5 reuse).

Proof (K5): ``OllamaEmbeddingAdapter`` implements the existing ``IEmbedding`` port and
routes through a local ``/v1/embeddings`` endpoint (Ollama/LM Studio) — no API key, no
external network. When the local server is unreachable, ``embed`` raises and the kernel's
retrieval degrades gracefully to keyword-overlap (no crash). Wiring flows
KroftConfig.embedding -> build_kernel(embedding=...) -> CognitiveKernel(embedding=...).

Deterministic portion (always runs):
- adapter import + port conformance;
- unreachable server -> embed raises (caller falls back);
- kernel wired with the adapter but server down -> _retrieve_similar_episodes does NOT
  raise and returns no episodes (graceful degradation to keyword path is the live kernel's
  job; here we assert the call is safe when the adapter itself errors).

Live portion (EMBED_LIVE=1): real Ollama embeddings find the synonym goal
"сохрани привет в файл" after "запиши hello в x.txt". Skipped without the flag or when
no local server/model is available.
"""

import os

import pytest

from contracts import IEmbedding
from adapters.ollama_embedding import OllamaEmbeddingAdapter


def test_adapter_implements_port_and_defaults():
    a = OllamaEmbeddingAdapter()
    assert isinstance(a, IEmbedding)
    assert a.base_url.endswith("/v1")
    # model default is the common local Ollama embedding model
    assert a.model


def test_unreachable_server_raises_gracefully():
    """No local server -> embed raises (kernel falls back to keyword-overlap)."""
    a = OllamaEmbeddingAdapter(base_url="http://127.0.0.1:9/v1")  # closed port
    with pytest.raises(Exception):
        a.embed("anything")


def test_kernel_wiring_carries_adapter():
    """KroftConfig.embedding 'auto' -> OllamaEmbeddingAdapter reaches the kernel."""
    from kernel.cognitive_kernel import build_kernel
    a = OllamaEmbeddingAdapter(base_url="http://127.0.0.1:9/v1")
    k = build_kernel(node_id="embed-wire", embedding=a)
    assert k._embedding is a


def test_retrieval_safe_when_adapter_errors():
    """Adapter errors during retrieval must NOT crash the kernel loop."""
    from kernel.cognitive_kernel import build_kernel
    from contracts.cognitive_domain import Episode, ConfidenceScore, Provenance, ProvenanceType
    a = OllamaEmbeddingAdapter(base_url="http://127.0.0.1:9/v1")  # will error on embed
    k = build_kernel(node_id="embed-safe", embedding=a)
    # seed an episode via the kernel's memory
    ep = Episode(id="e1", summary="exec:file:x.txt",
                 confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t"))
    k._memory.record_episode(ep)
    # retrieval must not raise even though the adapter is unreachable
    similar = k._retrieve_similar_episodes("сохрани привет в файл")
    assert isinstance(similar, list)  # graceful (likely empty; no crash)


def test_live_embedding_finds_synonyms():
    """EMBED_LIVE=1: real local embeddings retrieve the synonym episode."""
    if not os.environ.get("EMBED_LIVE"):
        pytest.skip("requires EMBED_LIVE=1 and a reachable local embedding server")
    from kernel.cognitive_kernel import build_kernel
    from contracts.cognitive_domain import Episode, ConfidenceScore, Provenance, ProvenanceType
    a = OllamaEmbeddingAdapter()  # default local endpoint
    # probe reachability before asserting
    try:
        a.embed("probe")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"local embedding server unreachable: {exc}")
    k = build_kernel(node_id="embed-live", embedding=a)
    ep = Episode(id="e1", summary="exec:file:x.txt",
                 confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                 provenance=Provenance(source="t", actor="t"))
    k._memory.record_episode(ep)
    similar = k._retrieve_similar_episodes("сохрани привет в файл")
    assert any(e.id == "e1" for e in similar), f"synonym episode not retrieved: {similar}"

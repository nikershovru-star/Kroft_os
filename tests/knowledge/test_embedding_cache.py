"""Slice: episode-embedding cache for retrieval (K5 reuse, perf).

Proof (K5): ``embed(ep.summary)`` must NOT be re-invoked on every retrieval when the
episode store is unchanged. CognitiveKernel caches summary -> vector (invalidated on
record_episode via the memory hook) and only calls the adapter for NEW summaries and
for a new query string. Query vectors are also cached per goal text.

Deterministic: a spy IEmbedding counts embed() calls.
- N episodes with the SAME summary -> embed(summary) called exactly ONCE (first retrieval).
- repeated retrieval with the same goal -> no new embed calls (cache hits).
- a new episode with a NEW summary -> embed called once more for that summary only.
"""

import hashlib

from contracts import IEmbedding
from contracts.cognitive_domain import Episode, ConfidenceScore, Provenance, ProvenanceType


class _SpyEmbedding(IEmbedding):
    """Counts embed() calls; returns a deterministic 8-dim vector from text hash."""

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, text: str):
        self.calls += 1
        h = hashlib.sha256((text or "").encode("utf-8")).digest()
        return [((h[i] / 255.0) * 2 - 1) for i in range(8)]


def _ep(eid: str, summary: str) -> Episode:
    return Episode(id=eid, summary=summary,
                   confidence=ConfidenceScore(0.9, ProvenanceType.RULE_INFERENCE),
                   provenance=Provenance(source="t", actor="t"))


def test_embed_called_once_per_unique_summary():
    from kernel.cognitive_kernel import build_kernel
    spy = _SpyEmbedding()
    k = build_kernel(node_id="cache", embedding=spy)
    # 5 episodes, identical summary -> only ONE unique summary to embed
    for i in range(5):
        k._memory.record_episode(_ep(f"e{i}", "exec:file:x.txt"))

    # first retrieval: embed the single unique summary + the query = 2 calls
    k._retrieve_similar_episodes("сохрани привет в файл")
    assert spy.calls == 2, f"expected 2 embed calls (1 summary + 1 query), got {spy.calls}"

    # repeated retrieval (same goal): cache hits -> NO new embed calls
    k._retrieve_similar_episodes("сохрани привет в файл")
    assert spy.calls == 2, f"cache should prevent re-embed, got {spy.calls}"
    k._retrieve_similar_episodes("сохрани привет в файл")
    assert spy.calls == 2, f"cache should prevent re-embed, got {spy.calls}"

    # a NEW episode invalidates the summary cache; next retrieval re-embeds the
    # (now-uncached) summaries but the query stays cached -> x.txt + y.txt = +2
    k._memory.record_episode(_ep("e5", "exec:file:y.txt"))
    k._retrieve_similar_episodes("сохрани привет в файл")
    assert spy.calls == 4, f"after invalidation: re-embed both summaries, got {spy.calls}"

    # subsequent retrieval after growth: cache hits again -> still 4
    k._retrieve_similar_episodes("сохрани привет в файл")
    assert spy.calls == 4, f"no re-embed after growth, got {spy.calls}"


def test_cache_invalidated_on_record_episode():
    """record_episode clears the summary cache so a brand-new retrieval re-embeds."""
    from kernel.cognitive_kernel import build_kernel
    spy = _SpyEmbedding()
    k = build_kernel(node_id="cache2", embedding=spy)
    k._memory.record_episode(_ep("a", "exec:file:x.txt"))
    k._retrieve_similar_episodes("goal one")  # embeds summary + query (2 calls)
    assert spy.calls == 2
    # a new episode invalidates the cache; next retrieval re-embeds the summary
    k._memory.record_episode(_ep("b", "exec:file:x.txt"))
    k._retrieve_similar_episodes("goal one")  # summary re-embedded (query cached) -> +1
    assert spy.calls == 3, f"invalidation should re-embed summary, got {spy.calls}"


def test_cache_getter_helpers():
    """Smoke: cache structures exist and are isolated per kernel instance."""
    from kernel.cognitive_kernel import build_kernel
    k1 = build_kernel(node_id="c-a", embedding=_SpyEmbedding())
    k2 = build_kernel(node_id="c-b", embedding=_SpyEmbedding())
    assert isinstance(k1._embedding_cache, dict)
    assert isinstance(k1._query_cache, dict)
    # independent caches
    k1._embedding_cache["x"] = [0.1]
    assert "x" not in k2._embedding_cache

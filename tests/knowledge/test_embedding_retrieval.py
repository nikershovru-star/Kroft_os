"""Slice: embedding-based episodic retrieval with keyword fallback (K5 reuse).

Proof (K5): searching past Episodes by MEANING, not keyword overlap. When an
``IEmbedding`` adapter is wired into ``CognitiveKernel``, ``_retrieve_similar_episodes``
scores by cosine similarity over ``Episode.summary`` embeddings — so a goal like
"сохрани привет в файл" finds the prior "запиши hello в x.txt" episode even though
they share NO keyword (hello/привет, запиши/сохрани are synonyms). When no adapter
is wired, it deterministically falls back to the original keyword-overlap path.

Reuses adapters.embedding.OpenAIEmbeddingAdapter (real semantic, gated on EMBED_LIVE
+ OPENAI_API_KEY) and the existing layered-memory Episode store. No new port/layer.
"""

import os
from typing import List

from contracts import IEmbedding

from composition.real_world_executor import RealWorldExecutor
from composition.run_kroft import KroftApp, KroftConfig


def _build_kernel(tmp_path, snapshot, embedding=None):
    """Build a CognitiveKernel with an optional embedding adapter via the public API.

    KroftApp wraps CognitiveKernel; we reach the kernel and re-instantiate it with
    the embedding wired (K3-clean: reuse public KroftApp + attach_executor).
    """
    app = KroftApp(KroftConfig(node_id="h1", llm="none", ticks=0,
                               vault=str(tmp_path / "vault"),
                               knowledge_snapshot=str(snapshot)))
    app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
    # re-wire the kernel with the embedding adapter (K5: constructor injection)
    from kernel.cognitive_kernel import CognitiveKernel
    kw = dict(
        world=app.kernel._world,
        attention=app.kernel._attention,
        resources=app.kernel._resources,
        values=app.kernel._values,
        decision=app.kernel._decision,
        executive=app.kernel._executive,
        learning=app.kernel._learning,
        planner=app.kernel._planner,
        clock=app.kernel._clock,
        reason=app.kernel._reason,
        world_model=app.kernel._world_model,
        memory_evolution=app.kernel._memory_evolution,
        memory=app.kernel._memory,
        reflection_engine=app.kernel._reflection_engine,
        embedding=embedding,
    )
    app.kernel = CognitiveKernel(**kw)
    app.kernel.attach_executor(RealWorldExecutor(base_dir=str(tmp_path)))
    return app


class _SynonymEmbedding(IEmbedding):
    """Test-only semantic-ish adapter: encodes the ACTION TYPE of a text.

    Not a production adapter (lives in the test). Proves the cosine path finds
    paraphrased episodes that share NO keyword but the SAME action type (file vs
    command) — something the keyword fallback cannot do. hello/привет and
    запиши/сохрани never appear in the lean episode summary (exec:file:x.txt),
    yet both goals are file-write intents and retrieve each other.
    """

    def embed(self, text: str) -> List[float]:
        t = (text or "").lower()
        if "file" in t or "файл" in t:
            return [1.0, 0.0, 0.0]
        if "command" in t or "команд" in t or "выполн" in t or "echo" in t:
            return [0.0, 1.0, 0.0]
        # stable pseudo-vector for anything else (keeps cosine deterministic)
        h = (hash(t) % 1000) / 1000.0
        return [0.0, 0.0, h]


def test_keyword_fallback_does_not_confuse_synonyms(tmp_path):
    """Offline: embedding=None -> keyword fallback. Synonyms share NO keyword,
    so the prior episode is NOT retrieved (deterministic, no false match)."""
    snap = tmp_path / "k.json"
    app = _build_kernel(tmp_path, snap, embedding=None)

    app.step("запиши hello в x.txt")
    # no embedding adapter -> fallback path; paraphrased goal shares no token>2
    similar = app.kernel._retrieve_similar_episodes("сохрани привет в файл")
    assert similar == [], "keyword fallback must NOT match synonyms"


def test_embedding_path_finds_synonyms(tmp_path):
    """With a semantic adapter wired, the paraphrased goal finds the prior episode
    via cosine similarity (no shared keywords)."""
    snap = tmp_path / "k.json"
    app = _build_kernel(tmp_path, snap, embedding=_SynonymEmbedding())

    app.step("запиши hello в x.txt")
    similar = app.kernel._retrieve_similar_episodes("сохрани привет в файл")
    assert similar, "embedding path must find the synonym episode"
    # the prior file-action episode is retrieved and folded into planning context
    app.step("сохрани привет в файл")
    plan = app.kernel._last_selected_plan
    assert any("past-experience" in s for s in plan.steps), plan.steps


def test_embedding_live_synonyms(tmp_path):
    """Gated on EMBED_LIVE=1 + OPENAI_API_KEY: real semantic adapter finds synonyms.

    Skips gracefully when the live embedding endpoint is unavailable (no key).
    """
    if not os.environ.get("EMBED_LIVE"):
        import pytest
        pytest.skip("requires live embedding (EMBED_LIVE=1 + OPENAI_API_KEY)")
    from adapters.embedding import OpenAIEmbeddingAdapter

    if not os.environ.get("OPENAI_API_KEY"):
        import pytest
        pytest.skip("OPENAI_API_KEY not set -> live embedding unavailable")

    snap = tmp_path / "k.json"
    app = _build_kernel(tmp_path, snap, embedding=OpenAIEmbeddingAdapter())

    app.step("запиши hello в x.txt")
    similar = app.kernel._retrieve_similar_episodes("сохрани привет в файл")
    assert similar, "live embedding must find the synonym episode"

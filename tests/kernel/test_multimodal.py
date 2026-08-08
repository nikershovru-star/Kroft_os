"""Tests for TZ-MULTIMODAL-001 (Multimodal Knowledge Engine, ADR-041).

Targets >=12 tests. Heavy deps (ollama/yt-dlp/whisper) are absent in CI, so we
test: (a) graceful degrade when unavailable, (b) pipeline orchestration with
fake IMultimodalParser adapters, (c) KG VIDEO/AUDIO/IMAGE node creation,
(d) negative proof-of-fire (K1/K8).
"""

import importlib.util
import pytest

from contracts.i_multimodal import IMultimodalParser, MediaKnowledge, MediaSegment, MediaSource
from contracts.knowledge_graph import EdgeType, IGraphEngine, Node, NodeType
from adapters.ollama_vision import OllamaVisionAdapter
from adapters.yt_dlp_transcript import YtDlpTranscriptAdapter
from services.media_intelligence import MediaIntelligenceService
from services.knowledge_graph.engine import InMemoryGraphEngine


class _FakeVision(IMultimodalParser):
    available = True

    def parse(self, source):
        if source.kind == "image":
            return MediaKnowledge("image caption", [MediaSegment(0, 0, "image caption", "visual")], source_kind="image")
        # video: simulate frame captions
        return MediaKnowledge("frame1. frame2.",
                               [MediaSegment(0, 1, "frame1", "visual"), MediaSegment(1, 2, "frame2", "visual")],
                               source_kind="video")


class _FakeTranscript(IMultimodalParser):
    available = True

    def parse(self, source):
        return MediaKnowledge("spoken text", [MediaSegment(0, 0, "spoken text", "speech")], source_kind="audio")


def test_port_contract():
    assert issubclass(OllamaVisionAdapter, IMultimodalParser)
    assert issubclass(YtDlpTranscriptAdapter, IMultimodalParser)


def test_vision_unavailable_graceful():
    # 'ollama' package not installed in CI -> available False -> RuntimeError
    a = OllamaVisionAdapter()
    assert a.available is False
    try:
        a.parse(MediaSource(kind="image", path="x.png"))
        assert False, "should raise"
    except RuntimeError as e:
        assert "unavailable" in str(e).lower()


def test_transcript_unavailable_graceful():
    # The adapter is available ONLY when yt-dlp is installed. Skip when it actually is
    # (then `available` is True by design); otherwise verify graceful degradation.
    if importlib.util.find_spec("yt_dlp") is not None:
        pytest.skip("yt-dlp installed -> adapter is available by design")
    a = YtDlpTranscriptAdapter()
    assert a.available is False
    try:
        a.parse(MediaSource(kind="youtube", url="http://x"))
        assert False, "should raise"
    except RuntimeError as e:
        assert "unavailable" in str(e).lower()


def test_service_video_ingest_creates_video_node():
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph, vision=_FakeVision(), transcript=_FakeTranscript())
    mk = svc.ingest(MediaSource(kind="video", path="clip.mp4", fps=1.0))
    assert "frame1" in mk.text
    nodes = graph.nodes()
    video_nodes = [n for n in nodes if n.type == NodeType.VIDEO]
    assert len(video_nodes) == 1
    # segments linked via CONTAINS
    edges = graph.edges()
    assert any(e.type == EdgeType.CONTAINS for e in edges)


def test_service_audio_ingest_creates_audio_node():
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph, vision=_FakeVision(), transcript=_FakeTranscript())
    mk = svc.ingest(MediaSource(kind="audio", path="talk.wav"))
    assert mk.segments[0].kind == "speech"
    audio_nodes = [n for n in graph.nodes() if n.type == NodeType.AUDIO]
    assert len(audio_nodes) == 1


def test_service_image_ingest_creates_image_node():
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph, vision=_FakeVision())
    svc.ingest(MediaSource(kind="image", path="pic.png"))
    image_nodes = [n for n in graph.nodes() if n.type == NodeType.IMAGE]
    assert len(image_nodes) == 1


def test_service_no_adapters_raises():
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph)  # vision/transcript None
    try:
        svc.ingest(MediaSource(kind="video", path="clip.mp4"))
        assert False, "should raise (no adapters)"
    except RuntimeError:
        pass


def test_service_blend_without_llm():
    # llm=None -> raw blend (no synthesis), still returns text
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph, vision=_FakeVision(), transcript=_FakeTranscript(), llm=None)
    mk = svc.ingest(MediaSource(kind="video", path="c.mp4"))
    assert mk.text  # non-empty raw blend


def test_kg_node_types_present():
    assert NodeType.VIDEO.value == "VIDEO"
    assert NodeType.AUDIO.value == "AUDIO"
    assert NodeType.IMAGE.value == "IMAGE"
    assert EdgeType.CONTAINS.value == "CONTAINS"


def test_negative_k1_port_clean():
    import inspect
    src = inspect.getsource(IMultimodalParser)
    assert "import services" not in src and "from services" not in src
    assert "import runtime" not in src and "from runtime" not in src
    assert "import adapters" not in src and "from adapters" not in src


def test_negative_k8_service_clean():
    import inspect
    src = inspect.getsource(MediaIntelligenceService)
    assert "import kernel" not in src and "from kernel" not in src
    assert "import runtime" not in src and "from runtime" not in src


def test_service_image_without_vision_raises():
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph)  # no vision adapter
    try:
        svc.ingest(MediaSource(kind="image", path="pic.png"))
        assert False, "should raise (no vision)"
    except RuntimeError:
        pass


def test_service_youtube_creates_video_node():
    graph = InMemoryGraphEngine()
    svc = MediaIntelligenceService(graph=graph, vision=_FakeVision(), transcript=_FakeTranscript())
    svc.ingest(MediaSource(kind="youtube", url="http://yt/x"))
    video_nodes = [n for n in graph.nodes() if n.type == NodeType.VIDEO]
    assert len(video_nodes) == 1

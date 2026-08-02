"""Media intelligence service (TZ-MULTIMODAL-001, ADR-041).

K8-compliant: services/ only, imports contracts + stdlib. Orchestrates the
grounding-in-text pipeline: audio->ASR (YtDlpTranscriptAdapter), video->
frames->Vision LLM (OllamaVisionAdapter via IExecutionSandbox ffmpeg), then
blends segments and synthesizes a summary via ILlm, and writes a VIDEO/AUDIO/
IMAGE node into the Knowledge Graph. K6: talks to adapters only through ports.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts.i_execution_sandbox import IExecutionSandbox
from contracts.i_llm import ILlm, ModelQuery
from contracts.i_multimodal import IMultimodalParser, MediaKnowledge, MediaSegment, MediaSource
from contracts.i_telemetry import ITelemetrySink
from contracts.knowledge_graph import Edge, EdgeType, IGraphEngine, Node, NodeType


class MediaIntelligenceService:
    """Ingests media into the Knowledge Graph as grounded text + typed node."""

    def __init__(
        self,
        graph: IGraphEngine,
        vision: Optional[IMultimodalParser] = None,
        transcript: Optional[IMultimodalParser] = None,
        sandbox: Optional[IExecutionSandbox] = None,
        llm: Optional[ILlm] = None,
        telemetry: Optional[ITelemetrySink] = None,
        logger: Any = None,
    ) -> None:
        self._graph = graph
        self._vision = vision
        self._transcript = transcript
        self._sandbox = sandbox
        self._llm = llm
        self._telemetry = telemetry
        self._log = logger

    # --- public API -------------------------------------------------------

    def ingest(self, source: MediaSource) -> MediaKnowledge:
        start = time.monotonic()
        try:
            if source.kind in ("audio", "youtube"):
                mk = self._ingest_audio(source)
            elif source.kind == "image":
                mk = self._ingest_image(source)
            else:  # video
                mk = self._ingest_video(source)
            self._write_node(source, mk)
            if self._telemetry is not None:
                self._telemetry.record("media_ingest.duration_ms", (time.monotonic() - start) * 1000,
                                        tags={"kind": source.kind})
            return mk
        except Exception as exc:
            if self._telemetry is not None:
                self._telemetry.record("media_ingest.errors", 1.0, tags={"kind": source.kind})
            if self._log:
                self._log.error("media.ingest.error", kind=source.kind, error=str(exc))
            raise

    # --- modality handlers ------------------------------------------------

    def _ingest_audio(self, source: MediaSource) -> MediaKnowledge:
        if self._transcript is None or not self._transcript.available:
            raise RuntimeError("No transcript adapter available for audio/youtube source.")
        return self._transcript.parse(source)

    def _ingest_image(self, source: MediaSource) -> MediaKnowledge:
        if self._vision is None or not self._vision.available:
            raise RuntimeError("No vision adapter available for image source.")
        return self._vision.parse(source)

    def _ingest_video(self, source: MediaSource) -> MediaKnowledge:
        if (self._transcript is None or not self._transcript.available) and \
           (self._vision is None or not self._vision.available):
            raise RuntimeError("No vision/transcript adapter available for video source.")
        segments: List[MediaSegment] = []
        # 1) audio -> speech text (if transcript adapter available)
        if self._transcript is not None and self._transcript.available and (source.path or source.url):
            try:
                audio_mk = self._transcript.parse(source)
                segments.extend(audio_mk.segments)
            except Exception as exc:
                if self._log:
                    self._log.warn("media.video.audio.skip", error=str(exc))
        # 2) video -> sampled frames -> vision (if vision adapter available)
        if self._vision is not None and self._vision.available and source.path:
            try:
                vision_mk = self._vision.parse(source)
                segments.extend(vision_mk.segments)
            except Exception as exc:
                if self._log:
                    self._log.warn("media.video.vision.skip", error=str(exc))
        # 3) blend + synthesize
        blended = self._blend(segments)
        return MediaKnowledge(text=blended, segments=segments,
                               metadata={"source": source.url or source.path, "fps": source.fps},
                               source_kind="video")

    # --- helpers ----------------------------------------------------------

    def _blend(self, segments: List[MediaSegment]) -> str:
        parts = [f"[{s.kind} {s.t_start:.0f}s] {s.text}" for s in segments]
        joined = "\n".join(parts)
        if self._llm is None:
            return joined  # raw blend without LLM synthesize
        try:
            resp = self._llm.complete(ModelQuery(
                prompt=f"Combine these media segments into a coherent summary:\n{joined}",
                max_tokens=512,
            ))
            return resp.text if resp.ok else joined
        except Exception:
            return joined

    def _write_node(self, source: MediaSource, mk: MediaKnowledge) -> None:
        node_type = {  # type: ignore[var-annotated]
            "video": NodeType.VIDEO, "youtube": NodeType.VIDEO,
            "audio": NodeType.AUDIO, "image": NodeType.IMAGE,
        }.get(source.kind, NodeType.VIDEO)
        node_id = f"{source.kind}:{source.url or source.path}"
        node = Node(id=node_id, type=node_type, label=node_id,
                    metadata={"text": mk.text[:500], "segments": len(mk.segments),
                              "source": source.url or source.path})
        self._graph.add_node(node)
        # link segments as child nodes via CONTAINS (lightweight)
        for i, seg in enumerate(mk.segments[:20]):
            seg_id = f"{node_id}#seg{i}"
            self._graph.add_node(Node(id=seg_id, type=NodeType.EXPERIMENT,
                                      label=f"segment {i}", metadata={"text": seg.text[:200]}))
            self._graph.add_edge(Edge(source_id=node_id, target_id=seg_id, type=EdgeType.CONTAINS))

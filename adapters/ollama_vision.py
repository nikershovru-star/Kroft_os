"""Ollama vision adapter (TZ-MULTIMODAL-001, ADR-041).

K8-compliant: lives in adapters/. Imports contracts + stdlib. The `ollama`
Python package is OPTIONAL and lazy-imported inside methods so the arch-gate
stays green even when the dep is absent. When unavailable, `available=False`
and calls raise a clear RuntimeError (graceful degrade, not silent).

Implements IMultimodalParser: image -> one MediaKnowledge; video -> frames
sampled via an injected IExecutionSandbox (ffmpeg) -> per-frame captions.
"""
from __future__ import annotations

import base64
import importlib.util
import os
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from contracts.i_execution_sandbox import IExecutionSandbox
from contracts.i_multimodal import IMultimodalParser, MediaKnowledge, MediaSegment, MediaSource


class OllamaVisionAdapter(IMultimodalParser):
    """Vision analysis via local Ollama (Qwen2.5-VL etc.)."""

    def __init__(
        self,
        model: str = "qwen2.5vl:7b",
        default_prompt: str = "Describe this media in detail.",
        sandbox: Optional[IExecutionSandbox] = None,
    ) -> None:
        self._model = model
        self._default_prompt = default_prompt
        self._sandbox = sandbox
        self._has_ollama = importlib.util.find_spec("ollama") is not None

    @property
    def available(self) -> bool:
        return self._has_ollama

    def _require(self) -> None:
        if not self._has_ollama:
            raise RuntimeError(
                f"OllamaVisionAdapter unavailable: 'ollama' package not installed. "
                f"Install it (pip install ollama) and pull {self._model} to enable vision."
            )

    def parse(self, source: MediaSource) -> MediaKnowledge:
        self._require()
        if source.kind == "image" and source.path:
            text = self._caption_image(source.path)
            return MediaKnowledge(text=text, segments=[MediaSegment(0.0, 0.0, text, "visual")],
                                  metadata={"path": source.path}, source_kind="image")
        if source.kind == "video" and source.path:
            return self._parse_video(source)
        raise ValueError(f"OllamaVisionAdapter cannot handle kind={source.kind} path={source.path}")

    def _caption_image(self, image_path: str, prompt: Optional[str] = None) -> str:
        import ollama  # lazy

        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        resp = ollama.chat(
            model=self._model,
            messages=[{"role": "user", "content": prompt or self._default_prompt, "images": [b64]}],
        )
        return resp["message"]["content"]

    def _parse_video(self, source: MediaSource) -> MediaKnowledge:
        frames = self._sample_frames(source)
        segments: List[MediaSegment] = []
        try:
            import ollama  # lazy

            for i, fp in enumerate(frames):
                b64 = base64.b64encode(Path(fp).read_bytes()).decode()
                resp = ollama.chat(
                    model=self._model,
                    messages=[{"role": "user", "content": "Describe this frame.", "images": [b64]}],
                )
                t = float(i) / max(source.fps, 0.01)
                segments.append(MediaSegment(t, t + 1.0 / max(source.fps, 0.01), resp["message"]["content"], "visual"))
        finally:
            for f in frames:
                try:
                    os.remove(f)
                except OSError:
                    pass
        text = "\n".join(f"[{s.kind} {s.t_start:.1f}s] {s.text}" for s in segments)
        return MediaKnowledge(text=text, segments=segments, metadata={"path": source.path, "fps": source.fps},
                               source_kind="video")

    def _sample_frames(self, source: MediaSource) -> List[str]:
        if self._sandbox is None:
            return []
        frames_dir = Path(tempfile.mkdtemp(prefix="kroft_frames_"))
        pattern = str(frames_dir / "frame_%04d.jpg")
        res = self._sandbox.execute(
            ["ffmpeg", "-y", "-i", source.path, "-vf", f"fps={source.fps}", pattern],
            timeout_sec=120.0,
        )
        if res.returncode != 0:
            return []
        return [str(f) for f in sorted(frames_dir.glob("*.jpg"))]

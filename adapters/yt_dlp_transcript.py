"""YouTube / audio transcript adapter (TZ-MULTIMODAL-001, ADR-041).

K8-compliant: lives in adapters/. yt-dlp + whisper are OPTIONAL and lazy-imported
inside methods; arch-gate stays green without them. When absent, `available=False`.
Implements IMultimodalParser: audio/youtube -> MediaKnowledge (speech text).
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from typing import Optional

from contracts.i_multimodal import IMultimodalParser, MediaKnowledge, MediaSegment, MediaSource


class YtDlpTranscriptAdapter(IMultimodalParser):
    """Audio -> text via yt-dlp (download) + whisper (transcribe)."""

    def __init__(self, whisper_model: str = "medium", timeout_sec: float = 300.0) -> None:
        self._whisper_model = whisper_model
        self._timeout = timeout_sec
        self._has_ytdlp = importlib.util.find_spec("yt_dlp") is not None
        self._has_whisper = (
            importlib.util.find_spec("faster_whisper") is not None
            or importlib.util.find_spec("whisper") is not None
        )

    @property
    def available(self) -> bool:
        return self._has_ytdlp and self._has_whisper

    def _require(self) -> None:
        if not self.available:
            missing = []
            if not self._has_ytdlp:
                missing.append("yt-dlp")
            if not self._has_whisper:
                missing.append("faster-whisper/openai-whisper")
            raise RuntimeError(f"YtDlpTranscriptAdapter unavailable: missing {', '.join(missing)}.")

    def parse(self, source: MediaSource) -> MediaKnowledge:
        """Download (if url) + transcribe (if local/downloaded audio) -> text."""
        self._require()
        path = source.path
        if source.url:
            path = self._download(source.url)
        elif path is None:
            raise ValueError("YtDlpTranscriptAdapter needs source.path or source.url")
        text = self._transcribe(path)
        segments = [MediaSegment(t_start=0.0, t_end=0.0, text=text, kind="speech")]
        return MediaKnowledge(
            text=text, segments=segments,
            metadata={"source": source.url or path, "kind": source.kind},
            source_kind="audio",
        )

    def _download(self, url: str) -> str:
        import yt_dlp  # lazy

        out_dir = tempfile.mkdtemp(prefix="kroft_media_")
        out_tmpl = str(Path(out_dir) / "%(id)s.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_tmpl,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".wav"
        return downloaded

    def _transcribe(self, audio_path: str) -> str:
        if importlib.util.find_spec("faster_whisper") is not None:
            from faster_whisper import WhisperModel

            model = WhisperModel(self._whisper_model, device="auto")
            segs, _ = model.transcribe(audio_path)
            return " ".join(s.text for s in segs)
        import whisper  # lazy

        model = whisper.load_model(self._whisper_model)
        result = model.transcribe(audio_path)
        return result["text"]

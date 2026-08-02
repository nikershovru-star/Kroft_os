"""Multimodal parser port (TZ-MULTIMODAL-001, ADR-041, RFC-013).

K1-compliant: stdlib only. Turns video/audio/image into grounded text
(MediaKnowledge) for ingestion into the Knowledge Graph as VIDEO/AUDIO/IMAGE
nodes. Heavy model deps live in adapters (optional, lazy-imported) — not here.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MediaSource:
    """A media item to parse."""

    kind: str  # "video" | "audio" | "image" | "youtube"
    path: Optional[str] = None  # local file path
    url: Optional[str] = None  # remote (youtube) url
    fps: float = 1.0  # frame sampling rate for video


@dataclass
class MediaSegment:
    """One timestamped chunk of grounded text."""

    t_start: float
    t_end: float
    text: str
    kind: str = "speech"  # "speech" | "visual"


@dataclass
class MediaKnowledge:
    """Grounded common-modality representation of a media item."""

    text: str
    segments: List[MediaSegment] = field(default_factory=list)
    metadata: Dict[str, object] = field(default_factory=dict)
    source_kind: str = "video"


class IMultimodalParser(ABC):
    """Parses media into MediaKnowledge (text-grounded)."""

    @abstractmethod
    def parse(self, source: MediaSource) -> MediaKnowledge:
        ...

    @property
    def available(self) -> bool:
        """Whether the underlying model/dep is usable in this environment."""
        return True

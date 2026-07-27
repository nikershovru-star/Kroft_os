"""KnowledgeOS v5 adapters — concrete port implementations."""
from .filesystem_adapter import LocalFileSystemAdapter
from .embedding import MockEmbeddingAdapter, OpenAIEmbeddingAdapter
from .desktop_adapter import MockDesktopAdapter, PyAutoGUIAdapter

__all__ = [
    "LocalFileSystemAdapter",
    "MockEmbeddingAdapter",
    "OpenAIEmbeddingAdapter",
    "MockDesktopAdapter",
    "PyAutoGUIAdapter",
]

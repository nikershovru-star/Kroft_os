"""KROFT_OS v5 adapters — concrete port implementations."""
from .filesystem_adapter import LocalFileSystemAdapter
from .embedding import MockEmbeddingAdapter, OpenAIEmbeddingAdapter
from .desktop_adapter import MockDesktopAdapter, PyAutoGUIAdapter
from .agent_adapter import RuleBasedAgentAdapter

__all__ = ["LocalFileSystemAdapter", "MockEmbeddingAdapter", "OpenAIEmbeddingAdapter",
           "MockDesktopAdapter", "PyAutoGUIAdapter", "RuleBasedAgentAdapter"]

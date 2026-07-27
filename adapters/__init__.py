"""KnowledgeOS v5 adapters — concrete port implementations."""
from .filesystem_adapter import LocalFileSystemAdapter
from .embedding import MockEmbeddingAdapter, OpenAIEmbeddingAdapter

__all__ = ["LocalFileSystemAdapter", "MockEmbeddingAdapter", "OpenAIEmbeddingAdapter"]

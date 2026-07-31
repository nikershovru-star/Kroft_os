"""KnowledgeOS v5 contracts (ports).

Abstract interfaces that define the system's hexagonal boundaries.
"""
from .i_service import IService
from .i_file_system import IFileSystem
from .i_event_bus import IEventBus
from .i_capability_registry import ICapabilityRegistry
from .igraph_builder import IGraphBuilder
from .igraph_query import IGraphQuery
from .snapshotable import ISnapshotable
from .plugin import IPlugin
from .embedding import IEmbedding
from .desktop import IDesktop
from .agent import IAgent, Tool
from .i_llm import ILlm, IModelMetadata, IHealth, ModelQuery, LlmResponse, ModelInfo
from .model_registry import ModelRegistry

__all__ = [
    "IService",
    "IFileSystem",
    "IEventBus",
    "ICapabilityRegistry",
    "IGraphBuilder",
    "IGraphQuery",
    "ISnapshotable",
    "IPlugin",
    "IEmbedding",
    "IDesktop",
    "IAgent",
    "Tool",
    "ILlm",
    "IModelMetadata",
    "IHealth",
    "ModelQuery",
    "LlmResponse",
    "ModelInfo",
    "ModelRegistry",
]

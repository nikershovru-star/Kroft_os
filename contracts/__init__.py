"""KROFT_OS v5 contracts (ports).

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
from .i_policy import IPolicy, PolicyContext, PolicyDecision, CallRecord
from .i_eval import IEvaluator, IBenchmark, IScorecard, Task, Metric, Scorecard, TaskCategory
from .i_knowledge import (
    IKnowledgeGraph,
    IEntityExtractor,
    IValidator,
    IFactChecker,
    Entity,
    Relation,
    Hypothesis,
    Fact,
    IngestReport,
)
from .i_memory import (
    IMemoryStore,
    ISemanticMemory,
    IProceduralMemory,
    MemoryItem,
    MemoryQuery,
    MemoryKind,
    ConsolidationReport,
)
from .i_workflow import (
    IPlanner,
    IExecutor,
    IReflection,
    IRetryManager,
    Workflow,
    Step,
    StepStatus,
    WorkflowStatus,
    RouterFn,
)
from .i_learning import (
    ExecutionTrace,
    StepTrace,
    Pattern,
    ILearningStore,
    IPatternExtractor,
)
from .i_optimization import (
    Recommendation,
    GuardrailResult,
    IOptimizer,
    IGuardrail,
)
from .i_autonomy import (
    EvaluationReport,
    DocSyncResult,
    IAutonomyController,
    ISelfEvaluator,
    IDocMaintainer,
)
from .i_agent_platform import (
    IAgentPlatform,
    AgentResult,
    AgentStatus,
)
from .i_kernel import IKernel, LifecycleState
from .i_process import IProcess, IProcessRegistry, ProcessStatus

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
    "IPolicy",
    "PolicyContext",
    "PolicyDecision",
    "CallRecord",
    "IEvaluator",
    "IBenchmark",
    "IScorecard",
    "Task",
    "Metric",
    "Scorecard",
    "TaskCategory",
    "IKnowledgeGraph",
    "IEntityExtractor",
    "IValidator",
    "IFactChecker",
    "Entity",
    "Relation",
    "Hypothesis",
    "Fact",
    "IngestReport",
    "IMemoryStore",
    "ISemanticMemory",
    "IProceduralMemory",
    "ExecutionTrace",
    "StepTrace",
    "Pattern",
    "ILearningStore",
    "IPatternExtractor",
    "Recommendation",
    "GuardrailResult",
    "IOptimizer",
    "IGuardrail",
    "EvaluationReport",
    "DocSyncResult",
    "IAutonomyController",
    "ISelfEvaluator",
    "IDocMaintainer",
    "MemoryItem",
    "MemoryQuery",
    "MemoryKind",
    "ConsolidationReport",
    "IPlanner",
    "IExecutor",
    "IReflection",
    "IRetryManager",
    "Workflow",
    "Step",
    "StepStatus",
    "WorkflowStatus",
    "RouterFn",
    "IAgentPlatform",
    "AgentResult",
    "AgentStatus",
    "IKernel",
    "LifecycleState",
    "IProcess",
    "IProcessRegistry",
    "ProcessStatus",
]

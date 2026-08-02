"""composition/container_builder.py — DI container factory (Composition Root).

Перенесено из main.py (Phase B.1). Единственное место, где регистрируются
конкретные адаптеры/сервисы. cli/ и kernel/ резолвят по имени — НЕ импортируют
adapters напрямую (arch-gate K1/K6).

He imports concrete `infrastructure` only for the container class + its
implementations (DependencyContainer, InMemoryGraphBuilder, InMemoryEventBus,
StateRepository, PluginLoader) — это Composition Root, вне арх-гейта.
"""
from __future__ import annotations
import os as _os

from infrastructure import (
    DependencyContainer,
    InMemoryGraphBuilder,
    InMemoryEventBus,
    PluginLoader,
)
from runtime import CapabilityRegistry
from adapters import LocalFileSystemAdapter
from adapters.exporters import export_dot, export_json, export_gexf
from adapters.file_watcher import FileWatcher
from adapters.http_server import KROFT_OSServer
from adapters.embedding import MockEmbeddingAdapter

from services import (
    VaultStreamCrawler, GraphQueryEngine, CrawlStateTracker, ContentIndex,
    WatchService, SemanticIndex, DesktopService, DesktopOrchestrator,
    ToolRegistry, AgentService, SchedulerService, SessionStore,
)
from adapters.desktop_adapter import MockDesktopAdapter
from adapters.agent_adapter import RuleBasedAgentAdapter
from adapters.subprocess_sandbox import SubprocessSandbox
from adapters.in_memory_telemetry import InMemoryTelemetrySink
from adapters.ollama_vision import OllamaVisionAdapter
from adapters.yt_dlp_transcript import YtDlpTranscriptAdapter
from services.media_intelligence import MediaIntelligenceService
from services.architecture_intelligence import (
    ArchitectureSimulator, TechDebtEngine, EvolutionEngine,
)
from kernel.security.approval_manager import ApprovalManager
from services.alert_engine import AlertEngine


def build_container(vault_path: str, loader=None, desktop_adapter: str = "mock") -> DependencyContainer:
    """Composition root: register ports + concrete adapters + services."""
    c = DependencyContainer()
    c.register_instance("IFileSystem", LocalFileSystemAdapter(vault_path))
    c.register_instance("IEventBus", InMemoryEventBus())
    c.register_instance("IGraphBuilder", InMemoryGraphBuilder())
    # TZ-MULTIMODAL-001 / ADR-041: Knowledge Graph v2 engine (VIDEO_NODE sink).
    from services.knowledge_graph.engine import InMemoryGraphEngine
    c.register_instance("IGraphEngine", InMemoryGraphEngine())
    c.register_instance("ICapabilityRegistry", CapabilityRegistry())
    # Phase B.3: state repository (IStateRepository impl) wired here.
    from infrastructure.state_repository import StateRepository
    c.register_instance("IStateRepository", StateRepository(c.resolve("IFileSystem"),
                                                            "data/state.json"))
    c.register_instance("ContentIndex", ContentIndex())
    c.register_instance("SemanticIndex", SemanticIndex())
    data_dir = _os.path.join(vault_path, ".kos")
    c.register_instance("SessionStore", SessionStore(
        persistence_path=_os.path.join(data_dir, "session.json"),
    ))
    c.register_instance("Embedding", MockEmbeddingAdapter())
    # TZ-EXECUTION-001 / ADR-039: subprocess sandbox as the IExecutionSandbox impl.
    bus = c.resolve("IEventBus")
    sandbox = SubprocessSandbox(default_timeout=30.0, bus=bus)
    c.register_instance("IExecutionSandbox", sandbox)
    # TZ-OBS-001 / ADR-040: telemetry sink + alert engine on the event bus.
    telemetry = InMemoryTelemetrySink(capacity=2000)
    c.register_instance("ITelemetrySink", telemetry)
    alert_log = _os.path.join(vault_path, ".kos", "alerts.log")
    c.register_factory(
        "AlertEngine",
        lambda: AlertEngine(bus, telemetry, alert_log_path=alert_log),
    )
    # TZ-MULTIMODAL-001 / ADR-041: vision + transcript adapters + media service.
    vision = OllamaVisionAdapter(model="qwen2.5vl:7b", sandbox=sandbox)
    c.register_instance("IVisionParser", vision)  # optional; available only if ollama + model present
    transcript = YtDlpTranscriptAdapter()
    c.register_instance("ITranscriptParser", transcript)  # optional; available only if yt-dlp+whisper present
    c.register_factory(
        "MediaIntelligenceService",
        lambda: MediaIntelligenceService(
            graph=c.resolve("IGraphEngine"),
            vision=vision if vision.available else None,
            transcript=transcript if transcript.available else None,
            sandbox=sandbox,
            llm=None,  # LLM not wired in build_container; _blend degrades to raw blend
            telemetry=telemetry,
        ),
    )
    # WP-12 / ADR-042: Architecture Intelligence (L5/L6/L7) on AKB + telemetry.
    akb_path = _os.path.join(vault_path, "docs", "architecture", "AKB")
    c.register_factory("ArchitectureSimulator", lambda: ArchitectureSimulator(sandbox=sandbox))
    c.register_factory("TechDebtEngine", lambda: TechDebtEngine(akb_path=akb_path, telemetry=telemetry))
    c.register_factory(
        "EvolutionEngine",
        lambda: EvolutionEngine(akb_path=akb_path, telemetry=telemetry,
                                debt_engine=c.resolve("TechDebtEngine")),
    )
    if desktop_adapter == "pyautogui":
        from adapters.desktop_adapter import PyAutoGUIAdapter
        c.register_instance("IDesktop", PyAutoGUIAdapter(sandbox=sandbox))
    else:
        c.register_instance("IDesktop", MockDesktopAdapter())
    c.register_factory(
        "ToolRegistry",
        lambda: ToolRegistry(sandbox=c.resolve("IExecutionSandbox"),
                             approval=ApprovalManager()),
    )
    c.register_factory(
        "DesktopService",
        lambda: DesktopService(c.resolve("IDesktop")),
    )
    c.register_factory(
        "DesktopOrchestrator",
        lambda: DesktopOrchestrator(
            c.resolve("GraphQueryEngine"),
            c.resolve("DesktopService"),
            c.resolve("IFileSystem"),
            vault_path,
        ),
    )
    c.register_factory("AgentService", lambda: _wire_agent(c))
    c.register_factory("IAgent", lambda: RuleBasedAgentAdapter(c.resolve("AgentService")))
    c.register_factory(
        "CrawlStateTracker",
        lambda: CrawlStateTracker(c.resolve("IFileSystem"), ".crawl_state.json"),
    )
    c.register_factory(
        "VaultStreamCrawler",
        lambda: VaultStreamCrawler(
            c.resolve("IFileSystem"), c.resolve("IEventBus"), c.resolve("IGraphBuilder"),
            vault_path, tracker=c.resolve("CrawlStateTracker"),
            index=c.resolve("ContentIndex"), semantic_index=c.resolve("SemanticIndex"),
            embedding=c.resolve("Embedding"),
        ),
    )
    c.register_factory(
        "GraphQueryEngine",
        lambda: GraphQueryEngine(
            c.resolve("IGraphBuilder"), index=c.resolve("ContentIndex"),
            semantic_index=c.resolve("SemanticIndex"), embedding=c.resolve("Embedding"),
            fs=c.resolve("IFileSystem"),
            snapshot_path=_os.path.join(vault_path, ".kos", "graph.json"),
        ),
    )
    c.register_instance("export_dot", export_dot)
    c.register_instance("export_json", export_json)
    c.register_instance("export_gexf", export_gexf)
    c.register_factory("FileWatcher", lambda: FileWatcher(vault_path, interval=2.0))
    c.register_factory(
        "WatchService",
        lambda: WatchService(
            c.resolve("VaultStreamCrawler"), c.resolve("FileWatcher"), kernel=None,
        ),
    )
    c.register_factory(
        "KROFT_OSServer",
        lambda: KROFT_OSServer(c, host="127.0.0.1", port=8080),
    )
    c.register_instance("PluginLoader", loader)
    if loader is not None:
        loader.apply_exporters(c)
    sched = SchedulerService(
        persistence_path=_os.path.join(data_dir, "scheduler.json"),
        log_path=_os.path.join(data_dir, "scheduler.log"),
    )
    c.register_instance("SchedulerService", sched)
    _wire_scheduler(c)
    return c


def _wire_agent(container: DependencyContainer) -> AgentService:
    """Register all available tools in the ToolRegistry and return AgentService."""
    registry: ToolRegistry = container.resolve("ToolRegistry")
    engine: GraphQueryEngine = container.resolve("GraphQueryEngine")
    orch: DesktopOrchestrator = container.resolve("DesktopOrchestrator")
    desktop: DesktopService = container.resolve("DesktopService")

    registry.register("list_notes", lambda query, top_k: orch.list_notes(query, top_k),
                      "List note candidates via hybrid search")
    registry.register("open_note", lambda query, top_k: orch.open_note(query, top_k),
                      "Open top-1 note via hybrid search")
    registry.register("most_central", lambda: engine.centrality(),
                      "Return centrality metrics for all nodes")
    registry.register("list_orphans", lambda: engine.search("is:orphan"), "List orphan nodes")

    def _export_graph(fmt: str):
        g = container.resolve("IGraphBuilder").get_graph()
        if fmt == "dot":
            return container.resolve("export_dot")(g)
        elif fmt == "json":
            return container.resolve("export_json")(g)
        elif fmt == "gexf":
            return container.resolve("export_gexf")(g)
        return {"error": f"unknown format {fmt}"}
    registry.register("export_graph", _export_graph, "Export graph to dot/json/gexf")
    registry.register("export_format", _export_graph, "Export graph as dot/json/gexf")

    registry.register("screenshot", lambda: {"size": len(desktop.capture_screen())},
                      "Capture screen and return PNG size")
    registry.register("cursor_position",
                      lambda: {"x": desktop.where_is_cursor()[0], "y": desktop.where_is_cursor()[1]},
                      "Return cursor coordinates")
    registry.register("desktop_click",
                      lambda x, y: (desktop.click_at(int(x), int(y)) or {"ok": True, "x": int(x), "y": int(y)}),
                      "Click at screen (x, y)")
    registry.register("desktop_type", lambda text: (desktop.type_text(text) or {"ok": True}),
                      "Type text via keyboard")
    registry.register("desktop_open_app", lambda name: (desktop.launch(name) or {"ok": True, "app": name}),
                      "Open an application by name")

    def _capabilities():
        return {
            "actions": ["find", "open", "show", "export", "desktop", "schedule", "centrality", "orphan"],
            "hint": "Try: find <topic>, open <file>, show <topic>, export <dot|json|gexf>, "
                    "desktop cursor|screenshot|click x y|type <text>|open_app <name>",
        }
    registry.register("capabilities", _capabilities, "List available agent actions")
    registry.register("show_note", lambda query, top_k=1: orch.show_note(query, top_k),
                      "Show top note content inline")

    def _graph_neighbors(query: str, direction: str = "both", depth: int = 1):
        results = engine.hybrid_search(query, top_k=1)
        if not results:
            return {"error": "no results", "query": query}
        nid = results[0][0]
        return {"ok": True, "node": nid, "neighbors": engine.get_neighbors(nid, direction, depth)}
    registry.register("graph_neighbors", _graph_neighbors, "Graph neighbors of a note")

    def _graph_path(from_query: str, to_query: str):
        a = engine.hybrid_search(from_query, top_k=1)
        b = engine.hybrid_search(to_query, top_k=1)
        if not a or not b:
            return {"error": "node not found"}
        path = engine.shortest_path(a[0][0], b[0][0])
        return {"ok": True, "from": a[0][0], "to": b[0][0], "path": path,
                "length": len(path) - 1 if path else -1}
    registry.register("graph_path", _graph_path, "Shortest path between two notes")

    def _graph_cluster(query: str, k: int = 5):
        results = engine.hybrid_search(query, top_k=1)
        if not results:
            return {"error": "no results", "query": query}
        return {"ok": True, "node": results[0][0], "cluster": engine.get_cluster(results[0][0], k)}
    registry.register("graph_cluster", _graph_cluster, "Personalized PageRank cluster around a note")

    def _graph_link(from_query: str, to_query: str, relation: str = "links"):
        return engine.add_link(from_query, to_query, relation)
    registry.register("graph_link", _graph_link, "Create a link between two notes")

    def _graph_unlink(from_query: str, to_query: str):
        return engine.remove_link(from_query, to_query)
    registry.register("graph_unlink", _graph_unlink, "Remove a link between two notes")

    def _graph_tag(query: str, tag: str):
        return engine.add_tag(query, tag)
    registry.register("graph_tag", _graph_tag, "Add a tag to a note")

    def _graph_untag(query: str, tag: str):
        return engine.remove_tag(query, tag)
    registry.register("graph_untag", _graph_untag, "Remove a tag from a note")

    def _graph_suggest(query: str, top_k: int = 5):
        results = engine.suggest_links(query, top_k=top_k)
        return {"ok": True, "query": query, "suggestions": results}
    registry.register("graph_suggest", _graph_suggest, "Suggest missing links for a note")

    def _graph_stats():
        return engine.graph_stats()
    registry.register("graph_stats", _graph_stats, "Graph statistics")

    def _graph_orphans():
        return {"ok": True, "orphans": engine.orphan_nodes()}
    registry.register("graph_orphans", _graph_orphans, "List orphan notes")

    def _graph_central(k: int = 5):
        return {"ok": True, "top": engine.top_central(k=k)}
    registry.register("graph_central", _graph_central, "Top central notes by pagerank/degree")

    def _graph_health():
        return engine.graph_health()
    registry.register("graph_health", _graph_health, "Graph health check")

    def _save_graph():
        return engine.save_graph()
    registry.register("save_graph", _save_graph, "Explicitly persist graph to disk")

    def _auto_save(enabled: bool):
        engine.set_auto_snapshot(enabled)
        return engine.auto_snapshot_status()
    registry.register("auto_save", _auto_save, "Toggle auto-snapshot after mutations")

    def _enhanced_search(query: str):
        results = engine.graph_enhanced_search(query)
        return {"ok": True, "query": query, "count": len(results), "results": results}
    registry.register("enhanced_search", _enhanced_search, "Graph-enhanced hybrid search")

    def _validate_graph():
        return engine.validate_graph()
    registry.register("validate_graph", _validate_graph, "Validate graph constraints")

    def _find_broken_links():
        return {"ok": True, "broken": engine.find_broken_links()}
    registry.register("find_broken_links", _find_broken_links, "Find edges pointing to missing nodes")

    def _fix_graph():
        return engine.fix_graph()
    registry.register("fix_graph", _fix_graph, "Auto-fix graph issues (tag orphans, remove broken links)")

    def _review_queue(top_k: int = 10):
        return {"ok": True, "queue": engine.review_queue(top_k=top_k)}
    registry.register("review_queue", _review_queue, "Prioritized review queue")

    def _compound_query(**filters):
        return {"ok": True, "matches": engine.compound_query(**filters)}
    registry.register("compound_query", _compound_query, "Compound graph query")

    def _audit_log():
        return {"ok": True, "log": engine.get_audit_log()}
    registry.register("audit_log", _audit_log, "Show graph temporal audit log")

    def _recent_changes():
        return {"ok": True, "log": engine.get_audit_log()[-10:]}
    registry.register("recent_changes", _recent_changes, "Show recent graph changes")

    def _mutations_since(ts_min: float):
        return {"ok": True, "mutations": engine.mutations_since(ts_min)}
    registry.register("mutations_since", _mutations_since, "Graph mutations since timestamp")

    def _research_topic(query: str):
        return engine.research_topic(query)
    registry.register("research_topic", _research_topic, "Research a topic through the knowledge graph")

    def _bridge_topics(from_query: str, to_query: str):
        return engine.bridge_topics(from_query, to_query)
    registry.register("bridge_topics", _bridge_topics, "Bridge two topics via shortest path or common neighbors")

    def _expand_knowledge(query: str):
        return engine.expand_knowledge(query)
    registry.register("expand_knowledge", _expand_knowledge, "Expand knowledge from a seed via cluster analysis")

    def _record_user_query(session_id: str, query_text: str, hit_nodes: list, intent: str = "unknown"):
        return engine.record_user_query(session_id, query_text, hit_nodes, intent)
    registry.register("record_user_query", _record_user_query, "Record user query into graph context memory")

    def _get_session_context(session_id: str, depth: int = 2):
        return engine.get_session_context(session_id, depth)
    registry.register("get_session_context", _get_session_context, "Retrieve session context from graph memory")

    def _suggest_next(session_id: str, top_n: int = 3):
        return engine.suggest_next(session_id, top_n)
    registry.register("suggest_next", _suggest_next, "Proactive suggestions based on interest graph")

    def _get_personalized_summary(session_id: str, target_node: str):
        return engine.get_personalized_summary(session_id, target_node)
    registry.register("get_personalized_summary", _get_personalized_summary, "Personalized node summary")

    def _graph_health_report():
        return engine.graph_health_report()
    registry.register("graph_health_report", engine.graph_health_report, "Full graph health diagnostic")

    def _find_duplicate_candidates(threshold: float = 0.8):
        return engine.find_duplicate_candidates(threshold)
    registry.register("find_duplicate_candidates", _find_duplicate_candidates, "Find duplicate node candidates")

    def _cleanup_orphans(dry_run: bool = True):
        return engine.cleanup_orphans(dry_run)
    registry.register("cleanup_orphans", _cleanup_orphans, "Remove orphaned content nodes")

    def _merge_nodes(from_node: str, to_node: str, dry_run: bool = True):
        return engine.merge_nodes(from_node, to_node, dry_run)
    registry.register("merge_nodes", _merge_nodes, "Merge two graph nodes into one")

    registry.register("find_hidden_connections", engine.find_hidden_connections, "Find hidden connections in graph")
    registry.register("apply_suggested_link", engine.apply_suggested_link, "Apply a suggested link between nodes")
    registry.register("query_dsl", engine.query_dsl, "Execute a graph query DSL statement")
    registry.register("rebuild_semantic_index", engine.rebuild_semantic_index, "Rebuild the semantic search index")
    registry.register("semantic_search", engine.semantic_search, "Semantic search across graph nodes")
    registry.register("semantic_similarity", engine.semantic_similarity, "Compute semantic similarity between nodes")
    registry.register("run_maintenance_cycle", engine.run_maintenance_cycle, "Run graph maintenance cycle")
    registry.register("get_maintenance_history", engine.get_maintenance_history, "Get graph maintenance history")
    registry.register("configure_maintenance", engine.configure_maintenance, "Configure graph maintenance settings")

    def _set_user_context(user_id: str, session_id: str):
        return engine.set_user_context(user_id, session_id)
    registry.register("set_user_context", _set_user_context, "Bind session to user")

    def _get_user_context(user_id: str):
        return engine.get_user_context(user_id)
    registry.register("get_user_context", _get_user_context, "Get unified user context")

    def _share_session(from_user: str, to_user: str, session_id: str):
        return engine.share_session(from_user, to_user, session_id)
    registry.register("share_session", _share_session, "Share session with another user")

    def _revoke_session(user_id: str, session_id: str):
        return engine.revoke_session(user_id, session_id)
    registry.register("revoke_session", _revoke_session, "Revoke session access")

    session = container.resolve("SessionStore")
    loader = container.try_resolve("PluginLoader")
    if loader is not None:
        agent = AgentService(registry, session_store=session)
        loader.apply_agent_extensions(registry, agent)
        return agent
    return AgentService(registry, session_store=session)


def _wire_scheduler(container: DependencyContainer) -> None:
    """Wire the scheduler's executor to the Hermes agent (composition root only)."""
    sched: SchedulerService = container.resolve("SchedulerService")
    agent = container.resolve("IAgent")
    sched.set_executor(lambda cmd: agent.execute(cmd))

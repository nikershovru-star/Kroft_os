"""KnowledgeOS v5 services — application layer."""
from .vault_stream_crawler import VaultStreamCrawler
from .graph_query_engine import GraphQueryEngine
from .incremental_tracker import CrawlStateTracker
from .content_index import ContentIndex
from .watch_service import WatchService
from .auth_service import SimpleAuthService
from .semantic_index import SemanticIndex
from .desktop_service import DesktopService

__all__ = [
    "VaultStreamCrawler",
    "GraphQueryEngine",
    "CrawlStateTracker",
    "ContentIndex",
    "WatchService",
    "SimpleAuthService",
    "SemanticIndex",
    "DesktopService",
]

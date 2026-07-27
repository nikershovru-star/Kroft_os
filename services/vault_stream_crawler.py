"""VaultStreamCrawler — first application-layer IService.

Walks an Obsidian Vault via the injected IFileSystem port, extracts
wiki-links [[...]] and tags #... via regex, builds a knowledge graph
through the injected IGraphBuilder port, and publishes lifecycle events
through the injected IEventBus port. Depends ONLY on contracts.* (+ stdlib);
it never imports adapters/infrastructure directly.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional

from contracts import IService, IFileSystem, IEventBus, IGraphBuilder


def _norm(p: str) -> str:
    """Normalize path separators to '/' for OS-independent graph ids/edges."""
    return p.replace("\\", "/")


class VaultStreamCrawler(IService):
    def __init__(
        self,
        fs: IFileSystem,
        bus: IEventBus,
        graph: IGraphBuilder,
        vault_path: str,
        tracker: Optional[Any] = None,
        index: Optional[Any] = None,
        semantic_index: Optional[Any] = None,
        embedding: Optional[Any] = None,
    ) -> None:
        self._fs = fs
        self._bus = bus
        self._graph = graph
        self._vault_path = vault_path
        # Stage 17: optional CrawlStateTracker (duck-typed; the arch gate
        # forbids sibling-service imports, so no type import here).
        # tracker=None => zero regression: full rescan exactly as in Stage 10.
        self._tracker = tracker
        # Stage 18: optional ContentIndex (same duck-typed DI convention).
        # index=None => zero regression: no full-text indexing at all.
        self._index = index
        # Stage 29: optional SemanticIndex + IEmbedding (duck-typed pair).
        # BOTH must be wired for semantic indexing; either None => no-op.
        self._semantic_index = semantic_index
        self._embedding = embedding
        self._stats: Dict[str, int] = {}

    # ----- IService -----
    def name(self) -> str:
        return "vault_stream_crawler"

    def initialize(self, context: Any | None = None) -> None:
        return None

    def execute(self, context_data: dict) -> str | List[str]:
        stats = asyncio.run(self.crawl())
        return json.dumps(stats)

    # ----- crawl (async) -----
    async def crawl(self) -> Dict[str, Any]:
        if self._tracker is not None:
            return await self._crawl_incremental()
        return await self._crawl_full()

    async def _crawl_full(self) -> Dict[str, Any]:
        """Stage-10 behavior: clear + full rescan (tracker=None path)."""
        await self._bus.publish("crawl.started", {"vault": self._vault_path})
        self._graph.clear()
        files: List[str] = []
        await self._walk(self._vault_path, files)
        self._scan_files(files)
        g = self._graph.get_graph()
        stats = {
            "files_scanned": len(files),
            "nodes": len(g["nodes"]),
            "edges": len(g["edges"]),
        }
        self._stats = stats
        await self._bus.publish(
            "crawl.finished", {"files": len(files), "nodes": len(g["nodes"])}
        )
        return stats

    async def _crawl_incremental(self) -> Dict[str, Any]:
        """Stage 17: differential crawl driven by the CrawlStateTracker.

        Never calls graph.clear(). Deleted files -> remove_node; changed
        files -> remove_node (drop stale edges) + rescan; unchanged files
        are not touched at all.
        """
        await self._bus.publish("crawl.started", {"vault": self._vault_path})
        changed, deleted = self._tracker.get_changed_files(self._vault_path)
        if not changed and not deleted and self._tracker.load_state():
            g = self._graph.get_graph()
            stats = {
                "status": "up_to_date",
                "files_scanned": 0,
                "nodes": len(g["nodes"]),
                "edges": len(g["edges"]),
            }
            self._stats = stats
            await self._bus.publish(
                "crawl.finished", {"files": 0, "nodes": len(g["nodes"])}
            )
            return stats
        # Drop nodes of deleted files (differential — no clear()).
        self._tracker.apply_to_graph(self._graph, deleted)
        # Stage 18: purge deleted files from the full-text index too.
        if self._index is not None:
            for fpath in deleted:
                self._index.remove_file(_norm(fpath))
        # Stage 29: purge deleted files from the semantic index too.
        if self._semantic_index is not None:
            for fpath in deleted:
                self._semantic_index.remove(_norm(fpath))
        # Changed files: drop their stale node+edges before rescanning,
        # otherwise re-adding would duplicate outgoing edges (edge storage
        # is a list). COLLISION caught in smoke: remove_node also drops
        # INCOMING edges from unchanged neighbors, which nobody rescans —
        # so preserve and re-add them (unless the source is itself changed:
        # its own rescan recreates them).
        changed_ids = {_norm(f) for f in changed}
        edges_before = self._graph.get_graph()["edges"]
        for nid in changed_ids:
            incoming = [
                e for e in edges_before
                if e["to"] == nid and e["from"] not in changed_ids
            ]
            self._graph.remove_node(nid)
            # Stage 18: drop stale terms before reindexing (index_file has
            # replace semantics anyway — this keeps the intent explicit even
            # if a changed file becomes unreadable and is skipped by the scan).
            if self._index is not None:
                self._index.remove_file(nid)
            for e in incoming:
                self._graph.add_edge(e["from"], e["to"], e["relation"])
        self._scan_files(changed)
        # Persist fresh mtimes of ALL current files (not just changed).
        self._tracker.save_state(self._tracker.scan_mtimes(self._vault_path))
        g = self._graph.get_graph()
        stats = {
            "files_scanned": len(changed),
            "nodes": len(g["nodes"]),
            "edges": len(g["edges"]),
        }
        self._stats = stats
        await self._bus.publish(
            "crawl.finished", {"files": len(changed), "nodes": len(g["nodes"])}
        )
        return stats

    def _scan_files(self, files: List[str]) -> None:
        """Parse each .md file: node + tag meta + [[wiki-link]] edges."""
        for fpath in files:
            fpath = _norm(fpath)
            try:
                text = self._fs.read_content(fpath)
            except Exception:
                continue
            tags = re.findall(r"#(\w+)", text)
            links = re.findall(r"\[\[(.*?)\]\]", text)
            self._graph.add_node(fpath, label=fpath, meta={"tags": tags})
            # Stage 18: full-text index (replace semantics — safe for both
            # full re-crawl and incremental changed-file rescan). index=None
            # => zero regression: nothing is indexed.
            if self._index is not None:
                self._index.index_file(fpath, text)
            # Stage 29: semantic embedding (replace semantics via dict add).
            if self._semantic_index is not None and self._embedding is not None:
                self._semantic_index.add(fpath, self._embedding.embed(text))
            for link in links:
                target = _norm(link.strip())
                if target:
                    self._graph.add_edge(fpath, target, "links_to")

    async def _walk(self, path: str, acc: List[str]) -> None:
        """Recursively collect .md files.

        IFileSystem.list_dir returns entries RELATIVE TO THE STORE BASE
        (the real LocalFileSystemAdapter yields e.g. "A.md" at top level and
        "sub\\B.md" for nested files). Therefore each entry is already a
        relative path: .md entries are files; everything else is a directory
        we recurse into directly. No string reconstruction needed.
        """
        try:
            entries = self._fs.list_dir(path)
        except Exception:
            return
        for e in entries:
            e = _norm(e)
            if e.endswith(".md"):
                acc.append(e)
            else:
                await self._walk(e, acc)

    def get_stats(self) -> dict:
        return dict(self._stats)

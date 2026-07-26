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
import re
from typing import Any, Dict, List, Optional

from contracts import IService, IFileSystem, IEventBus, IGraphBuilder


class VaultStreamCrawler(IService):
    def __init__(
        self,
        fs: IFileSystem,
        bus: IEventBus,
        graph: IGraphBuilder,
        vault_path: str,
    ) -> None:
        self._fs = fs
        self._bus = bus
        self._graph = graph
        self._vault_path = vault_path
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
    async def crawl(self) -> Dict[str, int]:
        await self._bus.publish("crawl.started", {"vault": self._vault_path})
        self._graph.clear()
        files: List[str] = []
        await self._walk(self._vault_path, files)
        for fpath in files:
            try:
                text = self._fs.read_content(fpath)
            except Exception:
                continue
            tags = re.findall(r"#(\w+)", text)
            links = re.findall(r"\[\[(.*?)\]\]", text)
            self._graph.add_node(fpath, label=fpath, meta={"tags": tags})
            for link in links:
                target = link.strip()
                if target:
                    self._graph.add_edge(fpath, target, "links_to")
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
            if e.endswith(".md"):
                acc.append(e)
            else:
                await self._walk(e, acc)

    def get_stats(self) -> dict:
        return dict(self._stats)

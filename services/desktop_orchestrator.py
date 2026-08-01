"""DesktopOrchestrator — high-level search-to-action workflows (Stage 32)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from contracts import IDesktop, IFileSystem


class DesktopOrchestrator:
    """Bridge between GraphQueryEngine (search) and DesktopService (action)."""

    def __init__(
        self,
        engine: GraphQueryEngine,
        desktop: DesktopService,
        fs: IFileSystem,
        vault_path: str,
    ) -> None:
        self._engine = engine
        self._desktop = desktop
        self._fs = fs
        self._vault_path = vault_path

    def open_note(self, query: str, top_k: int = 1) -> Dict[str, Any]:
        """Hybrid-search *query*, open the top result in the OS default app."""
        if not query or not query.strip():
            return {"error": "empty query"}
        results = self._engine.hybrid_search(query.strip(), top_k=top_k)
        if not results:
            return {"error": "no results", "query": query}
        nid = results[0][0]  # top-1 node id (relative path, e.g. "note.md")
        # Resolve to absolute path via IFileSystem
        full_path = os.path.join(self._vault_path, nid)
        if not self._fs.exists(full_path):
            # Fallback: nid may already be absolute or fs uses base-relative logic
            full_path = nid
        self._desktop.launch(full_path)
        return {"ok": True, "opened": nid, "path": full_path, "score": results[0][1]}

    def list_notes(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Hybrid-search and return ranked candidates (without opening)."""
        if not query or not query.strip():
            return []
        results = self._engine.hybrid_search(query.strip(), top_k=top_k)
        return [
            {"id": nid, "score": round(score, 4)} for nid, score in results
        ]

    def show_note(self, query: str, top_k: int = 1) -> Dict[str, Any]:
        """Hybrid-search *query*, read the top result content (no external app)."""
        if not query or not query.strip():
            return {"error": "empty query"}
        results = self._engine.hybrid_search(query.strip(), top_k=top_k)
        if not results:
            return {"error": "no results", "query": query}
        nid = results[0][0]  # top-1 node id (relative path, e.g. "note.md")
        full_path = os.path.join(self._vault_path, nid)
        if not self._fs.exists(full_path):
            full_path = nid
        try:
            content = self._fs.read_content(full_path)
        except Exception as exc:  # noqa: BLE001 -- surface read failures cleanly
            return {"error": f"cannot read {full_path}: {exc}", "id": nid}
        return {"ok": True, "id": nid, "path": full_path,
                "score": round(results[0][1], 4), "content": content}

"""CrawlStateTracker — incremental crawl state (Stage 17).

Tracks per-file mtimes between crawls so the crawler can rescan ONLY
changed/new files and differentially drop deleted ones — closing the
Stage-10 honest limitation "no incremental crawl — always full rescan".

State file: JSON {filepath: mtime} at `state_path` (default
".crawl_state.json", i.e. the vault root — the injected IFileSystem is
rooted there). File paths are vault-root-relative with '/' separators,
matching the crawler's node-id scheme exactly.

Architecture contract: depends ONLY on contracts.IFileSystem +
contracts.IGraphBuilder + stdlib (json, os). Never imports adapters,
kernel, cli, infrastructure or sibling services (enforced by
tests/test_architecture.py).

Honest limitations (Stage 17):
  * mtime-based, not content-hash: a rollback restoring an old mtime is missed
  * no rename detection: rename = delete + add (two events)
  * state file lives in the vault root, visible next to notes
  * no concurrent-crawl protection (state file race)
  * symlinked .md files may not reflect target changes in mtime
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from contracts import IFileSystem, IGraphBuilder


def _norm(p: str) -> str:
    """Normalize separators to '/' — same scheme as VaultStreamCrawler ids."""
    return p.replace("\\", "/")


class CrawlStateTracker:
    """Detects changed/new/deleted .md files between crawls via mtimes."""

    def __init__(self, fs: IFileSystem, state_path: str = ".crawl_state.json") -> None:
        self._fs = fs
        self._state_path = state_path

    # ----- state persistence -----
    def load_state(self) -> Dict[str, float]:
        """Read {filepath: mtime} from the state file via the FS port.

        Missing file or corrupt JSON -> {} (never raises).
        """
        try:
            if not self._fs.exists(self._state_path):
                return {}
            raw = self._fs.read_content(self._state_path)
            data = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        out: Dict[str, float] = {}
        for k, v in data.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue  # skip corrupt entries, keep the rest
        return out

    def save_state(self, current_mtimes: Dict[str, float]) -> None:
        """Serialize {filepath: mtime} to JSON via the FS port."""
        self._fs.write_content(
            self._state_path, json.dumps(current_mtimes, ensure_ascii=False)
        )

    # ----- diff detection -----
    def get_changed_files(self, vault_path: str) -> Tuple[List[str], List[str]]:
        """Return (changed_or_new, deleted) lists of vault-relative .md paths.

        changed_or_new: on disk but absent from state, or mtime differs.
        deleted:        in state but no longer on disk.
        """
        previous = self.load_state()
        current = self.scan_mtimes(vault_path)
        changed_or_new = [
            f for f, m in current.items()
            if f not in previous or previous[f] != m
        ]
        deleted = [f for f in previous if f not in current]
        return changed_or_new, deleted

    def scan_mtimes(self, vault_path: str) -> Dict[str, float]:
        """Walk the vault via the FS port; return {relpath: mtime} for .md files.

        list_dir returns entries RELATIVE TO THE FS BASE (vault root); .md
        entries are files, anything else is treated as a directory to recurse
        into (a non-dir non-.md entry makes list_dir raise -> silently skipped,
        same convention as VaultStreamCrawler._walk). mtime is read with
        os.path.getmtime on the absolute path (IFileSystem has no stat port —
        documented fallback).
        """
        acc: Dict[str, float] = {}
        self._walk(vault_path, vault_path, acc)
        return acc

    def _walk(self, root: str, path: str, acc: Dict[str, float]) -> None:
        try:
            entries = self._fs.list_dir(path)
        except Exception:
            return
        for e in entries:
            e = _norm(e)
            if e.endswith(".md"):
                abs_path = os.path.join(root, e.replace("/", os.sep))
                try:
                    acc[e] = os.path.getmtime(abs_path)
                except OSError:
                    continue  # vanished between list and stat
            else:
                self._walk(root, e, acc)

    # ----- differential graph update -----
    def apply_to_graph(self, graph: IGraphBuilder, deleted: List[str]) -> None:
        """Drop nodes for deleted files. NEVER calls graph.clear()."""
        for node_id in deleted:
            graph.remove_node(node_id)

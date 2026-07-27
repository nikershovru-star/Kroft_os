"""CrawlStateTracker — incremental crawl state (Stage 17, hash-aware since Stage 24).

Tracks per-file mtimes AND sha256 content hashes between crawls so the
crawler can rescan ONLY files whose CONTENT actually changed — closing the
Stage-17 honest limitation "mtime-based, not content-hash": mtime-only bumps
(git checkout, touch, copy) no longer trigger a re-crawl, so Watch Mode
(Stage 27) stops firing blanks.

State file (v2, Stage 24): JSON {filepath: {"mtime": float, "hash": str|null}}
at `state_path` (default ".crawl_state.json", i.e. the vault root — the
injected IFileSystem is rooted there). Legacy v1 files ({filepath: mtime})
are migrated on load: hash=None -> per-file fallback to mtime comparison.
File paths are vault-root-relative with '/' separators, matching the
crawler's node-id scheme exactly.

Architecture contract: depends ONLY on contracts.IFileSystem +
contracts.IGraphBuilder + stdlib (hashlib, json, os). Never imports adapters,
kernel, cli, infrastructure or sibling services (enforced by
tests/test_architecture.py).

Honest limitations (Stage 24):
  * hashing reads the entire file content — O(bytes) per file per crawl
  * unreadable files (transient locks) are treated as UNCHANGED to avoid
    infinite re-crawl loops in watch mode
Honest limitations (Stage 17, still open):
  * no rename detection: rename = delete + add (two events)
  * state file lives in the vault root, visible next to notes
  * no concurrent-crawl protection (state file race)
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from contracts import IFileSystem, IGraphBuilder


def _norm(p: str) -> str:
    """Normalize separators to '/' — same scheme as VaultStreamCrawler ids."""
    return p.replace("\\", "/")


class CrawlStateTracker:
    """Detects changed/new/deleted .md files between crawls via content hash
    (sha256), falling back to mtimes for legacy v1 state entries."""

    def __init__(self, fs: IFileSystem, state_path: str = ".crawl_state.json") -> None:
        self._fs = fs
        self._state_path = state_path

    # ----- hashing (Stage 24) -----
    @staticmethod
    def _hash_content(text: str) -> str:
        """sha256 hex digest of the file text (utf-8)."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _read_and_hash(self, rel_path: str) -> Optional[str]:
        """Best-effort sha256 of file content via the FS port. None on ANY
        failure (transient lock, vanished file) — callers treat None as
        'unknown', never as 'changed', to avoid watch-mode re-crawl loops."""
        try:
            return self._hash_content(self._fs.read_content(rel_path))
        except Exception:
            return None

    # ----- state persistence -----
    def load_state(self) -> Dict[str, Dict[str, Any]]:
        """Read state from the state file via the FS port; migrate v1 on the fly.

        Returns {filepath: {"mtime": float, "hash": str|None}}.
        Legacy v1 entries ({filepath: mtime}) become {"mtime": m, "hash": None}.
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
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in data.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                # v1 entry: bare mtime — no hash available.
                out[str(k)] = {"mtime": float(v), "hash": None}
            elif isinstance(v, dict):
                try:
                    mtime = float(v.get("mtime", 0))
                except (TypeError, ValueError):
                    mtime = 0.0
                h = v.get("hash")
                out[str(k)] = {"mtime": mtime, "hash": h if isinstance(h, str) else None}
            else:
                continue  # skip corrupt entries, keep the rest
        return out

    def save_state(self, current_mtimes: Dict[str, float]) -> None:
        """Serialize v2 state to JSON via the FS port.

        Signature unchanged since Stage 17 ({filepath: mtime} in); the hash of
        each file's CURRENT content is computed here (None if unreadable).
        """
        state: Dict[str, Dict[str, Any]] = {
            f: {"mtime": m, "hash": self._read_and_hash(f)}
            for f, m in current_mtimes.items()
        }
        self._fs.write_content(
            self._state_path, json.dumps(state, ensure_ascii=False)
        )

    # ----- diff detection -----
    def get_changed_files(self, vault_path: str) -> Tuple[List[str], List[str]]:
        """Return (changed_or_new, deleted) lists of vault-relative .md paths.

        Stage 24 semantics:
          * new file (absent from state)            -> changed
          * stored hash present -> compare CONTENT hash; mtime is ignored.
            Unreadable now (hash None) -> treated as unchanged (defensive).
          * stored hash None (legacy v1 / unreadable at save time)
            -> fall back to Stage-17 mtime comparison.
        deleted: in state but no longer on disk.
        """
        previous = self.load_state()
        current = self.scan_mtimes(vault_path)
        changed_or_new: List[str] = []
        for f, m in current.items():
            entry = previous.get(f)
            if entry is None:
                changed_or_new.append(f)  # new file
                continue
            old_hash = entry.get("hash")
            if old_hash is not None:
                new_hash = self._read_and_hash(f)
                if new_hash is not None and new_hash != old_hash:
                    changed_or_new.append(f)
                # new_hash None (transient lock) -> unchanged: avoids
                # infinite re-crawl loops in watch mode.
                continue
            # Legacy v1 fallback: mtime-only comparison.
            if entry.get("mtime") != m:
                changed_or_new.append(f)
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

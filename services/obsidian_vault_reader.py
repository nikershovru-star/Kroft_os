"""Obsidian vault reader (ТЗ-DAILY-01) — stdlib-only Markdown ingestion source.

K1-compliant: stdlib only (pathlib, no 3rd-party). K5: this is a NEW, narrow seam — there is
NO existing vault reader to reuse, and it does NOT duplicate KnowledgeEngine (ТЗ-KNOWLEDGE-ENGINE-01,
ADR-091): KnowledgeEngine owns extraction->graph; this reader only READS raw .md files from a
filesystem path and yields (doc_id, text) pairs. The composition layer feeds those pairs into the
existing KnowledgeEngine.ingest(), so the knowledge graph (and thus the dashboard's memory_notes)
grows from REAL vault content, not demo-seed.

Graceful degradation (O1-style): a missing/empty vault path yields an empty note list and never
raises — the dashboard simply shows 0 notes. Vault paths may contain spaces; we use pathlib (no shell).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional


@dataclass(frozen=True)
class VaultNote:
    """A single read-only Markdown note from the vault (ТЗ-DAILY-01)."""

    doc_id: str
    text: str
    path: str


class ObsidianVaultReader:
    """Read *.md files from an Obsidian vault directory (stdlib, deterministic, graceful)."""

    def __init__(self, vault_path: Optional[str] = None) -> None:
        # vault_path may be None (graceful: empty vault) or a path with spaces (pathlib handles it).
        self._vault_path = Path(vault_path) if vault_path else None

    def exists(self) -> bool:
        return self._vault_path is not None and self._vault_path.is_dir()

    def read_notes(self) -> List[VaultNote]:
        """Read all *.md notes recursively. Returns [] when the vault is missing/empty (graceful)."""
        if not self.exists():
            return []
        notes: List[VaultNote] = []
        # rglob is deterministic per-filesystem order; pathlib avoids shell quoting issues with spaces.
        for md in sorted(self._vault_path.rglob("*.md")):  # type: Path
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue  # skip unreadable files; never crash the reader
            doc_id = str(md.relative_to(self._vault_path)) if self._vault_path else md.name
            notes.append(VaultNote(doc_id=doc_id, text=text, path=str(md)))
        return notes

    def iter_notes(self) -> Iterator[VaultNote]:
        """Lazy variant of read_notes() for large vaults."""
        if not self.exists():
            return
        for md in sorted(self._vault_path.rglob("*.md")):  # type: Path
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            doc_id = str(md.relative_to(self._vault_path)) if self._vault_path else md.name
            yield VaultNote(doc_id=doc_id, text=text, path=str(md))

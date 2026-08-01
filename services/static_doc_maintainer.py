"""(services) StaticDocMaintainer — IDocMaintainer (Wave 14, ADR-017 v0.1).

Read-only doc/code consistency check. v0.1 is STATIC: it does not parse Obsidian
markdown. Instead it validates a supplied `code_state` snapshot against the
filesystem (files referenced by the MOC must resolve; ADR-accepted claims must
match actual files). It only PROPOSES diffs — never writes (ADR-017 §2.3).

LAW 2: imports only contracts.* + stdlib. The maintainer never imports the
concrete platforms; `code_state` is the caller's responsibility.
"""
from __future__ import annotations

import os
from typing import Dict, List, Tuple

from contracts.i_autonomy import DocSyncResult, IDocMaintainer


class StaticDocMaintainer(IDocMaintainer):
    """Validate doc/code consistency from a code_state snapshot (v0.1)."""

    # paths allowed for a recommendation target (mirrors LlmOptimizer whitelist)
    ALLOWED_PREFIXES = ("policy:", "knowledge:")

    def sync(self, docs_root: str, code_state: Dict) -> DocSyncResult:
        mismatches: List[str] = []
        proposed: List[str] = []

        # 1. referenced files must resolve on disk
        expected = code_state.get("expected_files", []) or []
        for rel in expected:
            full = os.path.join(docs_root, rel) if docs_root else rel
            if not os.path.exists(full):
                mismatches.append(f"missing doc file: {rel}")
                proposed.append(f"create or relink: {rel}")

        # 2. ADR 'accepted' claims must match an actual file
        adr_claims = code_state.get("adr_accepted", {}) or {}
        for adr_id, claimed in adr_claims.items():
            if claimed and not self._adr_file_exists(docs_root, adr_id):
                mismatches.append(f"ADR-{adr_id} claimed accepted but file missing")
                proposed.append(f"downgrade ADR-{adr_id} status to 'proposed' or add file")

        # 3. MOC links must resolve
        moc_links = code_state.get("moc_links", []) or []
        for link in moc_links:
            if not self._link_resolves(docs_root, link):
                mismatches.append(f"MOC link unresolved: {link}")
                proposed.append(f"fix MOC link: {link}")

        return DocSyncResult(
            mismatches=tuple(mismatches),
            proposed_diffs=tuple(proposed),
        )

    # --- helpers ---------------------------------------------------------
    @staticmethod
    def _adr_file_exists(docs_root: str, adr_id: str) -> bool:
        if not docs_root:
            return False
        import glob
        pattern = os.path.join(docs_root, "architecture", f"ADR-{adr_id} *.md")
        return bool(glob.glob(pattern))

    @staticmethod
    def _link_resolves(docs_root: str, link: str) -> bool:
        if not docs_root:
            return True  # cannot verify without a root; assume ok
        # link is a relative path or [[wikilink]] target filename
        name = link.strip("[]").split("|")[0].strip()
        full = os.path.join(docs_root, name)
        return os.path.exists(full)

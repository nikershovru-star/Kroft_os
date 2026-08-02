"""File Sandbox — path-prefix guard (TZ-SEC-001 WP-06).

K1-compliant: contracts + stdlib only. Agents may only operate inside allowed
roots (Obsidian Vault / Workspace / Temp / Projects). Anything under Windows
system dirs requires explicit user confirmation (represented as a denied path
here; the approval flow is handled by ApprovalManager).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from contracts.security import Capability

# Roots allowed without confirmation (resolve to absolute at runtime).
_DEFAULT_ALLOWED = [
    "{vault}",
    "{workspace}",
    "{temp}",
    "{projects}",
]

# Forbidden prefixes (Windows system / user-private) — block unless approved.
_FORBIDDEN_PREFIXES = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
    r"C:\Users",
    r"AppData",
    r"registry",
]


class FileSandbox:
    def __init__(self, roots: List[str] | None = None,
                 allowed: List[str] | None = None) -> None:
        self._roots_placeholders = allowed or list(_DEFAULT_ALLOWED)
        self._resolved: List[str] = []
        for r in (roots or []):
            self._resolved.append(os.path.normcase(os.path.abspath(r)))

    def set_roots(self, **kwargs: str) -> None:
        """Resolve placeholders ({vault}, {workspace}, ...) to real paths."""
        self._resolved = []
        for ph in self._roots_placeholders:
            key = ph.strip("{}")
            if key in kwargs:
                self._resolved.append(os.path.normcase(os.path.abspath(kwargs[key])))

    def is_allowed(self, path: str) -> bool:
        norm = os.path.normcase(os.path.abspath(path))
        # forbidden prefixes always block
        for forbidden in _FORBIDDEN_PREFIXES:
            if norm.startswith(os.path.normcase(forbidden)):
                return False
        # must be inside at least one allowed root
        if not self._resolved:
            return False
        return any(norm.startswith(root) for root in self._resolved)

    def check(self, path: str, required: Capability) -> bool:
        """True if the path is allowed for the given Filesystem capability."""
        if required.category.value != "Filesystem":
            return True
        if required.operation in ("Delete",) and not self.is_allowed(path):
            return False
        return self.is_allowed(path)

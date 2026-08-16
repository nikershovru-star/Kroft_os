"""H2 apply/test runner — minimal file-backed implementation.

K1-compliant: stdlib + contracts only. No service/adapter imports.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import List, Optional

from contracts.patch_runner import ApplyResult, IApplyPatch, ITestRunner, Patch, TestResult


class FileApplyPatch(IApplyPatch):
    """Applies string-replacement patches with a simple backup."""

    def __init__(self, root: Optional[str] = None) -> None:
        self._root = Path(root) if root else Path.cwd()

    def apply(self, patch: Patch) -> ApplyResult:
        target = self._root / patch.target_path
        if not target.exists():
            return ApplyResult(ok=False, patch_id=patch.patch_id, message=f"missing {target}")
        backup = target.with_suffix(target.suffix + ".bak")
        try:
            shutil.copy2(target, backup)
            text = target.read_text(encoding="utf-8")
            if patch.old not in text:
                return ApplyResult(ok=False, patch_id=patch.patch_id, message="old string not found", backup_path=str(backup))
            target.write_text(text.replace(patch.old, patch.new, 1), encoding="utf-8")
            return ApplyResult(ok=True, patch_id=patch.patch_id, message="applied", backup_path=str(backup))
        except Exception as exc:
            return ApplyResult(ok=False, patch_id=patch.patch_id, message=str(exc), backup_path=str(backup) if backup.exists() else None)


class InMemoryTestRunner(ITestRunner):
    """Placeholder test runner for H2 flow."""

    def run_tests(self, patch_id: str) -> TestResult:
        return TestResult(patch_id=patch_id, passed=True, total=0, output="no-tests")

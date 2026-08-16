"""H2 Patch/TestRunner contracts — controlled external actions.

K1-compliant: contracts + stdlib only. No kernel/service imports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Patch:
    """Minimal patch carrier for H2 apply path."""

    patch_id: str
    target_path: str
    old: str
    new: str
    reason: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ApplyResult:
    ok: bool
    patch_id: str
    message: str = ""
    backup_path: Optional[str] = None


@dataclass(frozen=True)
class TestResult:
    patch_id: str
    passed: bool
    total: int = 0
    failures: List[str] = field(default_factory=list)
    output: str = ""


class IApplyPatch(ABC):
    """Apply a Patch through controlled composition root."""

    @abstractmethod
    def apply(self, patch: Patch) -> ApplyResult:
        raise NotImplementedError


class ITestRunner(ABC):
    """Run tests for a specific patch and return TestResult."""

    @abstractmethod
    def run_tests(self, patch_id: str) -> TestResult:
        raise NotImplementedError

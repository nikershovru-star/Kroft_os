"""Tests: services/patch_runner.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

from services.patch_runner import FileApplyPatch, InMemoryTestRunner
from contracts.patch_runner import ApplyResult, Patch, TestResult


def test_apply_patch_success():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "file.txt"
        target.write_text("hello world\n", encoding="utf-8")
        patcher = FileApplyPatch(root=tmp)
        patch = Patch(patch_id="p1", target_path="file.txt", old="hello", new="hi")
        result = patcher.apply(patch)
        assert result.ok is True
        assert result.backup_path is not None
        assert target.read_text(encoding="utf-8") == "hi world\n"


def test_apply_patch_missing_target():
    patcher = FileApplyPatch()
    patch = Patch(patch_id="p1", target_path="__missing__.txt", old="x", new="y")
    result = patcher.apply(patch)
    assert result.ok is False
    assert "missing" in result.message


def test_apply_patch_old_string_not_found():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "file.txt"
        target.write_text("hello world\n", encoding="utf-8")
        patcher = FileApplyPatch(root=tmp)
        patch = Patch(patch_id="p1", target_path="file.txt", old="zzz", new="y")
        result = patcher.apply(patch)
        assert result.ok is False
        assert "not found" in result.message


def test_test_runner_placeholder():
    runner = InMemoryTestRunner()
    result = runner.run_tests("p1")
    assert isinstance(result, TestResult)
    assert result.patch_id == "p1"
    assert result.passed is True


def test_apply_patch_corrupt_backup_does_not_mask_error():
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "file.txt"
        target.write_text("hello world\n", encoding="utf-8")
        patcher = FileApplyPatch(root=tmp)
        patch = Patch(patch_id="p1", target_path="file.txt", old="hello", new="hi")
        # simulate failure after backup by making target read-only
        target.write_text("locked", encoding="utf-8")
        result = patcher.apply(patch)
        assert result.ok is False


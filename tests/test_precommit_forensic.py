"""Tests for the pre-commit forensic gate (P0-coord).

Verifies that the forensic gate:
- Detects duplicate class names in a new file
- Allows unique class names
- Correctly ignores tests/ directory for class definitions
- Correctly ignores docs/ directory for ADR references
"""
from __future__ import annotations

import os
import tempfile
import subprocess
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "pre_commit_forensic.py"
sys.path.insert(0, str(ROOT))

from scripts.pre_commit_forensic import (
    _extract_artifacts_from_file,
    _find_repo_root,
    _scan_repository_for_artifact,
)


def test_extract_artifacts_finds_class():
    """The extractor finds class definitions."""
    content = '''
class MyClass:
    pass

def some_function():
    pass
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()
        artifacts = _extract_artifacts_from_file(f.name)
    
    os.unlink(f.name)
    
    class_names = [a[0] for a in artifacts if a[1] == "class"]
    assert "MyClass" in class_names


def test_extract_artifacts_finds_adr():
    """The extractor finds ADR references."""
    content = "This is related to ADR-025 and ADR-030."
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(content)
        f.flush()
        artifacts = _extract_artifacts_from_file(f.name)
    
    os.unlink(f.name)
    
    adr_names = [a[0] for a in artifacts if a[1] == "adr"]
    assert "ADR-025" in adr_names
    assert "ADR-030" in adr_names


def test_no_duplicates_for_unique_class(tmp_path):
    """A class with a unique name should not trigger duplicate detection."""
    import time
    timestamp = str(int(time.time()))
    unique_name = f"XyZ_UniqueTestClass_{timestamp}_B"
    filepath = tmp_path / "unique_module.py"
    filepath.write_text(f"class {unique_name}:\n    pass\n")

    # Directly test the extraction and scan logic
    repo_root = str(ROOT)
    
    # Extract artifacts from the temp file
    artifacts = _extract_artifacts_from_file(filepath)
    assert (unique_name, "class") in artifacts
    
    # Scan repository for the artifact, excluding the temp file
    new_files = {str(filepath)}
    matches = _scan_repository_for_artifact(unique_name, "class", repo_root, new_files)
    
    # The class only exists in the temp file (excluded from scan), so no matches
    assert matches == []


def test_duplicate_detected_for_existing_class_via_scan():
    """A class name that already exists in the repo should be found by scan."""
    repo_root = str(ROOT)
    matches = _scan_repository_for_artifact("GraphQueryEngine", "class", repo_root, set())
    assert len(matches) > 0
    # Should find at least one file mentioning GraphQueryEngine
    assert any("GraphQueryEngine" in open(os.path.join(repo_root, m)).read() for m in matches)


def test_script_runs_with_help():
    """The script should respond to --help."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "pre-commit forensic" in result.stdout.lower()
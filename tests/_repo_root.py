"""Repo-root discovery for tests (ТЗ-RESTRUCTURE). Walk up from __file__ until the
AKB dir exists, so path math is correct regardless of test subfolder depth."""
from pathlib import Path

def repo_root() -> Path:
    d = Path(__file__).resolve().parent
    while not (d / "docs" / "architecture" / "AKB").exists():
        if d.parent == d:
            break
        d = d.parent
    return d

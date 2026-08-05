"""services/test_static_doc_maintainer.py — read-only doc/code check (Wave 14).

Verifies the maintainer proposes diffs but NEVER writes (ADR-017 §2.3), and
resolves mismatches from a code_state snapshot.
"""
from __future__ import annotations

import os
import tempfile

from services.static_doc_maintainer import StaticDocMaintainer


def test_missing_file_reported() -> None:
    with tempfile.TemporaryDirectory() as d:
        res = StaticDocMaintainer().sync(d, {"expected_files": ["nonexistent.md"]})
        assert any("missing doc file" in m for m in res.mismatches)
        assert len(res.proposed_diffs) == len(res.mismatches)


def test_existing_file_ok() -> None:
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "present.md")
        open(f, "w").write("x")
        res = StaticDocMaintainer().sync(d, {"expected_files": ["present.md"]})
        assert res.mismatches == ()


def test_adr_accepted_but_missing_detected() -> None:
    with tempfile.TemporaryDirectory() as d:
        # ADR-016 accepted, but no ADR-016 file present
        res = StaticDocMaintainer().sync(d, {"adr_accepted": {"016": True}})
        assert any("ADR-016" in m for m in res.mismatches)


def test_moc_link_unresolved() -> None:
    with tempfile.TemporaryDirectory() as d:
        res = StaticDocMaintainer().sync(d, {"moc_links": ["Architecture MOC.md"]})
        assert any("MOC link unresolved" in m for m in res.mismatches)


def test_maintainer_does_not_write() -> None:
    with tempfile.TemporaryDirectory() as d:
        maintainer = StaticDocMaintainer()
        res = maintainer.sync(d, {"expected_files": ["ghost.md"]})
        # no file created by the maintainer
        assert not os.path.exists(os.path.join(d, "ghost.md"))
        assert res.proposed_diffs  # but it proposed a fix

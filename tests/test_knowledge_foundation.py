"""Offline contract test for the Knowledge Foundation catalog (ADR-091).

Verifies the data file (docs/architecture/AKB/knowledge_foundation_v1.yaml)
and the on-disk PDF corpus agree, and that every downloadable entry is a
real PDF. No network, no env gating — always runs fast.

This is the relevant verification for edits to the catalog YAML and
scripts/fetch_foundation.py, which the engine/retrieval suite does not touch.
"""

import glob
import os

import pytest
import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join(
    REPO_ROOT, "docs", "architecture", "AKB", "knowledge_foundation_v1.yaml"
)
CORPUS_DIR = os.path.join(REPO_ROOT, "KROFT_KNOWLEDGE_FOUNDATION")

# legal statuses that are NOT directly downloadable as PDFs by the fetch script
NON_DOWNLOADABLE = ("copyrighted", "search_only", "author_page", "web_only", "no_link")


def _load_catalog():
    with open(YAML_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _all_entries():
    cat = _load_catalog()
    return cat.get("core_v1", []) + cat.get("extended", []) + cat.get("remaining", [])


def _downloadable():
    return [
        e
        for e in _all_entries()
        if e.get("legal") not in NON_DOWNLOADABLE and e.get("url")
    ]


def _filenames_of(e):
    """Return the catalog entry's filename list (1..N physical PDF reps)."""
    fn = e.get("filename")
    if fn is None:
        return []
    return fn if isinstance(fn, list) else [fn]


def _entry_matches(base, e):
    """Deterministic PDF<->catalog match.

    SSOT is the explicit ``filename`` field (a scalar or list). A PDF maps to
    an entry iff its basename (without .pdf) is contained in the entry's
    filename list. No tokenization, no fuzzy/substring author/title heuristics.
    """
    return base in _filenames_of(e)

def _on_disk_pdfs():
    if not os.path.isdir(CORPUS_DIR):
        return []
    return glob.glob(os.path.join(CORPUS_DIR, "**", "*.pdf"), recursive=True)


def test_catalog_loads():
    cat = _load_catalog()
    assert isinstance(cat, dict)
    # every block present and non-empty
    for key in ("core_v1", "extended", "remaining"):
        assert key in cat, f"missing catalog block: {key}"
        assert isinstance(cat[key], list) and cat[key], f"empty catalog block: {key}"


def test_each_entry_has_required_fields():
    for e in _all_entries():
        assert e.get("author"), f"missing author: {e}"
        assert e.get("title"), f"missing title: {e}"
        assert e.get("section"), f"missing section: {e}"
        assert e.get("legal"), f"missing legal: {e}"
        # public_domain entries must carry a direct PDF url (archive.org etc.)
        # author_draft / open_access / web_only may be local copies or pages (no url).
        if e.get("legal") == "public_domain":
            assert e.get("url"), f"public_domain entry without url: {e}"


def test_disk_pdfs_covered_by_catalog():
    """Invariant A: every on-disk PDF maps to EXACTLY ONE catalog entry
    (via deterministic filename match). No PDF may be orphaned; none may map
    to more than one entry.
    """
    entries = _all_entries()
    for f in _on_disk_pdfs():
        base = os.path.basename(f).lower().replace(".pdf", "")
        matched = [e for e in entries if _entry_matches(base, e)]
        assert len(matched) == 1, (
            f"PDF {base} matched {len(matched)} catalog entries "
            f"(expected exactly 1)"
        )
        assert matched[0]["legal"] != "copyrighted", (
            f"copyrighted PDF present on disk: {base}"
        )


def test_catalog_filename_integrity():
    """Invariant B + global uniqueness:
    - every catalog entry's filename points to a real on-disk PDF;
    - every filename value is unique across the WHOLE catalog (no two entries
      may claim the same physical file).
    """
    entries = _all_entries()
    disk = {os.path.basename(f).lower().replace(".pdf", "") for f in _on_disk_pdfs()}
    seen = {}
    for e in entries:
        for fn in _filenames_of(e):
            assert fn in disk, (
                f"catalog filename '{fn}' has no matching PDF on disk "
                f"({e['author']} | {e['title']})"
            )
            assert fn not in seen, (
                f"filename '{fn}' claimed by two entries: "
                f"{seen[fn]} AND ({e['author']} | {e['title']})"
            )
            seen[fn] = (e["author"], e["title"])


def test_every_disk_pdf_is_real():
    bad = []
    for f in _on_disk_pdfs():
        with open(f, "rb") as fh:
            head = fh.read(5)
        if head != b"%PDF-":
            bad.append((os.path.relpath(f, REPO_ROOT), head))
    assert not bad, f"non-PDF files on disk: {bad}"


def test_no_copyrighted_pdf_on_disk():
    """Guard: every on-disk PDF must map to EXACTLY ONE catalog entry, and that
    exact entry must not be copyrighted (we never hold pirated copies).
    """
    entries = _all_entries()
    for f in _on_disk_pdfs():
        base = os.path.basename(f).lower().replace(".pdf", "")
        matched = [e for e in entries if _entry_matches(base, e)]
        assert len(matched) == 1, f"on-disk PDF not in catalog: {base}"
        assert matched[0]["legal"] != "copyrighted", (
            f"copyrighted PDF present on disk: {base}"
        )

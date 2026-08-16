"""STAGE 4.8 — foundation_extract.py hardening regression tests.

Verifies the page-safe extractor (no global 45s document timeout) against
synthetic PDFs generated in TEMP. No production snapshot / _extracted touched.

Covers ТЗ STEP 6: A(small OK) B(multi-page no false timeout) C(page failure)
D(empty) E(checksum) F(schema) G(existing sidecar readable) H(no TIMEOUT status).
"""
from __future__ import annotations

import os
import sys
import json
import tempfile
import hashlib
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fitz  # PyMuPDF, available (STEP 3)
import scripts.foundation_extract as fx


def _make_pdf(path: Path, n_pages: int, text_per_page: str = "Hello world page."):
    doc = fitz.open()
    for i in range(n_pages):
        pg = doc.new_page()
        pg.insert_text((72, 72), f"{text_per_page} page {i+1}")
    doc.save(str(path))
    doc.close()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    # redirect extractor outputs into the temp sandbox
    monkeypatch.setattr(fx, "FOUNDATION", tmp_path)
    monkeypatch.setattr(fx, "OUT_DIR", tmp_path)
    return tmp_path


def test_A_small_pdf_ok(sandbox):
    pdf = sandbox / "small.pdf"
    long_text = ("Foundation knowledge snippet. " * 20)  # >80 chars -> chunkable
    _make_pdf(pdf, 3, long_text)
    meta = fx.process_file(pdf)
    assert meta["status"] == "OK", meta
    assert meta["chunk_count"] > 0, meta
    # checksum preserved
    assert meta["checksum"] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    # sidecar written + schema
    sc = json.loads((sandbox / "small.json").read_text(encoding="utf-8"))
    assert "meta" in sc and "chunks" in sc
    assert sc["chunks"][0]["text"] and "page_start" in sc["chunks"][0]


def test_B_multipage_no_false_timeout(sandbox):
    # 300 pages would have hit the OLD 45s global timeout; new page-safe
    # extractor must complete with status=OK.
    pdf = sandbox / "big.pdf"
    _make_pdf(pdf, 300, "Multi-page foundation text content here.")
    meta = fx.process_file(pdf)
    assert meta["status"] == "OK", meta
    assert meta["pages"] == 300
    assert meta["failed_pages"] == [], meta


def test_C_page_level_failure_diagnostic(sandbox, monkeypatch):
    # A CRASHING page must be reported as a DIAGNOSTIC failure (via
    # _extract_all_pages returning it in the failed list), not kill the whole
    # document. _extract_all_pages opens the PDF once and extracts per page
    # with try/except, so we monkey-patch pypdf.PdfReader (same process).
    pdf = sandbox / "partial.pdf"
    _make_pdf(pdf, 4, "Page text.")
    real_reader = fx.pypdf.PdfReader

    class _Boom:
        def __init__(self, *a, **k):
            pass
        @property
        def pages(self):
            class _Pg:
                def __init__(self, i):
                    self._i = i
                def extract_text(self):
                    if self._i == 1:
                        raise RuntimeError("boom on page 1")
                    return f"ok {self._i}"
            return [_Pg(i) for i in range(4)]

    monkeypatch.setattr(fx.pypdf, "PdfReader", _Boom)
    texts, failed, err = fx._extract_all_pages(str(pdf))
    monkeypatch.setattr(fx.pypdf, "PdfReader", real_reader)
    assert err is None, "document should still open"
    assert failed == [1], failed
    assert texts[0] != "" and texts[2] != "" and texts[3] != "" and texts[1] == ""


def test_D_empty_extraction_failed(sandbox):
    pdf = sandbox / "empty.pdf"
    _make_pdf(pdf, 2, "   ")  # whitespace only -> no real text
    meta = fx.process_file(pdf)
    assert meta["status"] == "EXTRACTION_FAILED", meta
    assert meta["chunk_count"] == 0


def test_E_checksum_preserved(sandbox):
    pdf = sandbox / "chk.pdf"
    _make_pdf(pdf, 5, "Checksum verification content.")
    meta = fx.process_file(pdf)
    assert meta["checksum"] == hashlib.sha256(pdf.read_bytes()).hexdigest()


def test_F_schema_compatible_with_ingest(sandbox):
    pdf = sandbox / "schema.pdf"
    _make_pdf(pdf, 4, "Schema compatible chunk.")
    meta = fx.process_file(pdf)
    sc = json.loads((sandbox / "schema.json").read_text(encoding="utf-8"))
    # old pipeline contract: meta.status + chunks[{text,page_start,page_end}]
    assert sc["meta"]["status"] in ("OK", "PARTIAL", "EXTRACTION_FAILED")
    for c in sc["chunks"]:
        assert {"text", "page_start", "page_end"} <= set(c.keys())


def test_G_existing_kant_russell_sidecars_readable():
    # production sidecars already recovered in 4.7 must remain valid for ingest
    ext = Path(ROOT) / "KROFT_KNOWLEDGE_FOUNDATION" / "_extracted"
    for stem in ["immanuel_kant_critique_of_pure_reason",
                 "bertrand_russell_the_problems_of_philosophy"]:
        sc = ext / f"{stem}.json"
        if not sc.is_file():
            pytest.skip(f"{stem} sidecar absent")
        d = json.loads(sc.read_text(encoding="utf-8"))
        assert d["meta"]["status"] == "OK", d["meta"]
        assert d["meta"]["chunk_count"] > 0
        assert len(d["chunks"]) > 0


def test_H_no_extraction_timeout_status():
    # After 4.8 the extractor must NEVER emit EXTRACTION_TIMEOUT.
    assert "EXTRACTION_TIMEOUT" not in [
        fx.process_file.__name__,  # placeholder; real check below
    ]
    # inspect source: status literal must not appear as an assignment target
    src = Path(fx.__file__).read_text(encoding="utf-8")
    assert '"EXTRACTION_TIMEOUT"' not in src, "extractor still emits EXTRACTION_TIMEOUT"

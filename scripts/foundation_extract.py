"""KROFT Knowledge Foundation — PDF -> text/chunks extractor (INGESTION v1.0, Этап A/B/C).

Reuses only stdlib + pypdf + fitz (already present). NO new engine/service.
Scanned PDFs (no text layer) are marked EXTRACTION_FAILED (tesseract/OCR
unavailable in this environment) and skipped, not fatal (ТЗ §5/§20).

Outputs a JSON sidecar per PDF: {meta, chunks:[{page_start,page_end,text}]}
so the node generator (Этап D) can build KROFT-FND-*.md with provenance pages.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

FOUNDATION = (Path(__file__).resolve().parent.parent / "KROFT_KNOWLEDGE_FOUNDATION").resolve()
OUT_DIR = FOUNDATION / "_extracted"
OUT_DIR.mkdir(exist_ok=True)

try:
    import pypdf
except ImportError:
    pypdf = None


def _checksum(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _pdf_pages(path: Path) -> int:
    try:
        return len(pypdf.PdfReader(str(path)).pages)
    except Exception:
        return -1


# --- Stage 4.8 extraction hardening (ТЗ-KNOWLEDGE-EXTRACT-HARDEN-01) ---
# OLD behaviour: a single 45s GLOBAL timeout on the whole document killed
# extraction for any large-but-valid text PDF (e.g. 710-page Kant took 136s
# and was marked EXTRACTION_TIMEOUT). NEW behaviour: each PDF is extracted by
# ONE pooled worker that opens the PDF once and extracts all pages (fast, like
# the pre-4.8 bulk path) — but with (a) per-page try/except so a CRASHING page
# is reported as a diagnostic failure (failed_pages) instead of killing the doc,
# and (b) a DOCUMENT_TIMEOUT watchdog (1800s, not 45s) so a genuinely hung doc
# is aborted without falsely failing valid large books. No 45s global timeout.
import multiprocessing as _mp

PAGE_TIMEOUT = 20          # seconds; a single page slower than this is pathological
DOCUMENT_TIMEOUT = 1800    # seconds; whole-document watchdog (30 min), replaces old 45s
_NWORKERS = max(1, min(4, (_mp.cpu_count() or 1)))


def _extract_all_pages(path: str) -> tuple[list[str], list[int], "object"]:
    """Pool worker: open PDF ONCE, extract every page, return (texts, failed, err).

    Per-page try/except makes a CRASHING page a diagnostic failure (appended to
    ``failed``) while the rest of the document still extracts. A hanging page is
    caught by the caller's DOCUMENT_TIMEOUT watchdog.
    """
    try:
        reader = pypdf.PdfReader(path)
        texts: list[str] = []
        failed: list[int] = []
        for i, pg in enumerate(reader.pages):
            try:
                texts.append(pg.extract_text() or "")
            except Exception:
                texts.append("")
                failed.append(i)
        return (texts, failed, None)
    except Exception as e:  # noqa: BLE001 - document-level failure is diagnostic
        return ([], [], str(e)[:200])


def extract_text(path: Path) -> tuple[str, int, list[str], list[int]]:
    """Return (joined_text, page_count, per_page_text, failed_pages).

    Page-safe: opened once, extracted per page with crash isolation. A crashing
    page is reported in ``failed_pages`` (diagnostic). The 45s global document
    timeout is GONE — replaced by DOCUMENT_TIMEOUT (1800s) so valid large PDFs
    complete. Empty text => scanned (handled by caller).
    """
    if pypdf is None:
        return "", _pdf_pages(path), [], []
    try:
        n = len(pypdf.PdfReader(str(path)).pages)
    except Exception:
        return "", 0, [], []
    ctx = _mp.get_context("spawn")
    try:
        with ctx.Pool(processes=_NWORKERS) as pool:
            res = pool.apply_async(_extract_all_pages, (str(path),))
            try:
                per_page, failed, err = res.get(timeout=DOCUMENT_TIMEOUT)
            except Exception:  # watchdog: doc hung past DOCUMENT_TIMEOUT
                return "", n, ["" ] * n, list(range(n))
    except Exception:
        return "", n, ["" ] * n, list(range(n))
    if err:
        return "", n, ["" ] * n, list(range(n))
    return "\n".join(per_page), n, per_page, failed


def chunk_text(text: str, pages_text: list[str], max_chars: int = 2600) -> list[dict]:
    """Logical chunking: split by paragraphs; cap size; track page bounds (ТЗ §6)."""
    chunks = []
    buf = ""
    buf_start = 1
    for i, pt in enumerate(pages_text, start=1):
        blocks = re.split(r"\n\s*\n", pt)
        for b in blocks:
            b = b.strip()
            if not b:
                continue
            if len(buf) + len(b) > max_chars and buf:
                chunks.append({"page_start": buf_start, "page_end": max(1, i - 1), "text": buf.strip()})
                buf = b
                buf_start = i
            else:
                buf = (buf + "\n" + b).strip()
    if buf:
        chunks.append({"page_start": buf_start, "page_end": len(pages_text) or buf_start, "text": buf.strip()})
    return [c for c in chunks if len(c["text"]) > 80]


def process_file(path: Path) -> dict:
    meta = {
        "path": str(path.relative_to(FOUNDATION)),
        "filename": path.name,
        "size": path.stat().st_size,
        "checksum": _checksum(path),
    }
    pages = _pdf_pages(path)
    meta["pages"] = pages
    # Stage 4.8: extract_text now returns failed_pages (page-level diagnostics)
    text, page_count, pages_text, failed_pages = extract_text(path)
    meta["text_length"] = len(text)
    meta["failed_pages"] = failed_pages
    if len(text.strip()) < 200:
        meta["status"] = "EXTRACTION_FAILED"   # scanned / no OCR layer
        meta["ocr_required"] = True
        meta["full_text"] = False
        chunks = []
    elif failed_pages:
        # valid text recovered for most pages, but some pages failed ->
        # explicit PARTIAL status (never OK with missing pages; ТЗ STEP3 contract)
        meta["status"] = "PARTIAL"
        meta["ocr_required"] = False
        meta["full_text"] = False
        chunks = chunk_text(text, pages_text)
    else:
        meta["status"] = "OK"
        meta["ocr_required"] = False
        meta["full_text"] = True
        chunks = chunk_text(text, pages_text)
    meta["chunk_count"] = len(chunks)
    sidecar = {"meta": meta, "chunks": chunks}
    out = OUT_DIR / (path.stem + ".json")
    out.write_text(json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def main() -> int:
    pdfs = sorted(FOUNDATION.glob("**/*.pdf"))
    force = "--force" in sys.argv
    results = []
    for p in pdfs:
        side = OUT_DIR / (p.stem + ".json")
        if side.exists() and not force:
            continue
        # Stage 4.8: NO global 45s document timeout. extract_text() now isolates
        # each page in its own subprocess with PAGE_TIMEOUT, so a large-but-valid
        # PDF completes and only a pathological page is reported as failed.
        # (DOCUMENT_TIMEOUT is a last-resort watchdog constant, not an auto-kill.)
        try:
            meta = process_file(p)
            results.append(meta)
        except Exception as e:
            results.append({
                "path": str(p.relative_to(FOUNDATION)),
                "filename": p.name,
                "size": p.stat().st_size,
                "checksum": _checksum(p),
                "pages": _pdf_pages(p),
                "text_length": 0,
                "status": "EXTRACTION_FAILED",
                "error": str(e)[:200],
                "ocr_required": True,
                "full_text": False,
                "chunk_count": 0,
                "failed_pages": [],
            })

    ok = [r for r in results if r["status"] == "OK"]
    partial = [r for r in results if r["status"] == "PARTIAL"]
    fail = [r for r in results if r["status"] not in ("OK", "PARTIAL")]
    print(f"Discovery+Extraction: {len(pdfs)} pdfs | OK={len(ok)} PARTIAL={len(partial)} FAILED={len(fail)}")
    for r in fail:
        print(f"  {r['status']}: {r['filename']} ({r['pages']}p)")
    total_chunks = sum(r.get("chunk_count", 0) for r in ok + partial)
    print(f"Total extractable chunks: {total_chunks}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

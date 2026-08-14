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


def extract_text(path: Path) -> tuple[str, int, list[str]]:
    """Return (joined_text, page_count, per_page_text). Empty text => scanned."""
    if pypdf is None:
        return "", _pdf_pages(path), []
    reader = pypdf.PdfReader(str(path))
    pages_text = []
    for pg in reader.pages:
        try:
            pages_text.append(pg.extract_text() or "")
        except Exception:
            pages_text.append("")
    return "\n".join(pages_text), len(pages_text), pages_text


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
    text, page_count, pages_text = extract_text(path)
    meta["text_length"] = len(text)
    if len(text.strip()) < 200:
        meta["status"] = "EXTRACTION_FAILED"   # scanned / no OCR layer
        meta["ocr_required"] = True
        meta["full_text"] = False
        chunks = []
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
    import multiprocessing as mp

    pdfs = sorted(FOUNDATION.glob("**/*.pdf"))
    force = "--force" in sys.argv
    results = []
    for p in pdfs:
        side = OUT_DIR / (p.stem + ".json")
        if side.exists() and not force:
            continue
        # per-file timeout: a hung pypdf on a big/scanned PDF must not block the run
        q = mp.Queue()
        proc = mp.Process(target=_worker, args=(p, q))
        proc.start()
        proc.join(timeout=45)
        if proc.is_alive():
            proc.kill()
            proc.join()
            meta = {
                "path": str(p.relative_to(FOUNDATION)),
                "filename": p.name,
                "size": p.stat().st_size,
                "checksum": _checksum(p),
                "pages": _pdf_pages(p),
                "text_length": 0,
                "status": "EXTRACTION_TIMEOUT",
                "ocr_required": True,
                "full_text": False,
                "chunk_count": 0,
            }
            out = OUT_DIR / (p.stem + ".json")
            out.write_text(json.dumps({"meta": meta, "chunks": []}, ensure_ascii=False, indent=1), encoding="utf-8")
            results.append(meta)
            print(f"  TIMEOUT: {p.name}")
            continue
        meta = q.get() if not q.empty() else None
        if meta:
            results.append(meta)

    ok = [r for r in results if r["status"] == "OK"]
    fail = [r for r in results if r["status"] != "OK"]
    print(f"Discovery+Extraction: {len(pdfs)} pdfs | OK={len(ok)} FAILED={len(fail)}")
    for r in fail:
        print(f"  {r['status']}: {r['filename']} ({r['pages']}p)")
    total_chunks = sum(r.get("chunk_count", 0) for r in ok)
    print(f"Total extractable chunks: {total_chunks}")
    return 0


def _worker(path: Path, q: "mp.Queue") -> None:
    try:
        q.put(process_file(path))
    except Exception as e:
        q.put({"path": str(path), "filename": path.name, "status": "EXTRACTION_FAILED",
                "error": str(e), "chunk_count": 0})


if __name__ == "__main__":
    sys.exit(main())

"""
fetch_foundation.py — скачивание Knowledge Foundation v1 (только легальные).

Читает docs/architecture/AKB/knowledge_foundation_v1.yaml, качает только
источники с legal != 'copyrighted' в KROFT_KNOWLEDGE_FOUNDATION/<section>/.
Копирайт-книги (legal: copyrighted) пропускаются — их нет в белом списке.

Запуск:
  python fetch_foundation.py            # из корня KROFT_OS
  python fetch_foundation.py --dry-run  # только показать, что скачает
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import yaml

try:
    import requests
except ImportError:
    print("Нужен requests: pip install requests")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YAML_PATH = os.path.join(ROOT, "docs", "architecture", "AKB", "knowledge_foundation_v1.yaml")
OUT_ROOT = os.path.join(ROOT, "KROFT_KNOWLEDGE_FOUNDATION")

# юзер-агент, чтобы archive.org/авторы не банили
HEADERS = {"User-Agent": "KROFT-OS-KnowledgeFoundation/1.0 (research; contact: local)"}


def _slug(s: str) -> str:
    out = []
    for ch in s.lower():
        if ch.isalnum() or ch in (" ", "-"):
            out.append(ch if ch != " " else "_")
        else:
            out.append("_")
    return "".join(out).strip("_")[:80]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    items = data.get("core_v1", []) + data.get("extended", []) + data.get("remaining", [])
    plan = [it for it in items if it.get("legal") not in ("copyrighted", "search_only", "author_page", "web_only", "no_link") and it.get("url")]
    skip = [it for it in items if it.get("legal") == "copyrighted"]

    print(f"Всего в каталоге: {len(items)} | легальных к скачиванию: {len(plan)} | копирайт (пропуск): {len(skip)}")
    if args.dry_run:
        for it in plan:
            print(f"  [dry] {it['section']}/{_slug(it['author']+'_'+it['title'])}.pdf  <- {it['url']}")
        return 0

    os.makedirs(OUT_ROOT, exist_ok=True)
    ok = 0
    for it in plan:
        section = it["section"]
        dest_dir = os.path.join(OUT_ROOT, section)
        os.makedirs(dest_dir, exist_ok=True)
        fname = _slug(it["author"] + "_" + it["title"]) + ".pdf"
        dest = os.path.join(dest_dir, fname)
        if os.path.exists(dest) and os.path.getsize(dest) > 1000:
            print(f"  [skip exists] {section}/{fname}")
            ok += 1
            continue
        try:
            r = requests.get(it["url"], headers=HEADERS, timeout=30, stream=True)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(dest, "wb") as out:
                    out.write(r.content)
                print(f"  [ok] {section}/{fname} ({len(r.content)//1024} KB)")
                ok += 1
            else:
                print(f"  [fail {r.status_code}] {it['url']}")
        except Exception as e:
            print(f"  [err] {it['url']}: {e}")
        time.sleep(0.5)  # вежливость к серверам

    print(f"\nСкачано: {ok}/{len(plan)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

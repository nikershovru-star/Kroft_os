"""KROFT_OS AKB linter (WP-05, TZ-003).

Validates the machine-readable Architecture Knowledge Base:
  - every AKB YAML parses (valid YAML)
  - ADR-*.md <-> adrs.yaml bijection (no orphans either side)
  - RFC status transitions are valid
  - KL forbidden synonyms (glossary aliases) not used in architecture docs
  - accepted/in_progress ADR carries evidence_level (WARN until WP-08 closes F6)

Design: blocking errors -> exit 1 (CI fails). Warnings -> printed, exit 0.
This matches TZ-003 R1: akb-lint is BLOCKING for structural errors, but
evidence-level is WARN (becomes blocking after WP-08 / TZ-002 Wave 2).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
AKB = ROOT / "docs" / "architecture" / "AKB"
ARCH_DIR = ROOT / "docs" / "architecture"

VALID_RFC_TRANSITIONS = {
    "draft": {"under_review", "rejected", "superseded"},
    "under_review": {"decided", "rejected", "superseded"},
    "decided": {"superseded"},
    "rejected": set(),
    "superseded": set(),
    # NOTE: no "None" key on purpose — missing previous_status means initial
    # RFC, handled by .get(prev, {"draft","under_review","decided"}) below.
}
VALID_ADR_STATUSES = {"proposed", "under_review", "accepted", "rejected", "superseded", "in_progress"}


def _err(msg: str):
    print(f"[AKB-LINT ERROR] {msg}")


def _warn(msg: str):
    print(f"[AKB-LINT WARN] {msg}")


def main() -> int:
    errors = 0

    # 1) All AKB YAML parse
    yaml_files = list(AKB.rglob("*.yaml")) + list(AKB.rglob("*.yml"))
    for yf in yaml_files:
        try:
            yaml.safe_load(yf.read_text(encoding="utf-8"))
        except Exception as e:
            _err(f"{yf.relative_to(ROOT)}: YAML parse error: {e}")
            errors += 1
    if not errors:
        print(f"[AKB-LINT] {len(yaml_files)} YAML files parsed OK")

    # 2) ADR bijection
    adr_md = set()
    for f in ARCH_DIR.glob("ADR-*.md"):
        import re
        m = re.search(r"ADR-0*(\d+)", f.name)
        if m:
            adr_md.add(int(m.group(1)))
    adrs_yaml = yaml.safe_load((AKB / "adrs.yaml").read_text(encoding="utf-8"))
    adr_ids = set()
    for a in adrs_yaml.get("adrs", []):
        aid = a.get("id", "")
        m = re.match(r"ADR-0*(\d+)", aid)
        if m:
            adr_ids.add(int(m.group(1)))

    orphans_md = adr_md - adr_ids
    orphans_yaml = adr_ids - adr_md
    if orphans_md:
        _err(f"ADR files without adrs.yaml entry: {sorted(orphans_md)}")
        errors += 1
    if orphans_yaml:
        _err(f"adrs.yaml entries without ADR file: {sorted(orphans_yaml)}")
        errors += 1
    if not errors:
        print(f"[AKB-LINT] ADR bijection OK: {len(adr_md)} files <-> {len(adr_ids)} yaml entries")

    # 3) ADR statuses valid
    for a in adrs_yaml.get("adrs", []):
        st = a.get("status")
        if st not in VALID_ADR_STATUSES:
            _err(f"{a.get('id')}: invalid status '{st}'")
            errors += 1

    # 3b) RFC status transitions (best-effort: parse rfcs.yaml, check transitions field)
    rfcs_path = AKB / "rfcs.yaml"
    if rfcs_path.exists():
        rfcs = yaml.safe_load(rfcs_path.read_text(encoding="utf-8")) or {}
        for r in rfcs.get("rfcs", []):
            rid = r.get("id")
            prev = r.get("previous_status")
            new = r.get("status")
            # No previous_status = initial RFC; allow direct draft/under_review/decided.
            allowed = VALID_RFC_TRANSITIONS.get(prev, {"draft", "under_review", "decided"})
            if new not in allowed:
                _err(f"{rid}: invalid transition {prev} -> {new}")
                errors += 1
        print(f"[AKB-LINT] RFC transitions checked")

    # 5) KL forbidden synonyms (warn, non-blocking)
    # Only TERMINOLOGICAL aliases are linted (not generic English words like
    # API/Event/Data which appear legitimately in ADR prose). Word-boundary
    # match to avoid substring false-positives (e.g. "API" inside a word).
    gloss = yaml.safe_load((AKB / "glossary.yaml").read_text(encoding="utf-8"))
    GENERIC_OK = {
        "API", "Event", "Data", "Info", "Interface", "Layer", "Output",
        "Result", "Source", "Test", "Core", "Engine", "Bootstrap", "Wiring",
        "Pipeline", "Knowledge", "Architecture", "System", "Model",
    }
    forbidden = set()
    for g in gloss.get("glossary", []):
        for alias in g.get("aliases", []):
            if alias not in GENERIC_OK:
                forbidden.add(alias)
    doc_texts = {}
    for md in ARCH_DIR.glob("*.md"):
        doc_texts[md] = md.read_text(encoding="utf-8", errors="ignore")
    found = 0
    import re
    for alias in sorted(forbidden):
        pat = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")
        for md, text in doc_texts.items():
            if pat.search(text):
                _warn(f"{md.name}: forbidden synonym '{alias}' (KL alias)")
                found += 1
                break
    if found:
        print(f"[AKB-LINT] {found} forbidden-synonym mentions (WARN, non-blocking)")
    else:
        print("[AKB-LINT] KL forbidden synonyms: none found")

    # 6) Evidence level on accepted/in_progress (WARN until WP-08)
    missing_ev = []
    for a in adrs_yaml.get("adrs", []):
        if a.get("status") in ("accepted", "in_progress"):
            lvl = a.get("evidence_level") or a.get("evidence")
            if lvl is None:
                missing_ev.append(a.get("id"))
    if missing_ev:
        _warn(f"ADRs without evidence_level (WARN, non-blocking until WP-08): {missing_ev}")
    else:
        print("[AKB-LINT] All accepted/in_progress ADRs carry evidence_level")

    if errors:
        print(f"\n[AKB-LINT] FAILED with {errors} blocking error(s)")
        return 1
    print("\n[AKB-LINT] PASSED (structural OK; warnings above are non-blocking)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

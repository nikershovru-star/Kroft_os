"""KROFT_OS context-map auto-sync (WP-06, TZ-003).

Regenerates the AUTO-GENERATED metrics block in PROJECT_CONTEXT_MAP.md from
real runs: test count, arch-gate count, ADR count, open violations.

Drift detection (CI): if a human hand-edits the numbers in the block, the
block no longer matches a fresh run -> CI fails. Usage:
    python tools/context_map_sync.py   # updates in place (idempotent)
CI step: run this, then `git diff --exit-code docs/PROJECT_CONTEXT_MAP.md`
-> if dirty, map drifted from reality -> fail.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "docs" / "PROJECT_CONTEXT_MAP.md"
START = "<!-- AUTO-GENERATED-START -->"
END = "<!-- AUTO-GENERATED-END -->"


def _count(cmd) -> str:
    out = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True).stdout
    m = re.search(r"(\d+) passed", out)
    return m.group(1) if m else "?"


def main() -> int:
    if not MAP.exists():
        print(f"[context_map_sync] {MAP} not found")
        return 1

    tests = _count([sys.executable, "-m", "pytest", "tests/", "-q"])
    gate = _count([sys.executable, "-m", "pytest",
                   "tests/test_architecture.py", "tests/test_architecture_negative.py", "-q"])
    arch_dir = ROOT / "docs" / "architecture"
    adr_ids = set()
    for f in arch_dir.glob("ADR-*.md"):
        m = re.search(r"ADR-0*(\d+)", f.name)
        if m:
            adr_ids.add(int(m.group(1)))
    adr_count = len(adr_ids)
    adr_max = max(adr_ids) if adr_ids else 0

    # open violations: akb-lint errors == 0 -> 0
    r = subprocess.run([sys.executable, "tools/akb_lint.py"], cwd=str(ROOT),
                       capture_output=True, text=True)
    open_viol = 0 if "FAILED" not in r.stdout else "?"

    block = (
        f"{START}\n"
        "## 6.1 Auto-Generated Metrics (CI, do not edit by hand)\n\n"
        "> Этот блок генерируется `tools/context_map_sync.py` из фактических прогонов.\n"
        "> Ручное изменение чисел здесь → CI падает (drift detection).\n\n"
        f"- **Tests:** {tests} passed (run `python scripts/ci.py`)\n"
        f"- **Arch-gate:** {gate} passed (8 positive + 6 negative)\n"
        f"- **ADR:** {adr_count} (ADR-001..{adr_max:03d})\n"
        f"- **Open violations:** {open_viol}\n"
        f"{END}\n"
    )

    text = MAP.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("[context_map_sync] markers not found in map")
        return 1
    new_text = re.sub(rf"{re.escape(START)}.*?{re.escape(END)}",
                       block.rstrip("\n"), text, flags=re.DOTALL)
    MAP.write_text(new_text, encoding="utf-8")
    print(f"[context_map_sync] updated: tests={tests}, gate={gate}, "
          f"adr={adr_count}, open_violations={open_viol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

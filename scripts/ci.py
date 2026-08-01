"""KROFT_OS local CI pipeline (WP-05, TZ-003).

Single entry point: `python scripts/ci.py [--quick]`.

Stages (blocking unless noted):
  import-check  import all top-level packages        (blocking)
  lint          ruff (if installed)                   (NON-blocking)
  tests         pytest tests/ -q                       (blocking)
  arch-gate     pytest test_architecture*.py -q        (blocking)
  akb-lint      python tools/akb_lint.py               (blocking)
  coverage       pytest --cov report                  (NON-blocking)

--quick: runs only lint + arch-gate + akb-lint (pre-commit subset).

Exit code: 1 if any BLOCKING stage fails. Matches TZ-003 R1: only
arch-gate + akb-lint + tests + import-check are blocking; lint/coverage are
advisory so existing workflow is not broken by strict style rules.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOP_PACKAGES = [
    "kernel", "runtime", "contracts", "composition", "services",
    "adapters", "infrastructure", "policies", "cli", "plugins",
]


def _run(cmd, label, blocking=True):
    print(f"\n{'='*60}\n>>> STAGE: {label}\n>>> {' '.join(cmd)}\n{'='*60}")
    t0 = time.time()
    rc = subprocess.run(cmd, cwd=str(ROOT)).returncode
    dt = time.time() - t0
    if rc == 0:
        print(f"[OK] {label} ({dt:.1f}s)")
    else:
        print(f"[{'FAIL' if blocking else 'WARN'}] {label} ({dt:.1f}s)")
    return rc, blocking


def stage_import_check():
    rc = 0
    for pkg in TOP_PACKAGES:
        p = ROOT / pkg
        if not p.exists():
            continue
        try:
            __import__(pkg)
            print(f"[OK] import {pkg}")
        except Exception as e:
            print(f"[FAIL] import {pkg}: {e}")
            rc = 1
    return rc, True


def stage_lint():
    # ruff optional — non-blocking
    try:
        subprocess.run([sys.executable, "-m", "ruff", "--version"],
                       cwd=str(ROOT), capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[SKIP] ruff not installed (non-blocking)")
        return 0, False
    return _run([sys.executable, "-m", "ruff", "check", "kernel", "runtime",
                 "contracts", "services", "adapters", "infrastructure",
                 "policies", "composition", "cli"], "lint", blocking=False)


def main():
    quick = "--quick" in sys.argv
    overall_fail = False
    start = time.time()

    # 1) import-check (blocking)
    rc, blk = stage_import_check()
    overall_fail |= (rc != 0 and blk)

    # 2) lint (non-blocking)
    rc, blk = stage_lint()
    overall_fail |= (rc != 0 and blk)

    if not quick:
        # 3) tests (blocking)
        rc, blk = _run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       "tests", blocking=True)
        overall_fail |= (rc != 0 and blk)

    # 4) arch-gate (blocking)
    rc, blk = _run([sys.executable, "-m", "pytest",
                   "tests/test_architecture.py", "tests/test_architecture_negative.py",
                   "-q"], "arch-gate", blocking=True)
    overall_fail |= (rc != 0 and blk)

    # 5) akb-lint (blocking)
    rc, blk = _run([sys.executable, "tools/akb_lint.py"], "akb-lint", blocking=True)
    overall_fail |= (rc != 0 and blk)

    # 6) coverage (non-blocking)
    if not quick:
        try:
            subprocess.run([sys.executable, "-m", "pytest", "--cov=kernel",
                            "--cov=services", "--cov-report=term-missing", "tests/",
                            "-q"], cwd=str(ROOT), capture_output=True, timeout=240)
            print("[OK] coverage report generated (non-blocking)")
        except Exception as e:
            print(f"[WARN] coverage skipped: {e}")

    total = time.time() - start
    print(f"\n{'='*60}\nCI TOTAL: {total:.1f}s -> "
          f"{'FAILED' if overall_fail else 'GREEN'}\n{'='*60}")
    sys.exit(1 if overall_fail else 0)


if __name__ == "__main__":
    main()

"""KROFT_OS live-test CI job (ADR-0XX, P2-F).

Separate CI entry point for *_LIVE gated tests. Does NOT modify scripts/ci.py
(TZ-003 R1 blocking set stays intact). Live tests are gated by env flags
(<X>_LIVE) via pytest.mark.skipif; this job raises all flags and runs only the
live/integration test files in a dedicated process/job.

By default NON-blocking: live tests require a local Ollama / network, so in a CI
matrix this is a separate job. Pass --strict to fail the job on any live failure.

Usage:
  python scripts/ci_live.py            # run live tests, exit 0 unless collection error
  python scripts/ci_live.py --strict  # exit 1 on live test failures
  python scripts/ci_live.py --list    # print discovered live files and exit
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# All env gates that live tests consult via pytest.mark.skipif(not <X>_LIVE).
LIVE_ENV_FLAGS = [
    "AGENT_LIVE", "AUTONOMY_LIVE", "DESKTOP_LIVE", "EMBED_LIVE",
    "KNOWLEDGE_LIVE", "LEARNING_LIVE", "LLM_LIVE", "MEMORY_LIVE",
    "OLLAMA_LIVE", "OMNIROUTE_LIVE", "OPTIMIZATION_LIVE", "WORKFLOW_LIVE",
]


def collect_live_files() -> list[Path]:
    """Deterministically find live/integration test files (pathlib glob)."""
    files: list[Path] = []
    seen: set[Path] = set()
    for pat in ("*live*.py", "*integration*.py"):
        for p in ROOT.glob(f"tests/**/{pat}"):
            if p.name.startswith("test_") and p not in seen:
                seen.add(p)
                files.append(p)
    return sorted(files)


def _run(files: list[Path], strict: bool) -> int:
    env = os.environ.copy()
    for flag in LIVE_ENV_FLAGS:
        env[flag] = "1"
    cmd = [sys.executable, "-m", "pytest", *[str(f) for f in files], "-q", "-p", "no:cacheprovider"]
    print(f"\n{'='*60}\n>>> LIVE CI: {len(files)} files, flags={LIVE_ENV_FLAGS}\n{'='*60}")
    t0 = time.time()
    rc = subprocess.run(cmd, cwd=str(ROOT), env=env).returncode
    dt = time.time() - t0
    if rc == 0:
        print(f"[OK] live job ({dt:.1f}s)")
    else:
        print(f"[{'FAIL' if strict else 'WARN'}] live job ({dt:.1f}s)")
    return rc if strict else 0


def main() -> int:
    args = sys.argv[1:]
    strict = "--strict" in args
    files = collect_live_files()
    if "--list" in args:
        for f in files:
            print(f.relative_to(ROOT))
        return 0
    if not files:
        print("[WARN] no live test files discovered")
        return 0
    return _run(files, strict)


if __name__ == "__main__":
    sys.exit(main())

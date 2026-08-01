"""KROFT_OS pre-commit fallback (no pre-commit framework needed).

Runs the fast CI subset before a commit. Usage:
    python scripts/precommit.py
Exit 1 if any blocking stage fails (abort commit).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    rc = subprocess.run([sys.executable, "scripts/ci.py", "--quick"],
                        cwd=str(ROOT)).returncode
    if rc != 0:
        print("\n[pre-commit] BLOCKING checks failed — commit aborted.")
        sys.exit(1)
    print("\n[pre-commit] OK — proceed with commit.")
    sys.exit(0)


if __name__ == "__main__":
    main()

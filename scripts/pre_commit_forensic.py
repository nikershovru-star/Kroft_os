#!/usr/bin/env python3
"""Pre-commit forensic gate (P0-coord).

Scans staged NEW files for duplicate class/module/ADR names against the
entire repository. If a match is found, prints a warning and exits 1
(blocking the commit). If no match, exits 0 (allowing the commit).

Usage (as a pre-commit hook):
    python scripts/pre-commit-forensic.py --staged-files "path1 path2 ..."

Usage (manual, for testing):
    python scripts/pre-commit-forensic.py --file path/to/new_file.py
    python scripts/pre-commit-forensic.py --name SomeClass --type class
    python scripts/pre-commit-forensic.py --name ADR-0XX --type adr

The script supports two modes:
1. --staged-files: scans all provided files for new class/module/ADR definitions
2. --file / --name + --type: checks a specific artifact name/type

Exit codes:
    0 = OK, no duplicates found
    1 = DUPLICATE DETECTED, commit blocked
    2 = Error (e.g. missing arguments, file not found)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

# Patterns for extracting artifact names from source files
CLASS_PATTERN = re.compile(r"^\s*class\s+(\w+)\s*[:\(]")
ADR_PATTERN = re.compile(r"(ADR-\d{3,})", re.IGNORECASE)
MODULE_PATTERN = re.compile(r"^def\s+(\w+)\s*\(")

# File extensions to scan for classes/functions
SCAN_EXTENSIONS = {".py", ".md"}

# Directories to ignore during searching
IGNORE_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules", "venv", ".venv"}


def _find_repo_root() -> str:
    """Find the repository root by looking for .git directory."""
    path = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        parent = os.path.dirname(path)
        if os.path.isdir(os.path.join(parent, ".git")):
            return parent
        path = parent
    return path


def _extract_artifacts_from_file(filepath: str) -> list[tuple[str, str]]:
    """Extract class names and ADR references from a file.

    Returns a list of (artifact_name, artifact_type) tuples.
    """
    artifacts: list[tuple[str, str]] = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return artifacts

    # Extract class definitions
    for match in CLASS_PATTERN.finditer(content):
        artifacts.append((match.group(1), "class"))

    # Extract ADR references (from filenames or content)
    filename = os.path.basename(filepath)
    adr_match = ADR_PATTERN.search(filename)
    if adr_match:
        artifacts.append((adr_match.group(1).upper(), "adr"))
    for match in ADR_PATTERN.finditer(content):
        artifacts.append((match.group(1).upper(), "adr"))

    return artifacts


def _scan_repository_for_artifact(
    name: str,
    artifact_type: str,
    repo_root: str,
    new_files: set[str] | None = None,
) -> list[str]:
    """Search the repository for an existing artifact with the given name.

    Args:
        name: The artifact name to search for (e.g. "MyClass").
        artifact_type: "class", "adr", or "module".
        repo_root: Root directory of the repository.
        new_files: Set of file paths to exclude from search (new files being added).

    Returns:
        List of file paths where the artifact was found (excluding new_files).
    """
    results: list[str] = []
    new_files = new_files or set()

    if _try_rg_search(name, repo_root, results, new_files, artifact_type):
        return results

    return _py_search(name, repo_root, results, new_files, artifact_type)


def _try_rg_search(
    name: str,
    repo_root: str,
    results: list[str],
    new_files: set[str],
    artifact_type: str,
) -> bool:
    """Try searching using ripgrep. Returns True if rg was used."""
    try:
        result = subprocess.run(
            ["rg", "--no-heading", "-l", "-F", name, "--glob", "*.py", "--glob", "*.md"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line and line not in new_files:
                    results.append(line)
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def _py_search(
    name: str,
    repo_root: str,
    results: list[str],
    new_files: set[str],
    artifact_type: str,
) -> list[str]:
    """Fallback file scanner using Python os.walk (slower but no dependencies)."""
    for dirpath, _, filenames in os.walk(repo_root):
        # Skip ignored directories
        parts = set(os.path.relpath(dirpath, repo_root).split(os.sep))
        if parts & IGNORE_DIRS:
            continue

        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext not in SCAN_EXTENSIONS:
                continue

            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, repo_root)

            # Skip new files being added in this commit
            if rel_path in new_files or filepath in new_files:
                continue

            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            if name in content:
                results.append(rel_path)

    return results


def _check_staged_files(staged_files: list[str]) -> int:
    """Check for duplicates among all new artifacts in staged files."""
    repo_root = _find_repo_root()
    new_files: set[str] = set()

    for filepath in staged_files:
        if not os.path.exists(filepath):
            continue
        # Convert to relative path if within repo; absolute path if outside
        abs_path = os.path.abspath(filepath)
        try:
            rel_path = os.path.relpath(abs_path, repo_root)
            new_files.add(rel_path)
            new_files.add(abs_path)
        except ValueError:
            # File outside repo (e.g. /tmp) — skip it for repo scanning
            continue

    found_duplicates: list[str] = []

    for filepath in staged_files:
        if not os.path.exists(filepath):
            continue

        artifacts = _extract_artifacts_from_file(filepath)
        rel_path = os.path.relpath(filepath, repo_root)

        for name, kind in artifacts:
            # Skip tests/ and docs/ directories for class definitions
            if kind == "class" and "tests" in rel_path:
                continue
            if kind == "adr" and "docs" in rel_path:
                continue

            matches = _scan_repository_for_artifact(name, kind, repo_root, new_files)
            if matches:
                found_duplicates.append(
                    f"DUPLICATE: '{name}' ({kind}) in {rel_path} "
                    f"already exists in: {', '.join(matches)}"
                )

    if found_duplicates:
        print("=" * 60)
        print("PRE-COMMIT FORENSIC GATE: DUPLICATES DETECTED")
        print("=" * 60)
        for dup in found_duplicates:
            print(f"  ⚠️  {dup}")
        print()
        print("Commit blocked. If this is a false positive, verify the file paths")
        print("or remove the duplicate. To force commit (use with caution),")
        print("bypass this hook with: git commit --no-verify")
        print("=" * 60)
        return 1

    print("Pre-commit forensic gate: no duplicates found. ✓")
    return 0


def _check_single(name: str, artifact_type: str) -> int:
    """Check a single artifact name against the repository."""
    repo_root = _find_repo_root()
    matches = _scan_repository_for_artifact(name, artifact_type, repo_root, set())

    if matches:
        print("=" * 60)
        print(f"PRE-COMMIT FORENSIC GATE: DUPLICATE FOUND")
        print("=" * 60)
        print(f"  Artifact: '{name}' (type: {artifact_type})")
        print(f"  Found in: {', '.join(matches)}")
        print()
        print("Commit blocked.")
        return 1

    print(f"Forensic gate: '{name}' is unique. ✓")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Pre-commit forensic gate (P0-coord) — prevents duplicate artifacts."
    )
    parser.add_argument(
        "--staged-files",
        nargs="+",
        default=None,
        help="List of staged file paths to scan for duplicates.",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Single file to check (alternative to --staged-files).",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Artifact name to check (use with --type).",
    )
    parser.add_argument(
        "--type",
        choices=["class", "adr", "module"],
        default="class",
        help="Type of artifact to check (default: class).",
    )

    args = parser.parse_args()

    if args.staged_files:
        return _check_staged_files(args.staged_files)

    if args.file and args.name:
        return _check_single(args.name, args.type)

    if args.name:
        return _check_single(args.name, args.type)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
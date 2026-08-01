"""Plugin loader — discover / validate / load component manifests.

Per Phase 2 (variant b): NO wrapper files. Manifests live in plugins/<name>/manifest.yaml.
The loader discovers them, validates the schema, and returns Manifest objects. It does
NOT instantiate platforms (they need injected ports) — the composition root builds the
real instances and passes them to ComponentRegistry.activate_platform.

Imports ONLY contracts + stdlib (arch-gate LAW K8). YAML parsed with a minimal
dependency-free parser fallback (PyYAML if available).
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from runtime.manifest_schema import Manifest


def _load_yaml(text: str) -> dict:
    """Parse a minimal YAML subset (top-level mapping) without external deps."""
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text) or {}
    except Exception:
        pass
    # Minimal fallback: top-level `key: value` / `key: [a, b]` / `key: true|false`.
    data: Dict[str, object] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        v = val.strip()
        if v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            data[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()] if inner else []
        elif v.lower() in ("true", "false"):
            data[key] = v.lower() == "true"
        elif v == "":
            data[key] = ""
        else:
            data[key] = v.strip("'\"")
    return data


def discover(plugins_dir: Path) -> List[Manifest]:
    """Find all plugins/*/manifest.yaml and parse them into Manifests."""
    if not plugins_dir.exists():
        return []
    manifests: List[Manifest] = []
    for manifest_path in sorted(plugins_dir.glob("*/manifest.yaml")):
        text = manifest_path.read_text(encoding="utf-8")
        data = _load_yaml(text)
        if not data.get("name"):
            continue
        manifests.append(Manifest.from_dict(data))
    return manifests


def validate(manifests: List[Manifest]) -> List[str]:
    """Return a list of validation errors (empty == all valid)."""
    errors: List[str] = []
    for m in manifests:
        if not m.name:
            errors.append("manifest missing 'name'")
        if not m.entrypoint:
            errors.append(f"manifest {m.name!r} missing 'entrypoint'")
    return errors

"""KROFT_OS v5 — Config Loader (Stage 15).

Reads ``kroft_os.yaml`` (preferred) or ``kroft_os.json`` (fallback) from
the vault root via the ``IFileSystem`` port. Resolves effective configuration
by merging YAML/JSON with CLI arguments:

    CLI arg (if not None)  >  config file value  >  hardcoded default

Design constraints (honest limitations):
- YAML is optional (``pyyaml``); if missing we fall back to JSON parsing.
- No schema validation: unknown top-level keys emit a ``warnings.warn`` and are
  ignored (not an error).
- Config is read ONCE per command (no hot-reload).
- Only CLI args and YAML override; no environment-variable override.
- ``vault`` in the file is relative to the config file's directory (the vault
  root) and is resolved by the CLI, not here.
- Flat config only: no profiles / sections.

Depends only on ``contracts.IFileSystem`` + stdlib (json, warnings, typing).
"""
from __future__ import annotations

import json
import warnings
from typing import Any, Dict, Optional, Tuple

try:  # pragma: no cover - exercised by import environment
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:  # pragma: no cover - fallback path
    yaml = None  # type: ignore
    _HAS_YAML = False

from contracts import IFileSystem


# Candidate filenames, in priority order (YAML preferred, JSON fallback).
_CONFIG_FILENAMES: Tuple[str, ...] = (
    "kroft_os.yaml",
    "kroft_os.yml",
    "kroft_os.json",
)

# Hardcoded defaults (lowest priority).
DEFAULT_AUTOSAVE_INTERVAL = 60.0

# Known top-level config keys; anything else triggers a warning (not an error).
_KNOWN_KEYS = frozenset({"vault", "autosave_interval", "features"})


class ConfigLoader:
    """Loads and merges KROFT_OS v5 per-vault configuration."""

    def __init__(
        self,
        config_filenames: Tuple[str, ...] = _CONFIG_FILENAMES,
        known_keys: frozenset = _KNOWN_KEYS,
        default_autosave: float = DEFAULT_AUTOSAVE_INTERVAL,
    ) -> None:
        self._config_filenames = config_filenames
        self._known_keys = known_keys
        self._default_autosave = default_autosave

    # -- load ---------------------------------------------------------------
    def load(self, vault_path: str, fs: IFileSystem) -> Dict[str, Any]:
        """Return the parsed config dict, or ``{}`` if none found / unreadable.

        Never raises: a missing or broken config file degrades to ``{}`` so the
        CLI falls back to its defaults.
        """
        for name in self._config_filenames:
            try:
                if not fs.exists(name):
                    continue
                raw = fs.read_content(name)
            except Exception:
                # I/O or traversal error -> treat as missing, try next candidate
                continue
            parsed = self._parse(raw, name)
            if parsed is not None:
                return parsed
        return {}

    def _parse(self, raw: str, name: str) -> Optional[Dict[str, Any]]:
        """Parse raw text into a dict; return ``None`` on any failure."""
        is_json = name.endswith(".json")
        if is_json or not _HAS_YAML:
            try:
                data = json.loads(raw)
            except Exception:
                return None
        else:
            try:
                data = yaml.safe_load(raw)
            except Exception:
                # Broken YAML -> no JSON fallback (would be misleading); return {}.
                return None
        if not isinstance(data, dict):
            return {}
        self._validate(data)
        return data

    def _validate(self, data: Dict[str, Any]) -> None:
        for key in data:
            if key not in self._known_keys:
                warnings.warn(
                    f"Unknown config key ignored: {key!r}",
                    stacklevel=3,
                )

    # -- merge ---------------------------------------------------------------
    def merge_with_cli(
        self,
        cli_args: Any,
        config: Dict[str, Any],
        defaults: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Merge config with CLI args. Priority: CLI > config > default.

        ``cli_args`` is any object exposing attribute access (argparse.Namespace).
        """
        defaults = defaults or {}
        autosave_default = float(
            defaults.get("autosave_interval", self._default_autosave)
        )

        cli_autosave = getattr(cli_args, "autosave", None)
        cfg_autosave = config.get("autosave_interval")

        if cli_autosave is not None:
            autosave = float(cli_autosave)
        elif cfg_autosave is not None:
            autosave = float(cfg_autosave)
        else:
            autosave = autosave_default

        cli_vault = getattr(cli_args, "vault", None)
        cfg_vault = config.get("vault")
        vault = cli_vault if cli_vault is not None else cfg_vault

        features = config.get("features") or {}

        return {
            "autosave_interval": autosave,
            "vault": vault,
            "features": features,
        }

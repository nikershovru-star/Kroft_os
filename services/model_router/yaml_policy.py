"""YAML-backed router policy — loads keyword/category rules from config (ТЗ-ECHO, E2).

Implements ``contracts.i_router_policy.IRouterPolicy``. Pure decision logic: reads
``config/router_policy.yaml`` and maps a ``ModelQuery`` to a category + ordered provider
name list. No network I/O. PyYAML is the only third-party dep (already a hard runtime dep).

K1: stdlib + contracts + PyYAML only. Reuses ProviderSpec (contracts.i_model_router) as a
routing-only VO (name + priority; base_url left empty — the IModelRouter owns the real
endpoint, so NO fake URL is manufactured here, G1 fix).

E2 hardening vs E1:
  - token-boundary matching for single-word keywords (G5: "def" no longer matches "definition");
  - deterministic category priority (G6: explicit ``priority`` list in YAML breaks ties);
  - load-time validation (STEP 17/19): missing default/categories/providers -> fail-fast.
"""

from __future__ import annotations

import os
import re
from typing import List

import yaml

from contracts.i_llm import ModelQuery
from contracts.i_model_router import ProviderSpec
from contracts.i_router_policy import IRouterPolicy


# Single-word keywords must match on a token boundary (not as a substring of a longer
# word). Multi-word keywords (contain a space) are matched as a phrase (substring).
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)


class YamlRouterPolicy(IRouterPolicy):
    """Rule policy loaded from a YAML file (config/router_policy.yaml)."""

    def __init__(self, policy_path: str) -> None:
        self._path = policy_path
        with open(policy_path, "r", encoding="utf-8") as fh:
            self._cfg = yaml.safe_load(fh) or {}
        # --- load-time validation (STEP 17/19) ---
        if not isinstance(self._cfg, dict):
            raise ValueError(f"router policy {policy_path}: top-level must be a mapping")
        categories = self._cfg.get("categories") or {}
        if not isinstance(categories, dict) or not categories:
            raise ValueError(f"router policy {policy_path}: 'categories' missing/empty")
        default = str(self._cfg.get("default", "analytical"))
        if default not in categories:
            raise ValueError(f"router policy {policy_path}: default '{default}' not in categories")
        # validate each category shape
        for name, body in categories.items():
            if not isinstance(body, dict):
                raise ValueError(f"router policy: category '{name}' must be a mapping")
            if not isinstance(body.get("providers") or [], list):
                raise ValueError(f"router policy: category '{name}' providers must be a list")
            if not isinstance(body.get("keywords") or [], list):
                raise ValueError(f"router policy: category '{name}' keywords must be a list")
        self._default = default
        self._categories: dict[str, dict] = categories
        # Deterministic category priority (G6): explicit ordered list in YAML; unknown
        # categories sort last so a known category always wins a tie.
        prio = self._cfg.get("priority") or []
        self._priority = list(prio) + [c for c in categories if c not in prio]
        # manual_overrides (E3): explicit substring -> category, checked before keywords.
        overrides = self._cfg.get("manual_overrides") or []
        self._overrides: list[tuple[str, str]] = []
        for o in overrides:
            if not isinstance(o, dict):
                raise ValueError(f"router policy: manual_overrides entries must be mappings")
            m = str(o.get("match") or "").lower()
            c = str(o.get("category") or "")
            if not m or c not in categories:
                raise ValueError(
                    f"router policy: manual_override {o!r} needs valid 'match' + 'category'"
                )
            self._overrides.append((m, c))

    # --- E3 config access ---
    def classifier_config(self) -> dict:
        """Return the ``classifier:`` section of the YAML (E3 LLM typer config).

        Callers (run_kroft) read ``enabled`` / ``model`` / ``timeout`` / ``fallback``
        from here so the classifier wiring is driven by config, not hardcoded env.
        Returns ``{}`` when the section is absent (classifier disabled by default).
        """
        cfg = self._cfg.get("classifier")
        return cfg if isinstance(cfg, dict) else {}

    @classmethod
    def load_default(cls, base_dir: str = "") -> "YamlRouterPolicy":
        """Load config/router_policy.yaml relative to ``base_dir`` (or repo root)."""
        cand = os.path.join(base_dir, "config", "router_policy.yaml")
        if not os.path.exists(cand):
            cand = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "config",
                "router_policy.yaml",
            )
        if not os.path.exists(cand):
            raise FileNotFoundError(f"router policy not found: {cand}")
        return cls(cand)

    # --- IRouterPolicy ---
    def classify(self, query: ModelQuery) -> str:
        text = (query.prompt or "").lower()
        # manual_overrides (E3): explicit substring -> category, before keyword rules.
        for sub, cat in self._overrides:
            if sub in text:
                return cat
        tokens = set(_TOKEN_RE.findall(text))
        # Deterministic priority order (G6): iterate self._priority, first category whose
        # ANY keyword matches wins. Multi-match resolves by declared priority, not YAML order.
        for name in self._priority:
            body = self._categories.get(name)
            if not body:
                continue
            for kw in (body.get("keywords") or []):
                kw = str(kw).lower()
                if " " in kw:
                    if kw in text:  # phrase: substring match
                        return name
                else:
                    if kw in tokens:  # single word: token-boundary match (G5)
                        return name
        return self._default

    def providers_for(self, category: str) -> List[ProviderSpec]:
        body = self._categories.get(category) or self._categories.get(self._default) or {}
        names = [str(n) for n in (body.get("providers") or [])]
        # Routing-only specs: name + priority (list order = priority). base_url stays empty;
        # the IModelRouter resolves the real endpoint (no fake URL, G1 fix).
        return [ProviderSpec(name=n, priority=i) for i, n in enumerate(names)]

    def categories(self) -> List[str]:
        return list(self._categories.keys())

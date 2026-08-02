"""Secret Manager (TZ-SEC-001 WP-04, ADR-032).

Loads secrets from environment / .env (never committed). Masks any secret value
on display, in logs, in audit records, and blocks storage of raw secrets.
K1-compliant for services: imports ONLY contracts + stdlib.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Optional

from contracts.security import ISecretManager

_SECRET_RE = re.compile(r"(sk|pk|token|api[_-]?key|password|secret|client[_-]?secret)[\"'=:\s]+([\w\-./]{6,})", re.IGNORECASE)

# Providers we know about (for documentation / validation only).
KNOWN_PROVIDERS = [
    "OpenAI", "OpenRouter", "GitHub", "Anthropic", "Gemini", "DeepSeek",
    "Telegram", "Discord", "SMTP", "SSH", "Git",
]


class SecretManager(ISecretManager):
    def __init__(self, env: Optional[Dict[str, str]] = None) -> None:
        self._env = dict(env) if env is not None else dict(os.environ)

    def get(self, key: str) -> str:
        val = self._env.get(key)
        if val is None:
            raise KeyError(f"secret {key} not found")
        return val

    def has(self, key: str) -> bool:
        return key in self._env

    def mask(self, value: str) -> str:
        """Mask a secret: keep first 4 + last 4, replace middle with ****."""
        if not value:
            return ""
        if len(value) <= 8:
            return "*" * len(value)
        return value[:4] + "****" + value[-4:]

    def safe_log(self, text: str) -> str:
        """Redact any secret-like substring from a log/audit line."""
        return _SECRET_RE.sub(lambda m: f"{m.group(1)}={self.mask(m.group(2))}", text)

    def redact_for_storage(self, text: str) -> str:
        """Block storing raw secrets: replace with masked form."""
        return self.safe_log(text)

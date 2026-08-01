"""Simple in-memory auth + session store (Stage 28).

Single-user basic auth for the Web UI. Credentials and session tokens live
in RAM only — no persistent users, no DB, no HTTPS (honest limitations).

Architecture contract: services/ may import ONLY contracts + stdlib.
This module needs just ``secrets`` (timing-safe compare + token generation).
"""
from __future__ import annotations

import secrets
from typing import Optional, Set


class SimpleAuthService:
    """Basic auth for single-user mode. Credentials live in RAM only."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._sessions: Set[str] = set()

    def check_credentials(self, username: str, password: str) -> bool:
        """Timing-attack-resistant comparison (secrets.compare_digest).

        Both comparisons always run (no short-circuit leak of username
        validity via response timing).
        """
        user_ok = secrets.compare_digest(
            username.encode("utf-8"), self._username.encode("utf-8")
        )
        pass_ok = secrets.compare_digest(
            password.encode("utf-8"), self._password.encode("utf-8")
        )
        return user_ok and pass_ok

    def create_session(self) -> str:
        """Random 32-byte hex token registered as a live session."""
        token = secrets.token_hex(32)
        self._sessions.add(token)
        return token

    def validate_session(self, token: Optional[str]) -> bool:
        return token is not None and token in self._sessions

    def revoke_session(self, token: Optional[str]) -> None:
        if token:
            self._sessions.discard(token)

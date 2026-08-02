"""Audit Logger (TZ-SEC-001 WP-07). In-memory + optional JSONL sink.

Records every tool/memory/shell/git/filesystem call with timestamp, agent, tool,
arguments (secrets masked), result, duration, status. The chain is append-only;
tamper-evidence via a running SHA-256 over records (checksum chain) lets a
verifier detect deletion/modification (R3 of TZ-SEC-001).
K1-compliant for services: contracts + stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import List, Optional

from contracts.security import AuditRecord, IAuditLogger


class AuditLogger(IAuditLogger):
    def __init__(self, sink_path: Optional[str] = None) -> None:
        self._records: List[AuditRecord] = []
        self._lock = threading.Lock()
        self._chain_hash = hashlib.sha256(b"").hexdigest()
        self._sink = Path(sink_path) if sink_path else None

    def log(self, record: AuditRecord) -> None:
        with self._lock:
            # checksum chain: hash(prev_hash || record_json)
            rec_json = json.dumps(record.__dict__, sort_keys=True, default=str)
            self._chain_hash = hashlib.sha256(
                (self._chain_hash + rec_json).encode("utf-8")
            ).hexdigest()
            self._records.append(record)
            if self._sink:
                with self._sink.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"h": self._chain_hash, **record.__dict__},
                                       default=str) + "\n")

    def tail(self, limit: int = 100) -> List[AuditRecord]:
        with self._lock:
            return list(self._records[-limit:])

    @property
    def chain_hash(self) -> str:
        with self._lock:
            return self._chain_hash

    def verify_chain(self) -> bool:
        """Recompute the chain from stored records; True if intact."""
        with self._lock:
            h = hashlib.sha256(b"").hexdigest()
            for r in self._records:
                rec_json = json.dumps(r.__dict__, sort_keys=True, default=str)
                h = hashlib.sha256((h + rec_json).encode("utf-8")).hexdigest()
            return h == self._chain_hash


def make_record(agent_id: str, tool: str, arguments: str, result: str,
                duration_ms: float, status: str) -> AuditRecord:
    return AuditRecord(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        agent_id=agent_id, tool=tool, arguments=arguments,
        result=result, duration_ms=duration_ms, status=status,
    )

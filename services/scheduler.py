"""Task Scheduler — cron-like job runner for KnowledgeOS (Stage 35)."""
from __future__ import annotations

import json
import os
import sched
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from contracts import IFileSystem


@dataclass
class Job:
    id: str
    cron_expr: str  # simplified: "every N seconds" or "daily HH:MM"
    command: str
    next_run: float = 0.0
    enabled: bool = True


class SchedulerService:
    """In-memory scheduler with JSON persistence."""

    def __init__(self, clock: Optional[Callable[[], float]] = None,
                 fs: Optional[IFileSystem] = None) -> None:
        self._sched = sched.scheduler(clock or time.time, time.sleep)
        self._jobs: Dict[str, Job] = {}
        self._counter = 0
        self._executor: Optional[Callable[[str], Any]] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._snapshot_path: Optional[str] = None

    def set_executor(self, fn: Callable[[str], Any]) -> None:
        self._executor = fn

    def add(self, cron_expr: str, command: str) -> str:
        with self._lock:
            self._counter += 1
            jid = f"job-{self._counter}"
            job = Job(id=jid, cron_expr=cron_expr, command=command)
            job.next_run = self._compute_next(cron_expr)
            self._jobs[jid] = job
            self._schedule(job)
            return jid

    def cancel(self, jid: str) -> bool:
        with self._lock:
            if jid in self._jobs:
                self._jobs[jid].enabled = False
                return True
            return False

    def list_jobs(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {"id": j.id, "cron": j.cron_expr, "command": j.command,
                 "next_run": j.next_run, "enabled": j.enabled}
                for j in self._jobs.values()
            ]

    def _compute_next(self, cron_expr: str) -> float:
        """Simplified: 'every N' -> N seconds from now; 'daily HH:MM' -> today or tomorrow."""
        parts = cron_expr.strip().split()
        if parts[0] == "every" and len(parts) == 2:
            return time.time() + int(parts[1])
        if parts[0] == "daily" and len(parts) == 2:
            hh, mm = map(int, parts[1].split(":"))
            now = time.localtime()
            t = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hh, mm, 0, 0, 0, -1))
            if t <= time.time():
                t += 86400
            return t
        return time.time() + 60  # default 1 min

    def _schedule(self, job: Job) -> None:
        if not job.enabled or job.next_run <= time.time():
            return
        delay = job.next_run - time.time()
        self._sched.enter(delay, 1, self._run, argument=(job.id,))

    def _run(self, jid: str) -> None:
        with self._lock:
            job = self._jobs.get(jid)
            if not job or not job.enabled:
                return
        if self._executor:
            try:
                self._executor(job.command)
            except Exception:
                pass
        # reschedule
        with self._lock:
            job.next_run = self._compute_next(job.cron_expr)
            self._schedule(job)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._sched.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        for ev in list(self._sched.queue):
            try:
                self._sched.cancel(ev)
            except ValueError:
                pass

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": 1,
                "jobs": [
                    {"id": j.id, "cron": j.cron_expr, "command": j.command, "enabled": j.enabled}
                    for j in self._jobs.values()
                ],
            }

    def restore(self, data: Dict[str, Any]) -> None:
        if not data or "jobs" not in data:
            return
        for item in data.get("jobs", []):
            if item.get("enabled", True):
                self.add(item["cron"], item["command"])

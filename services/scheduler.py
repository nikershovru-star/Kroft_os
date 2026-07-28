"""Task Scheduler — cron-like job runner for KnowledgeOS (Stage 35 + 38)."""
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


@dataclass
class ExecutionRecord:
    job_id: str
    command: str
    started_at: float
    finished_at: float
    success: bool
    output: str = ""


class SchedulerService:
    """In-memory scheduler with JSON persistence + JSON Lines execution log."""

    def __init__(self, clock: Optional[Callable[[], float]] = None,
                 fs: Optional[IFileSystem] = None,
                 persistence_path: Optional[str] = None,
                 log_path: Optional[str] = None) -> None:
        self._sched = sched.scheduler(clock or time.time, time.sleep)
        self._jobs: Dict[str, Job] = {}
        self._counter = 0
        self._executor: Optional[Callable[[str], Any]] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._persistence_path = persistence_path
        self._log_path = log_path
        self._history: List[Dict[str, Any]] = []  # in-proc ring buffer
        self.load()  # auto-restore on boot

    def set_executor(self, fn: Callable[[str], Any]) -> None:
        self._executor = fn

    def add(self, cron_expr: str, command: str, jid: Optional[str] = None) -> str:
        with self._lock:
            if jid is None:
                self._counter += 1
                jid = f"job-{self._counter}"
            job = Job(id=jid, cron_expr=cron_expr, command=command)
            job.next_run = self._compute_next(cron_expr)
            self._jobs[jid] = job
            self._schedule(job)
            self._save_under_lock()
            return jid

    def cancel(self, jid: str) -> bool:
        with self._lock:
            if jid in self._jobs:
                self._jobs[jid].enabled = False
                self._save_under_lock()
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
        started = time.time()
        success = True
        output = ""
        with self._lock:
            job = self._jobs.get(jid)
            if not job or not job.enabled:
                return
        if self._executor:
            try:
                result = self._executor(job.command)
                output = json.dumps(result, ensure_ascii=False)[:500]
            except Exception as exc:
                success = False
                output = str(exc)[:500]
        finished = time.time()
        record = {
            "job_id": jid,
            "command": job.command,
            "started_at": started,
            "finished_at": finished,
            "success": success,
            "output": output,
        }
        with self._lock:
            self._history.append(record)
            if len(self._history) > 1000:
                self._history = self._history[-1000:]
            if self._log_path:
                try:
                    os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
                    with open(self._log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception:
                    pass
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
        # Caller must hold self._lock (also invoked from _save_under_lock).
        return {
            "version": 1,
            "jobs": [
                {"id": j.id, "cron": j.cron_expr, "command": j.command, "enabled": j.enabled}
                for j in self._jobs.values()
            ],
        }

    def _save_under_lock(self) -> None:
        # Assumes self._lock is already held by the caller (add/cancel/restore).
        if not self._persistence_path:
            return
        try:
            os.makedirs(os.path.dirname(self._persistence_path), exist_ok=True)
            with open(self._persistence_path, "w", encoding="utf-8") as f:
                json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save(self) -> None:
        # Public, lock-safe entry point (e.g. atexit). Snapshots under lock.
        with self._lock:
            self._save_under_lock()

    def load(self) -> None:
        if not self._persistence_path or not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.restore(data)
        except Exception:
            pass

    def restore(self, data: Dict[str, Any]) -> None:
        if not data or "jobs" not in data:
            return
        for item in data.get("jobs", []):
            if item.get("enabled", True):
                self.add(item["cron"], item["command"], jid=item["id"])

    def history(self, job_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            records = self._history
            if job_id:
                records = [r for r in records if r["job_id"] == job_id]
            # newest first
            return list(reversed(records))

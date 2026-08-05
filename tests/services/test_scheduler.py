"""Stage 35 - Task Scheduler tests (6)."""
import time

import pytest

from services import SchedulerService


class TestScheduler:
    def test_add_job(self):
        s = SchedulerService()
        jid = s.add("every 3600", "find python")
        assert jid.startswith("job-")
        assert len(s.list_jobs()) == 1

    def test_cancel_job(self):
        s = SchedulerService()
        jid = s.add("every 3600", "find python")
        assert s.cancel(jid) is True
        assert s.cancel("job-999") is False

    def test_executor_called(self):
        s = SchedulerService()
        called = []
        s.set_executor(lambda cmd: called.append(cmd))
        jid = s.add("every 1", "test cmd")
        # manually trigger _run
        s._run(jid)
        assert called == ["test cmd"]

    def test_snapshot_restore(self):
        s = SchedulerService()
        s.add("every 60", "find python")
        snap = s.snapshot()
        s2 = SchedulerService()
        s2.restore(snap)
        assert len(s2.list_jobs()) == 1

    def test_invalid_cron_defaults_to_60(self):
        s = SchedulerService()
        s.add("invalid", "test")
        job = s.list_jobs()[0]
        assert job["next_run"] <= time.time() + 61

    def test_start_stop(self):
        s = SchedulerService()
        s.start()
        assert s._thread is not None
        s.stop()

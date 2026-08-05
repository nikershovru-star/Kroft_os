"""Stage 38 - Scheduler persistence & execution history tests (6)."""
import json
import os
import tempfile
import time

import pytest

from services import SchedulerService


class TestSchedulerPersistence:
    def test_persistence_save_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sched.json")
            s = SchedulerService(persistence_path=path)
            jid = s.add("every 3600", "find python")
            assert os.path.exists(path)
            s2 = SchedulerService(persistence_path=path)
            jobs = s2.list_jobs()
            assert len(jobs) == 1
            assert jobs[0]["id"] == jid

    def test_restore_preserves_job_ids(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sched.json")
            s = SchedulerService(persistence_path=path)
            jid = s.add("every 60", "cmd")
            s2 = SchedulerService(persistence_path=path)
            assert jid in s2._jobs
            assert s2._jobs[jid].command == "cmd"

    def test_history_records_success_and_failure(self):
        s = SchedulerService()
        s.set_executor(lambda cmd: "ok")
        s.add("every 1", "good")
        s._run(list(s._jobs.keys())[0])
        assert s.history()[0]["success"] is True

        s2 = SchedulerService()
        s2.set_executor(lambda cmd: (_ for _ in ()).throw(RuntimeError("fail")))
        s2.add("every 1", "bad")
        s2._run(list(s2._jobs.keys())[0])
        assert s2.history()[0]["success"] is False
        assert "fail" in s2.history()[0]["output"]

    def test_history_filter_by_job_id(self):
        s = SchedulerService()
        s.set_executor(lambda cmd: "ok")
        j1 = s.add("every 1", "a")
        j2 = s.add("every 1", "b")
        s._run(j1)
        s._run(j2)
        assert len(s.history(job_id=j1)) == 1
        assert s.history(job_id=j1)[0]["command"] == "a"

    def test_log_file_append_json_lines(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "exec.log")
            s = SchedulerService(log_path=log)
            s.set_executor(lambda cmd: "done")
            j = s.add("every 1", "x")
            s._run(j)
            assert os.path.exists(log)
            with open(log, "r", encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 1
            assert lines[0]["command"] == "x"
            assert lines[0]["success"] is True

    def test_auto_save_on_add_cancel(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sched.json")
            s = SchedulerService(persistence_path=path)
            j = s.add("every 60", "task")
            assert os.path.exists(path)
            mtime = os.path.getmtime(path)
            time.sleep(0.01)
            s.cancel(j)
            assert os.path.getmtime(path) >= mtime

"""Tests: kernel/execution_tape.py."""

from __future__ import annotations

import tempfile

from kernel.execution_tape import ExecutionRecord, ExecutionTape


def _record(step_id="step-1", episode_id="ep-1", cycle_id="c-1") -> ExecutionRecord:
    return ExecutionRecord(
        step_id=step_id,
        episode_id=episode_id,
        cycle_id=cycle_id,
        fsm_state="planning",
        transition="plan->execute",
        goal="demo",
        action="search",
        result="ok",
        confidence=0.9,
        timestamp=1.0,
    )


def test_execution_tape_append_and_episode_filter():
    tape = ExecutionTape()
    tape.record(_record(step_id="s1", episode_id="ep-1"))
    tape.record(_record(step_id="s2", episode_id="ep-1"))
    tape.record(_record(step_id="s3", episode_id="ep-2"))
    assert len(tape) == 3
    assert len(tape.episode("ep-1")) == 2
    assert len(tape.episode("ep-2")) == 1
    assert tape.episode("missing") == []


def test_execution_tape_persist_and_load():
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/tape.jsonl"
        tape = ExecutionTape(path=path)
        tape.record(_record(step_id="s1", episode_id="ep-1"))
        tape.record(_record(step_id="s2", episode_id="ep-2"))
        loaded = ExecutionTape()
        loaded.load(path)
        assert len(loaded) == 2
        assert loaded.episode("ep-1")[0].step_id == "s1"
        assert loaded.episode("ep-2")[0].action == "search"


def test_execution_tape_replay_is_dict():
    tape = ExecutionTape()
    tape.record(_record())
    replayed = tape.replay("ep-1")
    assert isinstance(replayed, list)
    assert replayed[0]["fsm_state"] == "planning"

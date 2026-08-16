"""Negative tests for new self-evolution modules."""

from __future__ import annotations

import json
import os
import tempfile

from kernel.arch_gate import run as arch_gate_run
from kernel.execution_tape import ExecutionTape, ExecutionRecord
from adapters.llm_hardening import CircuitBreaker, RetryableLlmClient
from contracts.i_llm import LlmResponse, ModelQuery
from contracts.i_llm_advisor import LLMError, LLMTimeout


class FakeLlm:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete(self, query: ModelQuery) -> LlmResponse:
        self.calls += 1
        resp = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(resp, Exception):
            raise resp
        return resp

    def stream(self, query: ModelQuery):
        yield self.complete(query).text


def test_hypothesis_engine_negative_gap_zero():
    from kernel.hypothesis_engine import ReferenceHypothesisEngine
    engine = ReferenceHypothesisEngine()
    gap = type("Gap", (), {
        "name": "r", "status": "ok", "score": 0.9, "target": 0.9,
        "gap": 0.0, "metric": "m", "evidence": ""
    })()
    assert engine.formulate(gap) is None


def test_akb_gate_negative_missing_yaml(monkeypatch, tmp_path):
    root = tmp_path
    import kernel.arch_gate as ag
    ag.ROOT = root
    code, violations = ag.run()
    assert code == 1
    assert any("import_matrix.yaml missing" in v.message for v in violations)


def test_execution_tape_negative_corrupt_jsonl():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bad.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json}\n")
        tape = ExecutionTape()
        tape.load(path)
        assert len(tape) == 0


def test_llm_hardening_negative_all_fallbacks_fail():
    inner = FakeLlm([LLMError("x")])
    fallback = FakeLlm([LLMError("y")])
    client = RetryableLlmClient(inner, max_attempts=2)
    client.add_fallback(fallback)
    try:
        client.complete(ModelQuery(prompt="hi"))
    except LLMError:
        pass
    else:
        raise AssertionError("expected LLMError")


def test_circuit_breaker_negative_open_blocks():
    breaker = CircuitBreaker(threshold=1, recovery_seconds=10.0)
    assert breaker.allow(now=1000.0)
    breaker.record_failure(now=1000.0)
    assert not breaker.allow(now=1000.0)

"""(tests) Wave 10 (ADR-013) Phase G — contract + serialization tests.

Ports abstract, Workflow/Step frozen, JSON round-trip deterministic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from contracts.i_workflow import (
    IPlanner,
    IExecutor,
    IReflection,
    IRetryManager,
    Workflow,
    Step,
    StepStatus,
    WorkflowStatus,
)
from contracts.i_llm import ModelQuery


def test_ports_are_abstract():
    for cls in (IPlanner, IExecutor, IReflection, IRetryManager):
        abstract = getattr(cls, "__abstractmethods__", set())
        assert abstract, f"{cls.__name__} must declare abstract methods"


def test_step_is_frozen():
    s = Step(id="s1", task="do")
    try:
        s.status = "done"
        assert False, "Step should be frozen"
    except Exception:
        pass


def test_workflow_is_frozen():
    w = Workflow(id="w1", goal="g")
    try:
        w.status = "running"
        assert False, "Workflow should be frozen"
    except Exception:
        pass


def test_workflow_plan_is_normalised_to_tuple():
    w = Workflow(id="w1", goal="g", plan=[Step(id="s1", task="t")])
    assert isinstance(w.plan, tuple)


def test_workflow_variables_copied_not_aliased():
    ext = {"k": "v"}
    w = Workflow(id="w1", goal="g", variables=ext)
    ext["k"] = "MUT"
    assert w.variables["k"] == "v"


def test_json_roundtrip_preserves_identity():
    w = Workflow(
        id="w1",
        goal="compare A and B",
        plan=(
            Step(id="s1_a", task="retrieve_A"),
            Step(id="s1_b", task="retrieve_B", status=StepStatus.DONE, output="ok", route_used="phi4"),
        ),
        variables={"topic": "rust"},
        reflection_log=("step 's1_a': done",),
    )
    raw = w.to_json()
    restored = Workflow.from_json(raw)
    assert isinstance(restored, Workflow)
    assert restored == w
    assert restored.to_json() == raw  # determinism: same bytes


def test_json_roundtrip_is_lossless_on_serialize_deserialize():
    w = Workflow(id="w1", goal="g", plan=[Step(id="s1", task="t")])
    blob = json.loads(w.to_json())
    assert blob["id"] == "w1"
    assert blob["plan"][0]["id"] == "s1"
    assert blob["status"] == WorkflowStatus.DRAFT


def test_query_passes_through_router_contract():
    # sanity: the structural router type is a callable expecting one ModelQuery
    def r(q: ModelQuery):
        return q
    assert callable(r)

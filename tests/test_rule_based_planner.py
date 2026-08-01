"""(tests) Wave 10 (ADR-013) Phase G — RuleBasedPlanner keyword routing."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_policy import PolicyContext
from contracts.i_workflow import Step
from adapters.rule_based_planner import RuleBasedPlanner


def _plan(goal: str) -> list:
    pl = RuleBasedPlanner()
    return [s.task for s in pl.plan(goal, PolicyContext(query=None))]


def test_first_keyword_match_wins_overlap():
    # "compare and summarize": compare template is ordered first
    tasks = _plan("compare and summarize the two papers")
    assert tasks[0].startswith("retrieve_A")


def test_compare_template():
    tasks = _plan("Compare Rust and Go performance")
    assert tasks == [
        "retrieve_A: Compare Rust and Go performance",
        "retrieve_B: Compare Rust and Go performance",
        "compare: Compare Rust and Go performance",
        "validate: Compare Rust and Go performance",
    ]


def test_summarize_template():
    tasks = _plan("Summarize the quarterly report")
    assert tasks[0].startswith("extract_entities")
    assert "summarize" in tasks[1]


def test_explain_template():
    tasks = _plan("Explain why the build failed")
    assert "retrieve_context" in tasks[0]
    assert "fact_check" in tasks[-1]


def test_russian_keywords():
    tasks = _plan("Сравни два подхода к кэшированию")
    assert tasks[0].startswith("retrieve_A")


def test_unknown_goal_falls_to_analyze_execute_validate():
    tasks = _plan("make me a sandwich")
    assert tasks == [
        "analyze: make me a sandwich",
        "execute: make me a sandwich",
        "validate: make me a sandwich",
    ]


def test_plan_is_deterministic():
    a = [s.task for s in RuleBasedPlanner().plan("compare x vs y", PolicyContext(query=None))]
    b = [s.task for s in RuleBasedPlanner().plan("compare x vs y", PolicyContext(query=None))]
    assert a == b


def test_step_ids_are_unique_and_ordered():
    steps = RuleBasedPlanner().plan("summarize z", PolicyContext(query=None))
    ids = [s.id for s in steps]
    assert len(ids) == len(set(ids))
    assert ids == ["s1_extract_entities", "s2_summarize", "s3_validate"]


def test_template_for_introspection():
    pl = RuleBasedPlanner()
    assert pl.template_for("compare a vs b") == "compare"
    assert pl.template_for("do the thing") == "default"

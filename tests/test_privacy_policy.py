"""Wave 5.1 — PrivacyPolicy tests (ADR-009 §4.2)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from policies.privacy_policy import PrivacyPolicy, _has_pii


def _catalog():
    return [
        ModelInfo(id="gpt", provider="omniroute", reasoning=True, local=False,
                  context_window=128000, free=False, cost_per_1k=5.0),
        ModelInfo(id="qwen", provider="ollama", reasoning=False, local=True,
                  context_window=32000, free=True, cost_per_1k=0.0),
        ModelInfo(id="phi4", provider="ollama", reasoning=True, local=True,
                  context_window=16000, free=True, cost_per_1k=0.0),
    ]


def test_has_pii_email():
    assert _has_pii("Contact me at alice@example.com please") is True


def test_has_pii_phone():
    assert _has_pii("My number is 555-123-4567") is True


def test_has_pii_ssn():
    assert _has_pii("SSN 123-45-6789 for verification") is True


def test_has_pii_clean():
    assert _has_pii("What is the capital of France?") is False


def test_local_only_filters_to_local():
    p = PrivacyPolicy(local_only=True)
    ctx = PolicyContext(query=ModelQuery(prompt="hi"))
    d = p.evaluate(ctx, _catalog())
    assert d.allowed is True
    assert all(m.local for m in d.fallback_chain)
    assert d.selected_model.provider == "ollama"


def test_local_only_veto_when_no_local():
    p = PrivacyPolicy(local_only=True)
    ctx = PolicyContext(query=ModelQuery(prompt="hi"))
    # catalog with zero local models
    cloud_only = [m for m in _catalog() if not m.local]
    d = p.evaluate(ctx, cloud_only)
    assert d.allowed is False
    assert d.vetoed_by == "PrivacyPolicy"


def test_blocked_providers_removes_them():
    p = PrivacyPolicy(blocked_providers=["omniroute"])
    ctx = PolicyContext(query=ModelQuery(prompt="hi"))
    d = p.evaluate(ctx, _catalog())
    assert d.allowed is True
    assert all(m.provider != "omniroute" for m in d.fallback_chain)


def test_allowed_providers_restricts():
    p = PrivacyPolicy(allowed_providers=["ollama"])
    ctx = PolicyContext(query=ModelQuery(prompt="hi"))
    d = p.evaluate(ctx, _catalog())
    assert d.allowed is True
    assert all(m.provider == "ollama" for m in d.fallback_chain)


def test_no_cloud_reasoning_with_reasoning_query():
    p = PrivacyPolicy(no_cloud_reasoning=True)
    ctx = PolicyContext(query=ModelQuery(prompt="solve this", reasoning=True))
    d = p.evaluate(ctx, _catalog())
    assert d.allowed is True
    assert all(m.local for m in d.fallback_chain)
    # PrivacyPolicy is a pure filter: it keeps local models but does NOT rank by
    # reasoning capability (that is ProviderSelectionPolicy's job). Assert local.
    assert d.selected_model.local is True


def test_no_cloud_reasoning_without_reasoning_query_passes():
    p = PrivacyPolicy(no_cloud_reasoning=True)
    ctx = PolicyContext(query=ModelQuery(prompt="hi", reasoning=False))
    d = p.evaluate(ctx, _catalog())
    assert d.allowed is True
    # non-reasoning query → no_cloud_reasoning does NOT force local
    assert any(not m.local for m in d.fallback_chain)


def test_pii_in_prompt_forces_local():
    p = PrivacyPolicy(local_only=False)
    ctx = PolicyContext(query=ModelQuery(prompt="Email me at bob@corp.com"))
    d = p.evaluate(ctx, _catalog())
    assert d.allowed is True
    assert all(m.local for m in d.fallback_chain)


def test_pii_in_prompt_veto_when_no_local_available():
    p = PrivacyPolicy(local_only=False)
    ctx = PolicyContext(query=ModelQuery(prompt="SSN 123-45-6789"))
    cloud_only = [m for m in _catalog() if not m.local]
    d = p.evaluate(ctx, cloud_only)
    assert d.allowed is False
    assert d.vetoed_by == "PrivacyPolicy"


def test_priority_and_flags():
    p = PrivacyPolicy()
    assert p.priority == 20
    assert p.can_veto is True
    assert p.name == "PrivacyPolicy"

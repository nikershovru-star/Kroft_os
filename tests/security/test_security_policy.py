"""Wave 5.2 (ADR-009) — SecurityPolicy unit tests.

Covers: blocklist filtering, trust-tier filtering, empty-catalog passthrough,
require_audit_trail flag, priority/can_veto flags, and integration ordering
with the engine (Budget 10 -> Privacy 20 -> Security 30 -> ProviderSelection 100).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts.i_llm import ModelInfo, ModelQuery
from contracts.i_policy import PolicyContext
from policies.security_policy import SecurityPolicy, trust_tier
from policies.budget_policy import BudgetPolicy
from policies.privacy_policy import PrivacyPolicy
from policies.provider_selection_policy import ProviderSelectionPolicy
from services.policy_engine import PolicyEngine
from contracts.model_registry import ModelRegistry


def _mi(id, free=True, local=False):
    return ModelInfo(id=id, provider="x", reasoning=False, local=local, free=free, context_window=8000)


def _ctx():
    return PolicyContext(query=ModelQuery(prompt="hi"))


def test_blocked_models_removed():
    cat = [_mi("gpt", free=False, local=False), _mi("qwen", free=True, local=True)]
    sp = SecurityPolicy(min_trust_tier=1, blocked_models=["gpt"])
    d = sp.evaluate(_ctx(), cat)
    ids = [m.id for m in d.fallback_chain]
    assert "gpt" not in ids
    assert "qwen" in ids


def test_min_tier_5_keeps_only_local_free():
    cat = [
        _mi("gpt", free=False, local=False),   # tier 2
        _mi("qwen", free=True, local=True),     # tier 5
        _mi("phi4", free=True, local=True),     # tier 5
        _mi("cloud", free=True, local=False),   # tier 3
    ]
    sp = SecurityPolicy(min_trust_tier=5)
    d = sp.evaluate(_ctx(), cat)
    ids = [m.id for m in d.fallback_chain]
    assert ids == ["qwen", "phi4"]


def test_min_tier_1_passes_all():
    cat = [
        _mi("gpt", free=False, local=False),
        _mi("qwen", free=True, local=True),
        _mi("cloud", free=True, local=False),
    ]
    sp = SecurityPolicy(min_trust_tier=1)
    d = sp.evaluate(_ctx(), cat)
    assert len(d.fallback_chain) == 3


def test_empty_catalog_after_filter_is_valid():
    # can_veto=False -> empty result is allowed=True, not a veto.
    cat = [_mi("gpt", free=False, local=False)]  # tier 2
    sp = SecurityPolicy(min_trust_tier=5, blocked_models=["gpt"])
    d = sp.evaluate(_ctx(), cat)
    assert d.allowed is True
    assert d.fallback_chain == []
    assert sp.can_veto is False


def test_require_audit_trail_adds_warning():
    cat = [_mi("qwen", free=True, local=True)]
    sp = SecurityPolicy(min_trust_tier=1, require_audit_trail=True)
    d = sp.evaluate(_ctx(), cat)
    assert any("audit_trail REQUIRED" in a for a in d.audit_log)


def test_priority_and_flags():
    sp = SecurityPolicy()
    assert sp.priority == 30
    assert sp.can_veto is False
    # trust_tier heuristic (LAW 3: computed)
    assert trust_tier(_mi("qwen", free=True, local=True)) == 5
    assert trust_tier(_mi("cloud", free=True, local=False)) == 3
    assert trust_tier(_mi("gpt", free=False, local=False)) == 2


def test_integration_ordering_in_engine():
    reg = ModelRegistry()
    reg.register_model(_mi("gpt", free=False, local=False))   # tier 2
    reg.register_model(_mi("qwen", free=True, local=True))     # tier 5
    reg.register_model(_mi("phi4", free=True, local=True))     # tier 5
    reg.register_model(_mi("cloud", free=True, local=False))   # tier 3
    eng = PolicyEngine(reg)
    eng.register(BudgetPolicy())
    eng.register(PrivacyPolicy())               # priority 20
    eng.register(SecurityPolicy(min_trust_tier=5, blocked_models=["phi4"]))  # priority 30
    eng.register(ProviderSelectionPolicy(strategy="scored"))  # priority 100
    d = eng.decide(PolicyContext(query=ModelQuery(prompt="hi")))
    # security keeps only local+free (qwen, phi4) then blocklist drops phi4
    assert d.selected_model.id == "qwen"
    assert "SecurityPolicy" in d.constraints_applied

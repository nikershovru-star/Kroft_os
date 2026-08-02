"""Tenant isolation tests (TZ-MULTI-001 WP-08).

Covers: context provider thread-safety, default fallback, manager approval/
soft-delete, sandbox tenant-prefix, cross-tenant memory/authz isolation,
secret scoping, backward-compat (full suite unaffected). Negative tests prove
fail-closed (cross-tenant denied, create without approval denied).
"""
import os
import threading

import pytest

from contracts.tenant import ITenantManager, ITenantIsolator, TenantId
from kernel.tenant import (
    DefaultTenantContext,
    TenantContext,
    TenantContextProvider,
    TenantKnowledgeBoundary,
    TenantMemoryNamespace,
    TenantRAGFilter,
)
from kernel.security import AuthorizationEngine, FileSandbox
from kernel.security.capability_manager import CapabilityManager
from services.security import SecretManager
from services.tenant import (
    InMemoryTenantManager,
    TenantIsolator,
    TenantOnboardingWorkflow,
)


# ---- WP-02: context provider ----
def test_default_tenant_fallback():
    TenantContextProvider.clear()
    assert TenantContextProvider.get_current_tenant_id() == "default"
    assert isinstance(TenantContextProvider.get_current(), DefaultTenantContext)


def test_set_and_get_current():
    TenantContextProvider.set_current(TenantContext(tenant_id="acme", agent_id="a1"))
    assert TenantContextProvider.get_current_tenant_id() == "acme"
    TenantContextProvider.clear()
    assert TenantContextProvider.get_current_tenant_id() == "default"


def test_tenant_context_provider_thread_safety():
    TenantContextProvider.clear()
    results = {}

    def worker(tid):
        TenantContextProvider.set_current(TenantContext(tenant_id=tid, agent_id=tid))
        results[tid] = TenantContextProvider.get_current_tenant_id()

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == {f"t{i}": f"t{i}" for i in range(8)}


# ---- WP-01: TenantId ----
def test_tenant_id_validation():
    assert TenantId("acme").value == "acme"
    with pytest.raises(ValueError):
        TenantId("ACME")  # uppercase invalid
    with pytest.raises(ValueError):
        TenantId("bad id!")  # space + punctuation


# ---- WP-03: manager ----
def test_tenant_manager_create_requires_approval():
    m: ITenantManager = InMemoryTenantManager()  # no approval wired
    with pytest.raises(PermissionError):
        m.create("acme", "nikita")


def test_tenant_manager_soft_delete():
    m = InMemoryTenantManager()
    m._approval = _StubApproval()  # type: ignore[assignment]
    rec = m.create("acme", "nikita")
    assert m.exists("acme")
    assert m.delete("acme") is True
    assert not m.exists("acme")  # soft-deleted -> not visible
    assert m.get("acme") is None


def test_tenant_manager_list_excludes_deleted():
    m = InMemoryTenantManager()
    m._approval = _StubApproval()  # type: ignore[assignment]
    m.create("a", "nikita")
    m.create("b", "nikita")
    m.delete("a")
    ids = [r.tenant_id for r in m.list()]
    assert ids == ["b"]


class _StubApproval:
    """Minimal approval stub that auto-approves (for tests only)."""

    class _Req:
        def __init__(self, rid):
            self._id = rid
            self.status = "approved"

    def request(self, *a, **k):
        return self._Req("req-1")


# ---- WP-04: sandbox ----
def test_file_sandbox_tenant_prefix_allowed():
    sb = FileSandbox()
    sb.set_tenant("acme")
    p = sb.namespace_path("note.md")
    assert sb.is_allowed(p)


def test_file_sandbox_tenant_traversal_blocked():
    sb = FileSandbox()
    sb.set_tenant("acme")
    assert not sb.is_allowed("workspace/acme/../corp/x.md")


def test_file_sandbox_cross_tenant_blocked():
    sb = FileSandbox()
    sb.set_tenant("acme")
    assert not sb.is_allowed("workspace/corp/secret.md")


# ---- WP-05: memory isolation ----
def test_cross_tenant_memory_isolation():
    iso: ITenantIsolator = TenantIsolator()
    ns = TenantMemoryNamespace(iso)
    assert ns.scope_key("acme", "node_1") == "tenant:acme:node_1"
    assert ns.scope_key("acme", "node_1") != ns.scope_key("corp", "node_1")


def test_tenant_rag_filter_owns():
    iso = TenantIsolator()
    rf = TenantRAGFilter(iso)
    assert rf.owns("acme", "tenant:acme:doc") is True
    assert rf.owns("acme", "tenant:corp:doc") is False


def test_tenant_knowledge_boundary():
    iso = TenantIsolator()
    kb = TenantKnowledgeBoundary(iso)
    assert kb.can_read("acme", "acme") is True
    assert kb.can_read("acme", "corp") is False


# ---- WP-06: authz cross-tenant ----
def test_authorization_engine_denies_cross_tenant():
    eng = AuthorizationEngine(CapabilityManager(), isolator=TenantIsolator())
    d = eng.authorize_cross_tenant("acme", "corp")
    assert not d.allowed
    assert "denied" in d.reason


def test_authorization_engine_allows_same_tenant():
    eng = AuthorizationEngine(CapabilityManager(), isolator=TenantIsolator())
    assert eng.authorize_cross_tenant("acme", "acme").allowed


# ---- WP-07: onboarding ----
def test_tenant_onboarding_requires_approval():
    wf = TenantOnboardingWorkflow(None)
    r = wf.request_create("acme", "nikita")
    assert r.approved is False
    assert "K5" in r.message


# ---- R10: secret scoping ----
def test_secret_manager_tenant_prefix():
    sm = SecretManager({"acme_OPENAI_API_KEY": "sk-acme", "corp_OPENAI_API_KEY": "sk-corp"})
    assert sm.get_for("acme", "OPENAI_API_KEY") == "sk-acme"
    assert sm.get_for("corp", "OPENAI_API_KEY") == "sk-corp"


# ---- R9 / backward compat ----
def test_backward_compat_default_tenant_isolation():
    # default tenant still isolated from explicit tenants
    iso = TenantIsolator()
    assert iso.check_boundary("default", "acme") is False
    assert iso.check_boundary("default", "default") is True


# ---- additional coverage (target >=26 tests) ----
def test_isolator_namespace_path_format():
    iso = TenantIsolator()
    assert iso.namespace_path("acme", "x.md") == "workspace/acme/x.md"


def test_isolator_global_tenant_cross_allowed():
    iso = TenantIsolator(global_tenants=frozenset({"admin"}))
    assert iso.check_boundary("admin", "acme") is True
    assert iso.check_boundary("acme", "admin") is False


def test_tenant_context_agent_id():
    ctx = TenantContext(tenant_id="acme", agent_id="agent-7")
    assert ctx.agent_id == "agent-7"
    assert ctx.tenant().value == "acme"
    assert ctx.has_metadata("k") is False


def test_tenant_record_to_dict():
    from contracts.tenant import TenantRecord
    rec = TenantRecord(tenant_id="acme", created_at="t", created_by="nikita",
                       metadata={"plan": "pro"})
    d = rec.to_dict()
    assert d["tenant_id"] == "acme" and d["deleted"] is False
    assert d["metadata"]["plan"] == "pro"


def test_manager_set_metadata():
    m = InMemoryTenantManager()
    m._approval = _StubApproval()
    m.create("acme", "nikita")
    m.set_metadata("acme", "plan", "pro")
    assert m.get("acme").metadata["plan"] == "pro"


def test_jsonl_persistence_roundtrip(tmp_path):
    path = str(tmp_path / "tenants.jsonl")
    m = InMemoryTenantManager(approval=_StubApproval(), persistence_path=path)
    m.create("acme", "nikita")
    m2 = InMemoryTenantManager(persistence_path=path)
    assert m2.exists("acme")


def test_secret_manager_tenant_mask():
    sm = SecretManager({"acme_OPENAI_API_KEY": "sk-secretvalue123"})
    assert sm.mask(sm.get_for("acme", "OPENAI_API_KEY")) == "sk-s****e123"


def test_onboarding_complete_create_approved():
    m = InMemoryTenantManager()
    m._approval = _StubApproval()
    wf = TenantOnboardingWorkflow(m, approval=m._approval)
    r = wf.request_create("acme", "nikita")
    assert r.approved is True
    rec = wf.complete_create("acme", "nikita", approved=True)
    assert rec is not None and rec.tenant_id == "acme"


def test_scope_key_format():
    iso = TenantIsolator()
    assert iso.scope_key("acme", "memory:node1") == "tenant:acme:memory:node1"


def test_rag_filter_query_format():
    rf = TenantRAGFilter(TenantIsolator())
    assert rf.filter_query("acme", "find ADRs") == "[tenant:acme] find ADRs"

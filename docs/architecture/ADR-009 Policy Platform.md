---
tags: [kroft, adr, policy, architecture, wave5]
created: 2026-07-31
status: accepted
---

# ADR-009 — Policy Platform (Routing Governance Layer)

> **Status: ACCEPTED** (Wave 5 implemented 2026-07-31).
> Source spec provided by user (AI-архитектор Kimi, 2026-07-31). Supersedes the
> earlier `ADR-007 Policy Platform` design stub — that stub is now absorbed here.
> Связано: [[ADR-006 Model Platform]], [[ROADMAP]], [[ADR-007 Policy Platform]] (stub).

## Decision (summary)
Policy as Code: each policy is a class implementing `IPolicy` (`name` / `priority` /
`can_veto` / `evaluate`); `PolicyEngine` orchestrates without knowing rule semantics.

Pipeline: **Veto (can_veto, asc priority) → Catalog Filter → Ranking → Fallback chain
→ Execute+Retry**. `FallbackPolicy` is a runtime wrapper around `ILlm.complete()`.

## Implementation (commits)
- `682198c` — Phase A+B: `contracts/i_policy.py` (IPolicy/PolicyContext/PolicyDecision/CallRecord), `ModelInfo.cost_per_1k`, `policies/budget_policy.py` (BudgetPolicy, veto).
- `1164dac` — Phase C: `policies/provider_selection_policy.py` (replaces static `_select_model`).
- `62e801d` — Phase D: `services/policy_engine.py` (PolicyEngine + FallbackPolicy).
- `3f3db84` — Phase E+F+G: `tests/test_policy_engine.py`, `tests/test_policies_integration.py`, `adapters/router.py`, `model_registry.register_model` fix.

## 9. Чек-лист реализации (ADR-009 §11)
- [x] contracts/i_policy.py — IPolicy, PolicyContext, PolicyDecision, CallRecord
- [x] policies/budget_policy.py — daily/session/per_call limits, can_veto
- [x] policies/privacy_policy.py — local_only, provider whitelist/blacklist  *(Wave 5.1)*
- [x] policies/security_policy.py — trust tiers, blocked models  *(Wave 5.2, 3625dfd)*
- [x] policies/provider_selection_policy.py — greedy/scored ranking (v2 scorecard blend in Wave 7)
- [x] services/policy_engine.py — Pipeline (veto → filter → rank → fallback)
- [x] adapters/router.py — PolicyEngine + ILlm integration
- [x] tests/test_policy_engine.py — veto, ranking, fallback
- [x] tests/test_policies_integration.py — golden: Budget veto + ProviderSelection local
- [x] tests/test_privacy_policy.py — PII, veto, filtering (Wave 5.1)
- [x] contracts/__init__.py — ports registered
- [x] ADR-009 → accepted

## 10. Закрытие (Wave 5.2)
- **Wave 5.2 (SecurityPolicy) closed 2026-07-31** — коммит `3625dfd`.
- Все пункты чек-листа ADR-009 ✅. Policy Platform полностью реализован:
  BudgetPolicy (10, veto) → PrivacyPolicy (20, veto+filter) → SecurityPolicy (30, filter)
  → ProviderSelectionPolicy (100, rank; v2 scorecard blend из Wave 7).
- ADR-009 статус: accepted, без открытых пунктов.

# tests/fixtures_violations/violation_k6_adapters_policies.py
# Намеренное нарушение K6/V3: adapters импортирует policies.
from policies.budget_policy import estimate_cost  # K6 violation

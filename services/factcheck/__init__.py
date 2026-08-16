"""Fact-check services (Stage 4). K1: domain layer, contracts + stdlib only."""
from .self_consistency import (
    FactCheckResult,
    SelfConsistency,
    Verdict,
)

__all__ = ["FactCheckResult", "SelfConsistency", "Verdict"]

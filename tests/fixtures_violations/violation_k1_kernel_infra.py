# tests/fixtures_violations/violation_k1_kernel_infra.py
# Намеренное нарушение K1: kernel импортирует infrastructure.
from infrastructure import DependencyContainer  # K1 violation

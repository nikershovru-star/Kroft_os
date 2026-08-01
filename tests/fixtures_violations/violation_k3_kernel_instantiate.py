# tests/fixtures_violations/violation_k3_kernel_instantiate.py
# Намеренное нарушение K3: kernel инстанцирует DependencyContainer.
from infrastructure import DependencyContainer


def build():
    return DependencyContainer()  # K3 violation (wiring outside composition)

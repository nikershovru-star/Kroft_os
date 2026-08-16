"""Echo-pattern model routing + ensemble layer (ТЗ-ECHO, E1).

Composition over inheritance: RuleBasedRouter delegates execution to the existing
``IModelRouter`` (OmniRouter) and SimpleEnsembleOrchestrator fans out over a list of
``ILlm`` clients. Ports live in contracts/ (K1); this package holds the implementations.
"""

from __future__ import annotations

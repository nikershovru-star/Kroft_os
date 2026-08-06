"""Skill Distributor port — federation replication of signed SkillPackages (ТЗ-FED-REPL-01, ADR-094).

K1-compliant: stdlib + contracts only. K5: this is a NEW distribution-across-nodes seam. It does
NOT duplicate:
  - contracts/i_network_transport.py already has INetworkTransport (send_soft_layer / on_soft_layer,
    ТЗ-NW-01). We REUSE it to ship a SkillPackage as a wire-dict (no new transport channel).
  - services/distributed_runtime.py FederationSoftMemorySync (ТЗ-FSE-01) already shows the PATTERN:
    publish via send_soft_layer + subscribe via on_soft_layer + verify + trust-gate. We follow that
    exact shape (do NOT re-invent federation), but for SkillPackages, not SOFT-layer items.
  - contracts/i_marketplace.py already has SkillPackage + ISkillRepository (install = verify + trust
    gate + version supersede, ТЗ-MARKETPLACE-01). We REUSE SkillPackage and the receiving node's
    ISkillRepository.install — no second install path.
  - contracts/i_signature.py (ISignatureProvider) + contracts/i_identity.py (ITrustRegistry) are reused
    by ISkillRepository.install (signature verify + trust_score_of gating). No re-implementation.
The missing piece was cross-node propagation of a signed package -> ISkillDistributor is that seam.

Determinism (I-09): package serialization is stable; the receiver verifies the SAME signature the
sender produced (HMAC canonical_bytes). O1: a node NEVER installs a package before verifying its
signature AND gating on author trust — untrusted / tampered -> rejected, store untouched.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from contracts.i_marketplace import SkillPackage
from contracts.i_network_transport import INetworkTransport


class ISkillDistributor(ABC):
    """Port: replicate a signed SkillPackage across federation nodes (ТЗ-FED-REPL-01).

    Contract:
      - publish_remote(pkg, transport): serialize `pkg` and ship it via
        ``transport.send_soft_layer([pkg_dict], self_node_id)``. The receiving node's
        ``on_remote_package`` handler does verify + trust-gate + install.
      - on_remote_package(pkg_dict, trust_registry, threshold): rebuild the SkillPackage, verify
        its signature (via the injected ISkillRepository), gate on author trust, and install into the
        local store (version supersede). Returns the installed payload or None if rejected (O1).
        Called by the node's ``transport.on_soft_layer`` handler (wired in composition, Флаг C).
      - Deterministic (I-09); never mutates HARD/FSM (O1).
    """

    @abstractmethod
    def publish_remote(self, pkg: SkillPackage, transport: INetworkTransport) -> None:
        raise NotImplementedError

    @abstractmethod
    def on_remote_package(self, pkg_dict: Dict[str, Any],
                         trust_registry=None,
                         threshold: float = 0.5) -> Optional[Any]:
        raise NotImplementedError

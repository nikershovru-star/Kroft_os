"""ТЗ-MARKETPLACE-01 (ADR-093) — Marketplace K8 tests (Флаг 1b, separate).

Covers: package+sign+publish; install verifies signature (roundtrip on another store with the
same signer); untrusted author -> rejected (O1); tampered payload -> rejected (O1); version
supersede (old SUPERSEDED); determinism (I-09). K5: reuses ISignatureProvider/attach_signature/
check_signature, ITrustRegistry/ReferenceTrustRegistry, Procedure, PluginManifest, IPluginRegistry
— no signing/trust/plugin port duplicated.
"""

from __future__ import annotations

import copy

import pytest

from adapters.hmac_signer import HmacSigner
from contracts.i_identity import ITrustRegistry, TrustMeta
from contracts.i_marketplace import ISkillRepository, SkillPackage
from contracts.i_memory import Procedure
from contracts.plugin import PluginManifest
from kernel.identity import ReferenceTrustRegistry
from services.skill_marketplace import SkillPackager, SkillRepository


def _signer():
    return HmacSigner(b"kroft-shared-secret")


def _procedure(version=1, steps=("echo good",)):
    return Procedure(skill_id=f"cap.v{version}", name="cap", capability="cap",
                     steps=steps, version=version, confidence=0.9)


# 1) implements port
def test_repository_implements_port():
    assert isinstance(SkillRepository(_signer()), ISkillRepository)


# 2) package + sign + publish
def test_package_sign_publish():
    signer = _signer()
    repo = SkillRepository(signer)
    pkg = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    assert isinstance(pkg, SkillPackage)
    assert pkg.signature  # signed
    repo.publish(pkg)
    assert pkg in repo.list()


# 3) install verifies signature (roundtrip on another store, same signer)
def test_install_verifies_signature():
    signer = _signer()
    repo_a = SkillRepository(signer)
    pkg = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    repo_a.publish(pkg)
    # a SECOND store, same signer key, installs the published package
    repo_b = SkillRepository(signer)
    trust = ReferenceTrustRegistry()
    trust.record(TrustMeta(item_id="alice-cap", trust_score=0.9, version=1, author_id="alice"))
    installed = repo_b.install(pkg, trust_registry=trust, threshold=0.5)
    assert installed is not None
    assert installed.version == 1
    assert installed.name == "cap"


# 4) untrusted author -> rejected (O1)
def test_untrusted_author_rejected():
    signer = _signer()
    repo = SkillRepository(signer)
    pkg = SkillPackager.package(_procedure(), author="mallory", signer=signer, version=1)
    trust = ReferenceTrustRegistry()  # mallory never recorded -> trust 0.0 < threshold
    assert repo.install(pkg, trust_registry=trust, threshold=0.5) is None


# 5) tampered payload -> rejected (O1)
def test_tampered_payload_rejected():
    signer = _signer()
    repo = SkillRepository(signer)
    pkg = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    tampered = pkg.__class__(**{**pkg.__dict__, "payload": {**pkg.payload, "steps": ["echo hacked"]}})
    # signature no longer matches the body
    assert repo.verify(tampered) is False
    assert repo.install(tampered) is None


# 6) version supersede (old SUPERSEDED for traceability)
def test_version_supersede():
    signer = _signer()
    repo = SkillRepository(signer)
    v1 = SkillPackager.package(_procedure(version=1), author="alice", signer=signer, version=1)
    v2 = SkillPackager.package(_procedure(version=2, steps=("echo better",)),
                                author="alice", signer=signer, version=2)
    repo.publish(v1)
    repo.publish(v2)
    repo.install(v1)
    repo.install(v2)
    assert repo._installed["cap"].version == 2
    assert len(repo.superseded("cap")) == 1
    assert repo.superseded("cap")[0].version == 1


# 7) determinism (I-09): same input + signer -> identical signature
def test_determinism():
    signer = _signer()
    a = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    b = SkillPackager.package(_procedure(), author="alice", signer=signer, version=1)
    assert a.signature == b.signature
    assert a.id == b.id


# 8) plugin payload packs + installs
def test_plugin_package_install():
    signer = _signer()
    repo = SkillRepository(signer)
    manifest = PluginManifest(id="p1", name="search-plugin", capabilities=("search", "research"))
    pkg = SkillPackager.package(manifest, author="alice", signer=signer, version=1)
    assert pkg.payload_type == "plugin"
    trust = ReferenceTrustRegistry()
    trust.record(TrustMeta(item_id="alice-p1", trust_score=0.9, version=1, author_id="alice"))
    installed = repo.install(pkg, trust_registry=trust, threshold=0.5)
    assert isinstance(installed, PluginManifest)
    assert installed.id == "p1"

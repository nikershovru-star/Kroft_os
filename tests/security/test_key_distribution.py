"""ТЗ-KEYDIST-01 (ADR-098) — key distribution + rotation/revocation K8 tests (Флаг 1b, separate).

Closes the AUTHOR-KEYS-01 security debt: per-author keys were seeded in-process; real multi-node
nodes could not learn each other's keys, and there was no rotation/revocation. KEYDIST-01 adds a
bootstrap-anchored key record (HMAC-signed by a pre-shared bootstrap key): publish/fetch with
bootstrap signature verification, rotation (version bump supersedes), revocation (reject). K5: reuses
IAuthorKeyRegistry / ISignatureProvider / canonical_bytes / HmacSigner (CRYPTO-01) — no port duplicated.
SkillRepository.verify now prefers a valid, non-revoked distributed key, then the local registry,
then the shared signer (backward-compat).
"""

from __future__ import annotations

import copy

import pytest

from adapters.hmac_signer import HmacSigner
from composition.author_keys_factory import build_author_key_registry
from composition.key_distribution_service import KeyDistributionService
from contracts.i_key_distribution import IKeyDistribution, KeyRecord
from contracts.i_memory import Procedure
from services.skill_marketplace import SkillPackager, SkillRepository

BOOT = b"bootstrap-anchor"
ALICE = b"alice-secret"
ALICE_V2 = b"alice-secret-v2"
BOB = b"bob-secret"
SHARED = b"kroft-shared-secret"


def _skill():
    return Procedure(skill_id="cap.v1", name="cap", capability="cap",
                    steps=("echo good",), version=1, confidence=0.9)


def _pkg(author, key, version=1):
    return SkillPackager.package(_skill(), author=author, signer=HmacSigner(key), version=version)


# 1) publish/fetch with bootstrap signature
def test_publish_fetch_valid():
    kd = KeyDistributionService(BOOT)
    rec = kd.publish_key("alice", ALICE, version=1)
    assert isinstance(rec, KeyRecord)
    assert kd.fetch_key("alice") is not None
    assert kd.fetch_key("alice").key == ALICE


# 2) tampered key-record -> rejected (bootstrap signature mismatch)
def test_tampered_record_rejected():
    kd = KeyDistributionService(BOOT)
    rec = kd.publish_key("alice", ALICE, version=1)
    # forge: swap the key but keep the old signature (impersonation attempt)
    forged = copy.copy(rec)
    forged = forged.__class__(author=rec.author, key=BOB, version=rec.version,
                             signed_by=rec.signed_by, signature=rec.signature, revoked=rec.revoked)
    kd._records["alice"] = forged  # simulate a tampered store
    assert kd.fetch_key("alice") is None  # bootstrap sig fails -> reject


# 3) rotation: higher version supersedes; non-increasing rejected
def test_rotation_supersedes():
    kd = KeyDistributionService(BOOT)
    kd.publish_key("alice", ALICE, version=1)
    rec2 = kd.publish_key("alice", ALICE_V2, version=2)
    assert rec2.version == 2
    assert kd.fetch_key("alice").key == ALICE_V2  # superseded
    with pytest.raises(ValueError):
        kd.publish_key("alice", b"x", version=2)  # non-increasing -> rejected
    with pytest.raises(ValueError):
        kd.publish_key("alice", b"x", version=0)  # version < 1


# 4) revocation -> rejected
def test_revocation_rejected():
    kd = KeyDistributionService(BOOT)
    kd.publish_key("alice", ALICE, version=1)
    kd.revoke("alice")
    assert kd.is_revoked("alice")
    assert kd.fetch_key("alice") is None
    assert kd.get_signer("alice") is None
    # re-publish (new version) re-validates a previously-revoked author
    kd.publish_key("alice", ALICE, version=2)
    assert not kd.is_revoked("alice")
    assert kd.fetch_key("alice") is not None


# 5) SkillRepository.verify prefers valid distributed key; revoked -> reject
def test_repo_verify_via_distribution():
    kd = KeyDistributionService(BOOT)
    kd.publish_key("alice", ALICE_V2, version=1)
    repo = SkillRepository(signer=HmacSigner(SHARED), key_distribution=kd)
    pkg = _pkg("alice", ALICE_V2)
    assert repo.verify(pkg) is True
    # revoke -> even the correct key is rejected
    kd.revoke("alice")
    assert repo.verify(_pkg("alice", ALICE_V2)) is False


# 6) backward-compat: local registry without distribution still works
def test_backward_compat_local_registry():
    reg = build_author_key_registry({"alice": ALICE})
    repo = SkillRepository(signer=HmacSigner(SHARED), author_key_registry=reg)
    assert repo.verify(_pkg("alice", ALICE)) is True
    # unregistered author signed with shared -> fallback shared (legacy)
    repo_shared = SkillRepository(signer=HmacSigner(SHARED))
    assert repo_shared.verify(_pkg("mallory", SHARED)) is True


# 7) determinism (I-09): same inputs -> identical bootstrap signature + record
def test_determinism():
    kd1 = KeyDistributionService(BOOT)
    kd2 = KeyDistributionService(BOOT)
    r1 = kd1.publish_key("alice", ALICE, version=1)
    r2 = kd2.publish_key("alice", ALICE, version=1)
    assert r1.signature == r2.signature
    assert r1 == r2


# 8) IKeyDistribution contract
def test_port_contract():
    kd: IKeyDistribution = KeyDistributionService(BOOT)
    assert kd.publish_key("alice", ALICE, 1) is not None
    assert kd.get_signer("alice") is not None

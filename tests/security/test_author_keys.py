"""ТЗ-AUTHOR-KEYS-01 (ADR-096) — per-author HMAC keys K8 tests (Флаг 1b, separate).

Closes Flag 3 (MARKETPLACE/FED-REPL/CAPSTONE): a package is now authenticated by the AUTHOR'S OWN
key, not a shared one. K5: reuses ISignatureProvider / HmacSigner (CRYPTO-01), ISkillRepository /
SkillPackager / SkillRepository (MARKETPLACE-01) — no signing/trust port duplicated. IAuthorKeyRegistry
is the only new seam. Backward-compat: an unregistered author falls back to the shared signer.
"""

from __future__ import annotations

import copy

import pytest

from adapters.hmac_signer import HmacSigner
from composition.author_keys_factory import AuthorKeyRegistry, build_author_key_registry
from contracts.i_author_keys import AuthorKey, IAuthorKeyRegistry
from contracts.i_memory import Procedure
from services.skill_marketplace import SkillPackager, SkillRepository

ALICE_KEY = b"alice-secret"
BOB_KEY = b"bob-secret"
SHARED = b"kroft-shared-secret"


def _skill():
    return Procedure(skill_id="cap.v1", name="cap", capability="cap",
                    steps=("echo good",), version=1, confidence=0.9)


def _pkg(author, key, version=1):
    return SkillPackager.package(_skill(), author=author, signer=HmacSigner(key), version=version)


# 1) sign with author's own key + verify via registry
def test_sign_with_author_key_and_verify():
    reg = build_author_key_registry({"alice": ALICE_KEY})
    repo = SkillRepository(signer=HmacSigner(SHARED), author_key_registry=reg)
    pkg = _pkg("alice", ALICE_KEY)
    assert repo.verify(pkg) is True


# 2) forged: wrong (bob's) registered key -> rejected
def test_wrong_registered_key_rejected():
    reg_bob = build_author_key_registry({"alice": BOB_KEY})  # alice bound to bob's key
    repo = SkillRepository(signer=HmacSigner(SHARED), author_key_registry=reg_bob)
    pkg = _pkg("alice", ALICE_KEY)  # genuinely signed by alice's real key
    assert repo.verify(pkg) is False  # registry expects bob's key -> mismatch


# 3) unregistered author -> fallback to shared key (backward-compat)
def test_unregistered_author_falls_back_to_shared():
    # alice NOT in registry; signed with the shared key -> legacy verification path
    repo_shared = SkillRepository(signer=HmacSigner(SHARED))
    pkg = _pkg("mallory", SHARED)  # unregistered author, shared key
    assert repo_shared.verify(pkg) is True


# 4) author-bound: alice's package verified by alice-key registry, NOT by shared-only
def test_author_bound_to_own_key():
    reg = build_author_key_registry({"alice": ALICE_KEY})
    repo_reg = SkillRepository(signer=HmacSigner(SHARED), author_key_registry=reg)
    repo_shared_only = SkillRepository(signer=HmacSigner(SHARED))  # alice unregistered here
    pkg = _pkg("alice", ALICE_KEY)
    assert repo_reg.verify(pkg) is True          # registry authenticates alice's key
    assert repo_shared_only.verify(pkg) is False  # fallback expects shared key -> mismatch


# 5) backward-compat: shared key, no registry at all
def test_backward_compat_shared_key_no_registry():
    repo = SkillRepository(signer=HmacSigner(SHARED))
    pkg = _pkg("alice", SHARED)  # signed with shared key, no registry
    assert repo.verify(pkg) is True


# 6) determinism (I-09)
def test_determinism():
    a = _pkg("alice", ALICE_KEY)
    b = _pkg("alice", ALICE_KEY)
    assert a.signature == b.signature


# 7) IAuthorKeyRegistry contract + AuthorKey VO
def test_registry_contract():
    reg: IAuthorKeyRegistry = build_author_key_registry()
    reg.register_key("alice", ALICE_KEY)
    assert reg.has("alice")
    assert reg.get_key("alice") == ALICE_KEY
    assert isinstance(reg.get_signer("alice"), HmacSigner)
    assert reg.get_signer("bob") is None
    ak = AuthorKey(author="alice", key=ALICE_KEY)
    assert ak.author == "alice" and ak.key == ALICE_KEY

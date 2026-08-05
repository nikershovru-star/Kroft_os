"""JSON persistence for kernel evolution state (ТЗ-LIVE-01, ADR-087) — K1-compliant.

Stdlib-only (json + dataclasses). Serializes the SOFT evolution state so a kernel can
resume across restarts: episodes (raw experience), semantic facts (consolidated),
normative/soft policies (self-evolution output), procedural skills (Procedure VOs), and
a local trust map.

Design:
- Pure serialization: this module turns cognitive VOs <-> plain dicts <-> JSON. It does
  NOT own a live store and does NOT import services/ (K3/K6: kernel may only import
  kernel + contracts + stdlib). The caller (run_evolution.py, a root script) extracts
  state from the kernel and replays it back on restart.
- O1: save/load is a faithful round-trip; it never deprecates/mutates HARD. The kernel
  only commits SOFT layers via memory_evolution, so persisted normative entries are SOFT.
- I-09: json.dump uses sort_keys + deterministic field order; load reconstructs identical
  VOs (dataclass __eq__), so the same file -> the same state.

VO shapes (frozen dataclasses) are serialized explicitly (not dataclasses.asdict) because
ConfidenceScore/Provenance/CausalMark carry nested enums + a Lamport clock that need
name-based (de)serialization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from contracts.cognitive_domain import (
    AggregationRule,
    CalibrationType,
    CausalMark,
    ConfidenceScore,
    Episode,
    Policy,
    PolicyLifecycle,
    Provenance,
    ProvenanceType,
    SemanticFact,
)
from contracts.i_memory import Procedure


# --------------------------------------------------------------------------
# VO <-> dict helpers (explicit, enum/clock aware)
# --------------------------------------------------------------------------
def _conf_to_dict(c: ConfidenceScore) -> dict:
    return {
        "value": c.value,
        "provenance": c.provenance.name,
        "calibration": c.calibration.name,
        "aggregation_rule": c.aggregation_rule.name if c.aggregation_rule is not None else None,
    }


def _conf_from_dict(d: dict) -> ConfidenceScore:
    return ConfidenceScore(
        value=float(d["value"]),
        provenance=ProvenanceType[d["provenance"]],
        calibration=CalibrationType[d["calibration"]],
        aggregation_rule=AggregationRule[d["aggregation_rule"]] if d.get("aggregation_rule") else None,
    )


def _prov_to_dict(p: Provenance) -> dict:
    return {"source": p.source, "actor": p.actor, "timestamp": p.timestamp}


def _prov_from_dict(d: dict) -> Provenance:
    return Provenance(source=d["source"], actor=d["actor"], timestamp=d.get("timestamp", ""))


def _episode_to_dict(e: Episode) -> dict:
    return {
        "id": e.id,
        "summary": e.summary,
        "confidence": _conf_to_dict(e.confidence),
        "provenance": _prov_to_dict(e.provenance),
    }


def _episode_from_dict(d: dict) -> Episode:
    return Episode(
        id=d["id"], summary=d["summary"],
        confidence=_conf_from_dict(d["confidence"]),
        provenance=_prov_from_dict(d["provenance"]),
    )


def _semantic_to_dict(f: SemanticFact) -> dict:
    return {
        "id": f.id,
        "content": f.content,
        "confidence": _conf_to_dict(f.confidence),
        "causal": f.causal.to_dict() if f.causal is not None else None,
        "source_episodes": list(f.source_episodes),
    }


def _semantic_from_dict(d: dict) -> SemanticFact:
    return SemanticFact(
        id=d["id"], content=d["content"],
        confidence=_conf_from_dict(d["confidence"]),
        causal=CausalMark.from_dict(d.get("causal")),
        source_episodes=tuple(d.get("source_episodes", [])),
    )


def _policy_to_dict(p: Policy) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "layer": p.layer,
        "body": p.body,
        "confidence": _conf_to_dict(p.confidence),
        "provenance": _prov_to_dict(p.provenance),
        "lifecycle": p.lifecycle.name if p.lifecycle is not None else None,
    }


def _policy_from_dict(d: dict) -> Policy:
    return Policy(
        id=d["id"], name=d["name"], layer=d["layer"], body=d["body"],
        confidence=_conf_from_dict(d["confidence"]),
        provenance=_prov_from_dict(d["provenance"]),
        lifecycle=PolicyLifecycle[d["lifecycle"]] if d.get("lifecycle") else None,
    )


def _procedure_to_dict(s: Procedure) -> dict:
    return {
        "skill_id": s.skill_id,
        "name": s.name,
        "capability": s.capability,
        "steps": list(s.steps),
        "preconditions": list(s.preconditions),
        "confidence": s.confidence,
        "provenance": s.provenance,
        "causal": s.causal,
    }


def _procedure_from_dict(d: dict) -> Procedure:
    return Procedure(
        skill_id=d["skill_id"], name=d["name"], capability=d["capability"],
        steps=tuple(d.get("steps", [])), preconditions=tuple(d.get("preconditions", [])),
        confidence=float(d.get("confidence", 0.0)),
        provenance=d.get("provenance", ""), causal=d.get("causal"),
    )


@dataclass(frozen=True)
class KernelState:
    """The persistable evolution state of a single node (ТЗ-LIVE-01).

    Holds plain VO lists (episodes/semantic/normative from the layered memory, plus skills
    from the procedural store and a local trust map). Serialized verbatim by JsonMemoryStore.
    """

    episodes: List[Episode] = field(default_factory=list)
    semantic: List[SemanticFact] = field(default_factory=list)
    normative: List[Policy] = field(default_factory=list)
    skills: List[Procedure] = field(default_factory=list)
    trust: dict = field(default_factory=dict)  # author_id -> running trust (float)

    def to_dict(self) -> dict:
        return {
            "episodes": [_episode_to_dict(e) for e in self.episodes],
            "semantic": [_semantic_to_dict(f) for f in self.semantic],
            "normative": [_policy_to_dict(p) for p in self.normative],
            "skills": [_procedure_to_dict(s) for s in self.skills],
            "trust": dict(self.trust),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KernelState":
        return cls(
            episodes=[_episode_from_dict(e) for e in d.get("episodes", [])],
            semantic=[_semantic_from_dict(f) for f in d.get("semantic", [])],
            normative=[_policy_from_dict(p) for p in d.get("normative", [])],
            skills=[_procedure_from_dict(s) for s in d.get("skills", [])],
            trust=dict(d.get("trust", {})),
        )


class JsonMemoryStore:
    """Deterministic JSON save/load of KernelState (stdlib json only).

    save(state, path) writes a sorted-key JSON file; load(path) reconstructs an identical
    KernelState. Round-trip is byte-stable for identical state (I-09). O1-safe: load never
    mutates HARD — it restores whatever was persisted (the kernel only commits SOFT layers,
    so persisted normative entries are SOFT and immutable-by-experience anyway).
    """

    def save(self, state: KernelState, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, ensure_ascii=False, indent=2, sort_keys=True)

    def load(self, path: str) -> KernelState:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return KernelState.from_dict(data)

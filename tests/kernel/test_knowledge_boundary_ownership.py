"""ADR-028 Stage 4 — Knowledge Boundary ownership axis (I/we vs external).

Proof-over-existence: a fragment below the trust threshold is REJECTED (never
silently enters the graph); a local node reports LOCAL origin; an unknown
external node reports INGESTED. Honest merging prerequisite.
"""

from contracts.i_self_evolution_cycle import GraphFragment, KnowledgeOrigin
from kernel.self_evolution_cycle import ReferenceKnowledgeBoundary


def test_low_trust_fragment_rejected():
    boundary = ReferenceKnowledgeBoundary()
    frag = GraphFragment(author_id="nodeX", node_ids=("n1",), trust_score=0.2)
    # 0.2 < default 0.5 threshold -> rejected
    assert boundary.can_accept(frag) is False
    assert boundary.can_accept(frag, trust_threshold=0.1) is True


def test_sufficient_trust_fragment_accepted():
    boundary = ReferenceKnowledgeBoundary()
    frag = GraphFragment(author_id="nodeY", node_ids=("n1",), trust_score=0.9)
    assert boundary.can_accept(frag) is True


def test_local_node_reports_local_origin():
    # minimal fake graph (IGraphBuilder shape, only get_graph used here)
    class _G:
        def get_graph(self):
            return {"nodes": [{"id": "local-1"}]}
    boundary = ReferenceKnowledgeBoundary(graph=_G())
    assert boundary.origin_of("local-1") == KnowledgeOrigin.LOCAL
    # unknown id with no trust registry -> INGESTED (external default)
    assert boundary.origin_of("ghost") == KnowledgeOrigin.INGESTED


def test_origin_federated_when_trust_known_but_not_local():
    class _NoGraph:
        def get_graph(self):
            return {"nodes": []}
    class _Trust:
        def current_trust(self, author_id):
            return 0.8 if author_id == "fed-node" else 0.0
    boundary = ReferenceKnowledgeBoundary(graph=_NoGraph(), trust_registry=_Trust())
    # node id == author id "fed-node" is known to trust but not in local graph
    assert boundary.origin_of("fed-node") == KnowledgeOrigin.FEDERATED

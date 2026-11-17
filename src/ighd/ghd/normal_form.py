"""Normal-form checker (stage S8; paper §2.3, D10; precondition of Def 5.1).

Replay definition used here (the one Algorithm 3 relies on): start at the root with H_root = E(H).
At node n handling the edge set H_n, let C_1..C_l be the [B_n]-components of H_n. The GHD is in
normal form iff, at every node, there is a bijection between C_1..C_l and the children of n such
that child u gets the component c with (V(c) \\ B_n) & B_u non-empty (Alg 3 line 16), every edge of c
is contained in some bag of T_u, and the same holds recursively with H_u = c.

Every output of the static decomposer satisfies this (MATHEMATICAL_INVARIANTS §2.7, Lemma F).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.types import EdgeSet, NodeId, VertexSet
from ighd.ghd.tree import GHD
from ighd.hypergraph.core import Hypergraph
from ighd.static.separation import components


@dataclass(frozen=True)
class NFReport:
    """``ok`` plus, on success, the edge set handled at every node; on failure, where and why."""

    ok: bool
    handled: Mapping[NodeId, EdgeSet] = field(default_factory=dict)
    failed_node: NodeId | None = None
    reason: str = ""


def _names(edges: EdgeSet) -> str:
    return "{" + ",".join(sorted(edges)) + "}"


def _perfect_matching(children: tuple[NodeId, ...], comps: list[EdgeSet],
                      allowed: dict[NodeId, list[int]]) -> dict[NodeId, int] | None:
    """A perfect matching child -> component index using only ``allowed`` pairs, or None.

    Augmenting paths (Kuhn), children in order and components in components() order, so the
    result is deterministic. For a valid GHD the admissible pairs already form a matching
    (a vertex of V(c) \\ B_n in two child subtrees would be disconnected), so the choice is moot.
    """
    owner: dict[int, NodeId] = {}

    def augment(u: NodeId, seen: set[int]) -> bool:
        for ci in allowed[u]:
            if ci in seen:
                continue
            seen.add(ci)
            if ci not in owner or augment(owner[ci], seen):
                owner[ci] = u
                return True
        return False

    for u in children:
        if not augment(u, set()):
            return None
    if len(owner) != len(comps):
        return None
    return {u: ci for ci, u in owner.items()}


def check_normal_form(h: Hypergraph, ghd: GHD, semantics: Semantics = PAPER_DEFAULT) -> NFReport:
    """Check the replay normal form described in the module docstring.

    The replay is top-down from the current root (Alg 3's traversal). At node n with edge set
    H_n: (1) |children(n)| must equal the number of [B_n]-components of H_n; (2) a child u and a
    component c are *admissible* iff (V(c) \\ B_n) & B_u != {} (Alg 3 line 16) and every edge of c
    lies inside some bag of T_u; (3) the admissible pairs must contain a bijection. The first
    failing node (in preorder) is reported. The GHD need not be valid for the check to run.
    An empty GHD is in normal form iff ``h`` has no edges.
    """
    if len(ghd) == 0:
        if h.edge_names:
            return NFReport(False, {}, None,
                            f"empty GHD, but the hypergraph has edges {_names(h.edge_names)}")
        return NFReport(True, {}, None, "")

    # bags of every subtree, bottom-up, to decide "every edge of c lies in some bag of T_u"
    subtree_bags: dict[NodeId, list[VertexSet]] = {}
    for x in ghd.postorder():
        bags = [ghd.node(x).bag]
        for c in ghd.children(x):
            bags.extend(subtree_bags[c])
        subtree_bags[x] = bags

    def covered_in(u: NodeId, comp: EdgeSet) -> bool:
        return all(any(h.edge(e) <= b for b in subtree_bags[u]) for e in comp)

    handled: dict[NodeId, EdgeSet] = {}
    stack: list[tuple[NodeId, EdgeSet]] = [(ghd.root, h.edge_names)]
    while stack:
        n, h_n = stack.pop()
        handled[n] = h_n
        bag = ghd.node(n).bag
        comps = components(h, h_n, bag, semantics)
        kids = ghd.children(n)
        if len(kids) != len(comps):
            return NFReport(False, {}, n,
                            f"node {n}: {len(kids)} children but {len(comps)} [B_n]-components "
                            f"{[_names(c) for c in comps]} of the handled edges {_names(h_n)}")
        outside = [h.covered_vertices(c) - bag for c in comps]
        allowed: dict[NodeId, list[int]] = {}
        for u in kids:
            b_u = ghd.node(u).bag
            allowed[u] = [i for i, c in enumerate(comps) if outside[i] & b_u and covered_in(u, c)]
        matching = _perfect_matching(kids, comps, allowed)
        if matching is None:
            detail = "; ".join(
                f"child {u} admits {[_names(comps[i]) for i in allowed[u]]}" for u in kids)
            return NFReport(False, {}, n,
                            f"node {n}: no bijection between children and [B_n]-components "
                            f"(line-16 rule plus coverage in the child subtree): {detail}")
        for u in reversed(kids):
            stack.append((u, comps[matching[u]]))
    return NFReport(True, handled, None, "")

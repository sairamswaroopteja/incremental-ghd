"""delta(H)*: the part of delta(H) to re-decompose (stage S10; paper §4.1, D19, A11).

Reading: V* = delta(B(T*)) u V_new, and the edges are the non-empty restrictions e & V* for
e in E(delta(H)), keyed by edge name. Condition (ii) of Def 4.1 implies that every edge containing
a new vertex lies entirely inside V*; this is asserted, not assumed (invariant I8).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ighd.common.types import EdgeName, NodeId, VertexSet
from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult


@dataclass(frozen=True)
class RedecompositionTarget:
    vertices: VertexSet
    """V*."""
    edges: Mapping[EdgeName, VertexSet]
    """{name: e & V*} for edges of delta(H) meeting V*."""
    full_edges: frozenset[EdgeName]
    """Names of edges of delta(H) lying entirely inside V* (the rest are restricted)."""


def _invariant(cond: bool, msg: str) -> None:
    """Raise AssertionError (also under ``python -O``) when a proved invariant fails."""
    if not cond:
        raise AssertionError(msg)


def redecomposition_target(change: ModificationResult, ghd: GHD,
                           t_star: Iterable[NodeId]) -> RedecompositionTarget:
    """Compute delta(H)* for a delta-mutable subtree ``t_star`` of ``ghd`` (paper §4.1, D19, A11).

    * delta(Y) := Y & V(delta(H)) (vertices removed by delta are dropped);
    * V* := delta(B(T*)) u V_new with V_new = ``change.new_vertices``;
    * edges: {name: e & V*} for every edge e of delta(H) with e & V* non-empty, keyed by its
      delta(H) name (so a cover of a D* built on these edges is read as a cover in delta(H):
      B <= e & V* <= e);
    * full_edges: the names of edges e of delta(H) with e <= V*.

    Every vertex of delta(H) lies in some edge, so V(Hypergraph(edges)) = V*.

    Invariant I8 (Def 4.1(ii) => D19): every edge of delta(H) containing a new vertex lies
    inside V*. Proof: an old vertex of such an edge is adjacent to a new vertex, so by (ii) it is
    not in B(T \\ T*); as old vertices all lie in B(T), it is in B(T*). The check raises
    AssertionError naming the edge; it can only fire if ``t_star`` is not delta-mutable.

    ``t_star`` may be empty (A12): then V* = V_new.
    """
    s = frozenset(t_star)
    new_h = change.new
    v_new = frozenset(change.new_vertices)
    v_star: VertexSet = (ghd.bag_union(s) & new_h.vertices) | v_new

    edges: dict[EdgeName, VertexSet] = {}
    full: set[EdgeName] = set()
    for name, vs in new_h.edges.items():
        r = vs & v_star
        if r:
            edges[name] = r
            if r == vs:
                full.add(name)
        if vs & v_new:
            _invariant(
                vs <= v_star,
                f"invariant I8 violated: edge {name!r} = {sorted(vs)} of delta(H) contains new "
                f"vertices {sorted(vs & v_new)} but has vertices {sorted(vs - v_star)} outside "
                f"V* = {sorted(v_star)}; T* = {sorted(s)} is not delta-mutable (Def 4.1(ii))")
    return RedecompositionTarget(vertices=v_star, edges=edges, full_edges=frozenset(full))

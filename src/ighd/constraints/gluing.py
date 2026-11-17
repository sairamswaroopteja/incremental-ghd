"""Theorem 4.5 gluing (stage S10).

Start from D* (a GHD of delta(H)*). For each constraint C_i pick a node u_i* of D* with
C_i <= B_{u_i*} (the smallest id, for determinism) and attach the outer tree T_i, re-rooted at u_i,
below u_i* by one tree edge. Covers are left untouched (proof part (W)). Raises InvalidGHDError if
some constraint is not satisfied by D*: gluing is only claimed under Theorem 4.5's hypothesis.
"""

from __future__ import annotations

from collections.abc import Sequence

from ighd.common.errors import InvalidGHDError
from ighd.constraints.constraints import BagConstraint
from ighd.ghd.tree import GHD


def glue(d_star: GHD, old: GHD, constraints: Sequence[BagConstraint]) -> GHD:
    """Return D* with every outer tree of ``old`` re-attached (a new GHD object).

    Theorem 4.5 construction: for each C_i, u_i* is the node of D* (an id of ``d_star``; outer
    nodes attached earlier are never chosen) with the smallest id and C_i <= B_{u_i*}; the outer tree
    ``old.extract(outer_tree, root=outer_node)`` is hung below u_i* by one tree edge (GHD.attach;
    ids of the outer tree may be remapped on collision, labels are kept). Bags and covers of both
    D* and the outer trees are copied unchanged (Lemma 4.2 reuse, proof part (W): width <= k).
    Neither argument is modified.

    Connectedness (proof part (C)): a vertex v in B(T_i) and in D* is an old vertex in B(T*), so
    by connectedness of the old tree v in B_{u_i}, hence v in C_i <= B_{u_i*}; the new tree edge
    u_i*-u_i joins its occurrences.

    Empty D* (V* = {}, e.g. A12 with no new vertex, or delta deleting all of B(T*)):
      * no constraints: the empty GHD;
      * every constraint empty: the outer trees are pairwise vertex-disjoint (a shared vertex would
        lie in C_i & C_j), so they are joined arbitrarily: the first outer tree (re-rooted at its
        outer_node) is the base and the others hang below its root. With the single T* = {}
        pseudo-constraint this is a copy of the old tree rooted at its old root;
      * otherwise InvalidGHDError (an empty D* satisfies no non-empty constraint).

    Raises InvalidGHDError naming the first constraint that no bag of D* contains (Theorem 4.5's
    hypothesis fails), or on a label clash between D* and an outer tree.
    """
    if len(d_star) == 0:
        if not constraints:
            return GHD()
        nonempty = [c for c in constraints if c.vertices]
        if nonempty:
            c = nonempty[0]
            raise InvalidGHDError(
                f"glue: D* is empty but constraint C = {sorted(c.vertices)} of outer node "
                f"{c.outer_node} is non-empty (Theorem 4.5's hypothesis fails)")
        first, *rest = constraints
        out = old.extract(first.outer_tree, root=first.outer_node)
        base = out.root
        for c in rest:
            out.attach(base, old.extract(c.outer_tree, root=c.outer_node), c.outer_node)
        return out

    out = d_star.copy()
    d_nodes = [(nid, d_star.node(nid).bag) for nid in d_star.node_ids()]
    for c in constraints:
        target = next((nid for nid, bag in d_nodes if c.vertices <= bag), None)
        if target is None:
            raise InvalidGHDError(
                f"glue: bag constraint C = {sorted(c.vertices)} (outer node {c.outer_node}, inner "
                f"neighbour {c.inner_neighbor}) is contained in no bag of D*; Theorem 4.5's "
                "hypothesis fails")
        out.attach(target, old.extract(c.outer_tree, root=c.outer_node), c.outer_node)
    return out

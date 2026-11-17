"""T*-induced bag constraints (stage S10; paper §4.1, D20).

For every node u_i outside T* with a tree neighbour in T*: C_i = B_{u_i} & B(T*). Each tree of
the forest T \\ T* contains exactly one such node, so constraints correspond one-to-one to the
outer subtrees (guide §6.6). This is asserted (invariant I5).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ighd.common.errors import InvalidGHDError
from ighd.common.types import NodeId, VertexSet
from ighd.ghd.tree import GHD


@dataclass(frozen=True)
class BagConstraint:
    outer_node: NodeId
    """u_i: the node of the outer tree adjacent to T*."""
    inner_neighbor: NodeId
    """Its neighbour in T* (in the old tree)."""
    outer_tree: frozenset[NodeId]
    """Node set of the tree of T \\ T* containing u_i."""
    vertices: VertexSet
    """C_i = B_{u_i} & B(T*)."""


def _invariant(cond: bool, msg: str) -> None:
    """Raise AssertionError (also under ``python -O``) when a proved invariant fails."""
    if not cond:
        raise AssertionError(msg)


def bag_constraints(ghd: GHD, t_star: Iterable[NodeId]) -> list[BagConstraint]:
    """One constraint per outer tree, sorted by outer_node (paper §4.1, D20; Theorem 4.5).

    For each tree T_i of the forest T \\ T* (``ghd.components_without``), u_i is the unique node of
    T_i with a tree neighbour in T*, and C_i = B_{u_i} & B(T*).

    Invariant I5: T_i meets T* by exactly one tree edge. Proof: T_i and T* are connected and
    disjoint, so two tree edges between them would close a cycle; at least one exists because T
    is connected and T* is non-empty. Checked at runtime (AssertionError).

    Special cases:
      * T* = all of T: no outer tree, returns [].
      * T* = {} (A12, ledger L-A12: delta is invisible from every bag): returns ONE
        pseudo-constraint with outer_node = inner_neighbor = the old root (inner_neighbor equal to
        outer_node marks "no inner neighbour"), outer_tree = all nodes and vertices = {}. An empty
        constraint is satisfied by every bag, so ``glue`` attaches the whole old tree to D*
        (the old and new parts share no vertex, as B(T*) = {}).
      * an empty GHD: returns [].

    Raises InvalidGHDError if ``t_star`` contains unknown ids or is not connected (it then is not
    a subtree, Def 4.1).
    """
    s = frozenset(t_star)
    if not ghd.is_connected(s):  # also rejects unknown ids
        raise InvalidGHDError(f"bag_constraints: T* = {sorted(s)} is not a connected subtree")
    if len(ghd) == 0:
        return []
    if not s:
        root = ghd.root
        return [BagConstraint(outer_node=root, inner_neighbor=root,
                              outer_tree=frozenset(ghd.node_ids()), vertices=frozenset())]
    b_star = ghd.bag_union(s)
    out: list[BagConstraint] = []
    for tree in ghd.components_without(s):
        links = [(u, w) for u in sorted(tree) for w in ghd.tree_neighbors(u) if w in s]
        _invariant(
            len(links) == 1,
            f"invariant I5 violated: outer tree {sorted(tree)} meets T* = {sorted(s)} by tree "
            f"edges {links} (expected exactly one)")
        u, w = links[0]
        out.append(BagConstraint(outer_node=u, inner_neighbor=w, outer_tree=tree,
                                 vertices=ghd.node(u).bag & b_star))
    out.sort(key=lambda c: c.outer_node)
    return out

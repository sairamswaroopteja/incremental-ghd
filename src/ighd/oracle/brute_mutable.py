"""Brute-force delta-mutable subtrees (stage S5; reference for Alg 2 and Lemma 4.4).

Enumerates every connected node subset T* of a small GHD (including the empty set and the whole
tree), and keeps those satisfying both conditions of Def 4.1 checked *directly from the
definition* (not via ighd.mutable).

Def 4.1 (PAPER_ANALYSIS D18): T* is delta-mutable iff, with X = B(T minus T*),
  (i)  H[X] = delta(H)[X], and
  (ii) no vertex of V(delta(H)) minus V(H) is adjacent in delta(H) to a vertex of X.
(i) is read per A2: EDGEWISE compares each old edge e with its image s_delta(e) on X (a deleted
edge counts as the empty set, and edges of delta(H) outside the image must miss X); SET compares
the two sets of non-empty restrictions. Both readings are evaluated inline here, independently of
ighd.hypergraph.compare. Adjacency in (ii) means sharing an edge of delta(H) (A10).

Lemma 4.4 states that under EDGEWISE the minimum delta-mutable subtree is unique; the output of
this module lets tests check that and compare it with Algorithm 2.
"""

from __future__ import annotations

from collections import deque

from ighd.common.config import PAPER_DEFAULT, InducedComparison, Semantics
from ighd.common.errors import InvalidModificationError, OracleTooLargeError
from ighd.common.types import EdgeName, NodeId, VertexSet
from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult

MAX_BRUTE_NODES = 12
"""Size guard: larger GHDs raise OracleTooLargeError."""


def _check_change(change: ModificationResult) -> VertexSet:
    """Verify the ModificationResult invariants this oracle relies on; return V_new.

    s_delta must have exactly the keys E(old) and values in E(new) or None, and
    change.new_vertices must equal V(new) - V(old) (the set Def 4.1 (ii) is about).
    Raises InvalidModificationError otherwise, so a malformed change is never judged silently.
    """
    old, new = change.old, change.new
    if set(change.s_delta) != set(old.edge_names):
        raise InvalidModificationError(
            f"s_delta keys {sorted(change.s_delta)} differ from E(old) {sorted(old.edge_names)}")
    bad = sorted(e for e, t in change.s_delta.items() if t is not None and t not in new.edge_names)
    if bad:
        raise InvalidModificationError(f"s_delta maps {bad} to names that are not edges of delta(H)")
    v_new = new.vertices - old.vertices
    if frozenset(change.new_vertices) != v_new:
        raise InvalidModificationError(
            f"new_vertices {sorted(change.new_vertices)} != V(new) - V(old) = {sorted(v_new)}")
    return v_new


def _connected(adj: dict[NodeId, tuple[NodeId, ...]], nodes: frozenset[NodeId]) -> bool:
    """True iff ``nodes`` induces a connected subgraph of the tree (the empty set is connected)."""
    if not nodes:
        return True
    start = min(nodes)
    seen = {start}
    queue = deque([start])
    while queue:
        x = queue.popleft()
        for y in adj[x]:
            if y in nodes and y not in seen:
                seen.add(y)
                queue.append(y)
    return len(seen) == len(nodes)


def _condition_i(change: ModificationResult, x: VertexSet, mode: InducedComparison) -> bool:
    """Def 4.1 (i): H[X] = delta(H)[X] under the A2 reading ``mode``."""
    old_edges = change.old.edges
    new_edges = change.new.edges
    if mode is InducedComparison.EDGEWISE:
        image: set[EdgeName] = set()
        for e, vs in old_edges.items():
            target = change.s_delta[e]
            counterpart: VertexSet = frozenset() if target is None else new_edges[target]
            if target is not None:
                image.add(target)
            if vs & x != counterpart & x:
                return False
        return all(not (vs & x) for f, vs in new_edges.items() if f not in image)
    if mode is InducedComparison.SET:
        before = {vs & x for vs in old_edges.values()} - {frozenset()}
        after = {vs & x for vs in new_edges.values()} - {frozenset()}
        return before == after
    raise ValueError(f"unknown induced comparison {mode!r}")  # pragma: no cover


def _condition_ii(change: ModificationResult, x: VertexSet, v_new: VertexSet) -> bool:
    """Def 4.1 (ii): no new vertex shares an edge of delta(H) with a vertex of X."""
    if not v_new:
        return True
    return not any(vs & v_new and vs & x for vs in change.new.edges.values())


def all_mutable_subtrees(
    change: ModificationResult, ghd: GHD, semantics: Semantics = PAPER_DEFAULT
) -> list[frozenset[NodeId]]:
    """All delta-mutable subtrees of ``ghd`` (a GHD of change.old), sorted by (size, ids).

    Every one of the 2^|T| node subsets is tested for connectedness in the unrooted tree (BFS over
    ``tree_neighbors``; the empty set counts) and then for Def 4.1 (i) and (ii) with
    X = B(T minus T*). Raises OracleTooLargeError above MAX_BRUTE_NODES nodes and
    InvalidModificationError if ``change`` violates the ModificationResult invariants.
    """
    n = len(ghd)
    if n > MAX_BRUTE_NODES:
        raise OracleTooLargeError(
            f"all_mutable_subtrees: {n} nodes exceed MAX_BRUTE_NODES={MAX_BRUTE_NODES}")
    v_new = _check_change(change)
    ids = sorted(node.id for node in ghd)
    bags = {node.id: frozenset(node.bag) for node in ghd}
    adj = {u: tuple(ghd.tree_neighbors(u)) for u in ids}
    mode = semantics.induced_comparison

    found: list[frozenset[NodeId]] = []
    for mask in range(1 << n):
        t_star = frozenset(ids[i] for i in range(n) if mask >> i & 1)
        if not _connected(adj, t_star):
            continue
        x: set[str] = set()
        for u in ids:
            if u not in t_star:
                x |= bags[u]
        xs = frozenset(x)
        if _condition_i(change, xs, mode) and _condition_ii(change, xs, v_new):
            found.append(t_star)
    found.sort(key=lambda t: (len(t), sorted(t)))
    return found

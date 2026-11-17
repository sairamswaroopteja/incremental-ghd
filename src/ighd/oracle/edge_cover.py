"""Exact integral edge-cover number rho_H(B) (stage S5).

rho_H(B) = min |lambda| over lambda <= E(H) with B <= B(lambda); the cost of a bag in a GHD
(paper §2.2: the width of a GHD is max |lambda_u|, and the best guard of a bag B_u has size
rho_H(B_u)).

Method (exact). Encode B as a bitmask and every edge as e & B. Then
    rho(0) = 0,   rho(T) = 1 + min { rho(T - e) : e an edge containing the lowest vertex of T },
because some edge of every cover contains that vertex. The recursion is memoised per subset T,
so the cost is O(2^|B| * |E|) instead of the O(|E|^rho) of trying all combinations (the test
suite cross-checks it against the plain combination search).

A minimum cover never contains an edge disjoint from what is still uncovered when it is added
(dropping it would give a smaller cover); ``minimum_edge_cover`` uses this to enumerate covers
in lexicographic order of their sorted name tuples with rho as a pruning bound.

INDEPENDENCE RULE: imports only ighd.common and ighd.hypergraph.core.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ighd.common.types import EdgeName, EdgeSet, Vertex, VertexSet
from ighd.hypergraph.core import Hypergraph


class CoverSolver:
    """Memoised exact set cover over bitmask-encoded edges (helper shared with ghw_dp).

    ``rho(T)`` is the minimum number of edge masks whose union contains T, or None if the union
    of all masks does not contain T. Bit i must be a valid vertex index (< 64 is not required).
    """

    def __init__(self, edge_masks: Sequence[int]) -> None:
        self.edge_masks: list[int] = list(edge_masks)
        self._by_bit: dict[int, list[int]] = {}
        self._universe = 0
        for m in set(self.edge_masks):
            self._universe |= m
            rest = m
            while rest:
                low = rest & -rest
                self._by_bit.setdefault(low, []).append(m)
                rest ^= low
        self._memo: dict[int, int] = {0: 0}

    def rho(self, target: int) -> int | None:
        """Minimum number of edges covering ``target``; None if impossible."""
        if target & ~self._universe:
            return None
        return self._rho(target)

    def _rho(self, target: int) -> int:
        got = self._memo.get(target)
        if got is not None:
            return got
        low = target & -target
        best = min(self._rho(target & ~m) for m in self._by_bit[low]) + 1
        self._memo[target] = best
        return best


def _encode(h: Hypergraph, target: VertexSet) -> tuple[list[EdgeName], list[int], int] | None:
    """Names (sorted) and masks (restricted to B) of the edges meeting B, and B's mask.

    None if B is not inside V(H).
    """
    if not target <= h.vertices:
        return None
    index = {v: i for i, v in enumerate(sorted(target))}
    names: list[EdgeName] = []
    masks: list[int] = []
    for name, vs in sorted(h.edges.items()):
        r = vs & target
        if r:
            names.append(name)
            masks.append(sum(1 << index[v] for v in r))
    return names, masks, (1 << len(index)) - 1


def edge_cover_number(h: Hypergraph, vertices: Iterable[Vertex]) -> int | None:
    """rho_H(B); None if some vertex of B lies in no edge of H; 0 for the empty set."""
    target = frozenset(vertices)
    if not target:
        return 0
    enc = _encode(h, target)
    if enc is None:
        return None
    _, masks, full = enc
    return CoverSolver(masks).rho(full)


def minimum_edge_cover(h: Hypergraph, vertices: Iterable[Vertex]) -> EdgeSet | None:
    """A witness lambda of size rho_H(B) (smallest names first, for determinism).

    Among all minimum covers, returns the one whose sorted tuple of edge names is
    lexicographically smallest: a depth-first search picks edges in increasing name order,
    only edges that meet the still-uncovered part (true of every minimum cover, see module
    docstring), and prunes when rho(uncovered) exceeds the remaining budget. The first cover it
    completes is therefore the lexicographically smallest of size rho.
    None if some vertex of B is not in V(H); the empty set for empty B.
    """
    target = frozenset(vertices)
    if not target:
        return frozenset()
    enc = _encode(h, target)
    if enc is None:
        return None
    names, masks, full = enc
    solver = CoverSolver(masks)
    k = solver.rho(full)
    assert k is not None

    def search(start: int, uncovered: int, budget: int) -> list[int] | None:
        if not uncovered:
            return []
        if budget == 0 or solver.rho(uncovered) > budget:  # type: ignore[operator]
            return None
        for i in range(start, len(masks)):
            if masks[i] & uncovered:
                rest = search(i + 1, uncovered & ~masks[i], budget - 1)
                if rest is not None:
                    return [i, *rest]
        return None

    picked = search(0, full, k)
    assert picked is not None and len(picked) == k
    return frozenset(names[i] for i in picked)

"""Exact ghw by dynamic programming over elimination orderings (stage S5).

Background (PAPER_ANALYSIS §3): ghw(H) = min over tree decompositions of max rho_H(bag). Since
rho_H is monotone and every tree decomposition refines to one from a minimal triangulation with
bags inside the old bags, the minimum is attained over elimination orderings of the primal graph:
    f(S) = min_{v in S} max( f(S - v), rho_H({v} u Q(S - v, v)) ),   f({}) = 0,
where Q(S, v) is the set of vertices outside S u {v} reachable from v through S. ghw(H) = f(V(H)).

This method is deliberately different from the top-down search of ighd.static, so the two can
cross-check each other (IMPLEMENTATION_PLAN §F, Level 5).
"""

from __future__ import annotations

from ighd.common.errors import OracleTooLargeError
from ighd.common.types import NodeId, Vertex
from ighd.ghd.tree import GHD
from ighd.hypergraph.core import Hypergraph
from ighd.oracle.edge_cover import CoverSolver, minimum_edge_cover

MAX_ORACLE_VERTICES = 16
"""Size guard: larger inputs raise OracleTooLargeError."""


def _bits(mask: int) -> list[int]:
    """Indices of the set bits of ``mask``, increasing."""
    out: list[int] = []
    i = 0
    while mask:
        if mask & 1:
            out.append(i)
        mask >>= 1
        i += 1
    return out


class _Primal:
    """Bitmask view of H: vertex i is the i-th smallest vertex name."""

    def __init__(self, h: Hypergraph) -> None:
        self.names: list[Vertex] = sorted(h.vertices)
        index = {v: i for i, v in enumerate(self.names)}
        self.edge_masks: list[int] = [sum(1 << index[v] for v in vs) for _, vs in sorted(h.edges.items())]
        self.adj: list[int] = [0] * len(self.names)
        for m in self.edge_masks:
            for i in _bits(m):
                self.adj[i] |= m
        for i in range(len(self.names)):
            self.adj[i] &= ~(1 << i)
        self._solver = CoverSolver(self.edge_masks)

    def q(self, s: int, v: int) -> int:
        """Q(S, v): vertices outside S u {v} reachable from v by a path with interior in S.

        Equivalently the neighbours of v in the graph obtained by eliminating S (the fill-in
        neighbourhood); v must not lie in S.
        """
        inside = 1 << v      # v plus the vertices of S reached so far
        frontier = inside
        reach = 0
        while frontier:
            nb = 0
            for x in _bits(frontier):
                nb |= self.adj[x]
            reach |= nb
            frontier = nb & s & ~inside
            inside |= frontier
        return reach & ~s & ~(1 << v)

    def rho(self, bag: int) -> int:
        """rho_H(bag), memoised by bag mask (every bag lies inside V(H), so never None)."""
        r = self._solver.rho(bag)
        assert r is not None, "bag outside V(H)"
        return r


def exact_ghw(h: Hypergraph) -> tuple[int, GHD]:
    """Return (ghw(H), a witness GHD of that width). ghw of the empty hypergraph is 0.

    DP over vertex subsets S (bitmasks): f(S) = min over v in S (v = the vertex of S eliminated
    last) of max(f(S - v), rho_H({v} u Q(S - v, v))). Ties go to the smallest vertex name.
    The witness is the tree decomposition of the optimal elimination ordering: one node per
    vertex v_i with bag {v_i} u Q({v_1..v_{i-1}}, v_i), parent = the node of the earliest
    eliminated vertex of Q(...); roots of further components hang below the first root (their
    bags share no vertex with it, so connectedness is preserved). Covers are minimum edge covers
    (lexicographically smallest), so the witness width equals ghw.

    Raises OracleTooLargeError if |V(H)| > MAX_ORACLE_VERTICES.
    """
    n_vertices = len(h.vertices)
    if n_vertices > MAX_ORACLE_VERTICES:
        raise OracleTooLargeError(
            f"exact_ghw: {n_vertices} vertices exceed MAX_ORACLE_VERTICES={MAX_ORACLE_VERTICES}")
    if n_vertices == 0:
        return 0, GHD()

    pg = _Primal(h)
    n = n_vertices
    full = (1 << n) - 1
    inf = n + 1
    f = [0] * (1 << n)
    last = [0] * (1 << n)
    for s in range(1, full + 1):
        best = inf
        choice = -1
        for v in _bits(s):
            rest = s & ~(1 << v)
            sub = f[rest]
            if sub >= best:
                continue
            val = max(sub, pg.rho((1 << v) | pg.q(rest, v)))
            if val < best:
                best, choice = val, v
        f[s] = best
        last[s] = choice

    # reconstruct an optimal elimination ordering v_1 .. v_n
    reverse_order: list[int] = []
    s = full
    while s:
        v = last[s]
        reverse_order.append(v)
        s &= ~(1 << v)
    order = reverse_order[::-1]
    position = {v: i for i, v in enumerate(order)}

    bags: dict[int, int] = {}
    parent_vertex: dict[int, int | None] = {}
    eliminated = 0
    for v in order:
        q = pg.q(eliminated, v)
        bags[v] = (1 << v) | q
        parent_vertex[v] = min(_bits(q), key=position.__getitem__) if q else None
        eliminated |= 1 << v

    ghd = GHD()
    node_of: dict[int, NodeId] = {}
    first_root: NodeId | None = None
    width_seen = 0
    for v in reverse_order:  # parents are eliminated later, hence created earlier
        bag = [pg.names[i] for i in _bits(bags[v])]
        cover = minimum_edge_cover(h, bag)
        assert cover is not None
        width_seen = max(width_seen, len(cover))
        p = parent_vertex[v]
        parent = node_of[p] if p is not None else first_root
        node_of[v] = ghd.add_node(bag, cover, parent=parent, label=f"elim:{pg.names[v]}")
        if first_root is None:
            first_root = node_of[v]
    assert width_seen == f[full], (width_seen, f[full])
    return f[full], ghd

"""The Hypergraph value type (stage S1).

Conventions (PAPER_ANALYSIS D2-D5, A1, A9):
  * edges are named and non-empty; an empty edge is rejected;
  * V(H) is *derived* as the union of the edges, so isolated vertices cannot exist;
  * two differently named edges may have the same vertex set (A9); they stay distinct;
  * H[U] keeps, for every edge e, the restriction e & U if it is non-empty (A1), keyed by
    the edge's name, so that both the edge-wise and the set reading of A2 can be evaluated.
Hypergraph objects are immutable; every "modifying" method returns a new object.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType

from ighd.common.errors import InvalidHypergraphError
from ighd.common.types import EdgeName, EdgeSet, Vertex, VertexSet

InducedView = Mapping[EdgeName, VertexSet]
"""H[U] as {edge name: non-empty e & U}. The vertex set of H[U] is U itself (paper §2.1)."""

_EMPTY: VertexSet = frozenset()


def _freeze_edges(edges: Mapping[EdgeName, Iterable[Vertex]]) -> dict[EdgeName, VertexSet]:
    """Validate and freeze an edge mapping (D2: named, non-empty edges over string vertices)."""
    if not isinstance(edges, Mapping):
        raise InvalidHypergraphError(f"edges must be a mapping name -> vertices, got {type(edges).__name__}")
    frozen: dict[EdgeName, VertexSet] = {}
    for name, vs in edges.items():
        if not isinstance(name, str):
            raise InvalidHypergraphError(f"edge name {name!r} is not a str")
        try:
            fs = frozenset(vs)
        except TypeError as exc:
            raise InvalidHypergraphError(f"edge {name!r}: vertices {vs!r} are not an iterable of str") from exc
        bad = [v for v in fs if not isinstance(v, str)]
        if bad:
            raise InvalidHypergraphError(f"edge {name!r} has non-str vertices {bad!r}")
        if not fs:
            raise InvalidHypergraphError(f"edge {name!r} is empty (paper §2.1: edges are non-empty)")
        frozen[name] = fs
    return frozen


class Hypergraph:
    """An immutable hypergraph H = (V(H), E(H)) with named edges (paper §2.1, PAPER_ANALYSIS D2)."""

    __slots__ = ("_edges", "_edges_view", "_names", "_vertices", "_incidence", "_hash")

    def __init__(self, edges: Mapping[EdgeName, Iterable[Vertex]]) -> None:
        """Build from {edge name: vertices}. Raises InvalidHypergraphError on an empty edge."""
        frozen = _freeze_edges(edges)
        # Sorted insertion order makes iteration over the internal dict deterministic.
        self._edges: dict[EdgeName, VertexSet] = {n: frozen[n] for n in sorted(frozen)}
        self._edges_view: Mapping[EdgeName, VertexSet] = MappingProxyType(self._edges)
        self._names: EdgeSet = frozenset(self._edges)
        incidence: dict[Vertex, set[EdgeName]] = {}
        for name, vs in self._edges.items():
            for v in vs:
                incidence.setdefault(v, set()).add(name)
        self._incidence: Mapping[Vertex, EdgeSet] = MappingProxyType(
            {v: frozenset(es) for v, es in incidence.items()})
        self._vertices: VertexSet = frozenset(incidence)
        self._hash: int = hash(frozenset(self._edges.items()))

    def __setattr__(self, key: str, value: object) -> None:
        if hasattr(self, "_hash"):
            raise AttributeError("Hypergraph is immutable")
        object.__setattr__(self, key, value)

    # --- basic access -------------------------------------------------------------------
    @property
    def edges(self) -> Mapping[EdgeName, VertexSet]:
        """Read-only map edge name -> vertex set (E(H) with names, D2)."""
        return self._edges_view

    @property
    def edge_names(self) -> EdgeSet:
        """The set of edge names (E(H) viewed as names, D3)."""
        return self._names

    @property
    def vertices(self) -> VertexSet:
        """V(H) = union of all edges."""
        return self._vertices

    def edge(self, name: EdgeName) -> VertexSet:
        """Vertices of one edge (KeyError naming the edge if unknown)."""
        try:
            return self._edges[name]
        except KeyError:
            raise KeyError(f"unknown edge {name!r}") from None

    def incident(self, v: Vertex) -> EdgeSet:
        """Names of the edges containing v (I(v)); empty for a vertex not in V(H)."""
        return self._incidence.get(v, _EMPTY)

    def covered_vertices(self, names: Iterable[EdgeName]) -> VertexSet:
        """B(E) = union of the given edges (paper §2.2, D5). KeyError on an unknown name."""
        out: set[Vertex] = set()
        for n in names:
            out |= self.edge(n)
        return frozenset(out)

    def neighbors(self, v: Vertex) -> VertexSet:
        """Vertices sharing at least one edge with v, excluding v itself."""
        out: set[Vertex] = set()
        for n in self.incident(v):
            out |= self._edges[n]
        out.discard(v)
        return frozenset(out)

    def adjacent_to(self, vertices: Iterable[Vertex]) -> VertexSet:
        """All vertices sharing an edge with some vertex of ``vertices`` (Alg 2 line 9).

        Returns the union, over v in ``vertices`` & V(H), of all edges containing v. This
        INCLUDES every vertex of ``vertices`` that lies in V(H) (a vertex shares an edge with
        itself); vertices not in V(H) contribute nothing. Algorithm 2 line 9 only uses the
        result intersected with the *new* vertices of delta(H), which are never in the old
        bags, so the inclusion is harmless there (PAPER_ANALYSIS A10).
        """
        out: set[Vertex] = set()
        for v in set(vertices):
            for n in self.incident(v):
                out |= self._edges[n]
        return frozenset(out)

    def degree(self, v: Vertex) -> int:
        """Number of edges containing v (0 for a vertex not in V(H))."""
        return len(self.incident(v))

    def rank(self) -> int:
        """Maximum edge size (0 for the empty hypergraph)."""
        return max((len(vs) for vs in self._edges.values()), default=0)

    # --- derived hypergraphs ------------------------------------------------------------
    def induced(self, vertices: Iterable[Vertex]) -> InducedView:
        """H[U]: {name: e & U} for every edge with e & U non-empty (D4, A1).

        Vertices of U outside V(H) are ignored (they would be isolated in H[U]). Returns a
        fresh dict in edge-name order.
        """
        u = frozenset(vertices)
        out: dict[EdgeName, VertexSet] = {}
        for name, vs in self._edges.items():
            r = vs & u
            if r:
                out[name] = r
        return out

    def subhypergraph(self, names: Iterable[EdgeName]) -> "Hypergraph":
        """The subhypergraph consisting of the given edges (D3). KeyError on an unknown name."""
        return Hypergraph({n: self.edge(n) for n in names})

    def with_edges(self, extra: Mapping[EdgeName, Iterable[Vertex]]) -> "Hypergraph":
        """New hypergraph with additional (or replaced, if the name exists) edges."""
        merged: dict[EdgeName, Iterable[Vertex]] = dict(self._edges)
        merged.update(extra)
        return Hypergraph(merged)

    def without_edges(self, names: Iterable[EdgeName]) -> "Hypergraph":
        """New hypergraph without the given edges (KeyError on an unknown name)."""
        drop = set(names)
        unknown = sorted(n for n in drop if n not in self._edges)
        if unknown:
            raise KeyError(f"unknown edge(s) {unknown!r}")
        return Hypergraph({n: vs for n, vs in self._edges.items() if n not in drop})

    def has_duplicate_edges(self) -> bool:
        """True if two differently named edges have equal vertex sets (A9)."""
        return len(set(self._edges.values())) < len(self._edges)

    # --- value semantics ----------------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        """Equal iff the same edge names map to the same vertex sets."""
        if not isinstance(other, Hypergraph):
            return NotImplemented
        return self._hash == other._hash and self._edges == other._edges

    def __hash__(self) -> int:
        return self._hash

    def __iter__(self) -> Iterator[EdgeName]:
        """Edge names in sorted order."""
        return iter(self._edges)

    def __len__(self) -> int:
        """Number of edges |E(H)|."""
        return len(self._edges)

    def __repr__(self) -> str:
        body = ", ".join(f"{n!r}: {sorted(vs)!r}" for n, vs in self._edges.items())
        return f"Hypergraph({{{body}}})"

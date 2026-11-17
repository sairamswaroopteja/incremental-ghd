"""[U]-components (stage S6; paper §2.3, D9, A3).

Defined on EDGES: two edges are [U]-adjacent iff they share a vertex outside U; components are
maximal [U]-connected edge sets. Edges e <= U are covered by the separator and belong to no
component (A3; Examples 2.3 and 5.2), unless Semantics.inside_edges_form_components is set.
This is NOT ordinary connectivity of the primal graph.
"""

from __future__ import annotations

from collections.abc import Iterable

from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.types import EdgeName, EdgeSet, Vertex, VertexSet
from ighd.hypergraph.core import Hypergraph


def _edge_names(h: Hypergraph, edges: Iterable[EdgeName]) -> list[EdgeName]:
    """Distinct names of ``edges`` in sorted order; KeyError naming the first unknown edge."""
    names = sorted(set(edges))
    for n in names:
        h.edge(n)  # raises KeyError("unknown edge 'n'")
    return names


def components(
    h: Hypergraph,
    edges: Iterable[EdgeName],
    separator: Iterable[Vertex],
    semantics: Semantics = PAPER_DEFAULT,
) -> list[EdgeSet]:
    """The [U]-components of the subhypergraph ``edges``, sorted by smallest edge name.

    Paper §2.3 (PAPER_ANALYSIS D9): for U = ``separator``, edges e1, e2 are [U]-adjacent iff
    (e1 & e2) - U is non-empty; [U]-connectedness is the transitive closure, and a
    [U]-component is a maximal [U]-connected set of edges. Only the edges named in ``edges``
    (a subset of E(h)) are considered; an unknown name raises KeyError naming it. Separator
    vertices outside V(h) are irrelevant (they are in no edge).

    A3 (ledger L-A3): an edge e <= U is covered by the separator and belongs to no component,
    as in the paper's Examples 2.3 and 5.2. With ``semantics.inside_edges_form_components``
    (the literal reading, test-only) each such edge is a singleton component instead.

    Union-find over edges, joining all edges that contain a common vertex v not in U;
    O(sum of edge sizes * alpha) plus sorting.
    """
    u = frozenset(separator)
    names = _edge_names(h, edges)
    parent: dict[EdgeName, EdgeName] = {}

    def find(x: EdgeName) -> EdgeName:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:  # path compression
            parent[x], x = root, parent[x]
        return root

    owner: dict[Vertex, EdgeName] = {}  # first edge seen containing an outside vertex
    singletons: list[EdgeSet] = []
    for name in names:
        outside = h.edge(name) - u
        if not outside:
            if semantics.inside_edges_form_components:
                singletons.append(frozenset((name,)))
            continue
        parent[name] = name
        for v in outside:
            other = owner.setdefault(v, name)
            if other != name:
                ra, rb = find(other), find(name)
                if ra != rb:
                    # keep the lexicographically smaller root (cosmetic only)
                    if rb < ra:
                        ra, rb = rb, ra
                    parent[rb] = ra

    groups: dict[EdgeName, set[EdgeName]] = {}
    for name in parent:
        groups.setdefault(find(name), set()).add(name)
    result = [frozenset(g) for g in groups.values()] + singletons
    result.sort(key=min)
    return result


def inside_edges(h: Hypergraph, edges: Iterable[EdgeName], separator: Iterable[Vertex]) -> EdgeSet:
    """Edges of ``edges`` entirely inside the separator (covered at the separator's node).

    These are the edges e with e <= U that, under the A3 reading (ledger L-A3, PAPER_DEFAULT),
    belong to no [U]-component; ``components(...)`` and ``inside_edges(...)`` together
    partition ``edges``. KeyError on an unknown edge name.
    """
    u = frozenset(separator)
    return frozenset(n for n in _edge_names(h, edges) if h.edge(n) <= u)


def connection(h: Hypergraph, component: Iterable[EdgeName], separator: Iterable[Vertex]) -> VertexSet:
    """conn(c) = V(c) & U: what the child's root bag must contain (A13, A21).

    V(c) is the union of the component's edges (paper §2.3, D9) and U is the parent separator.
    KeyError on an unknown edge name.
    """
    return h.covered_vertices(component) & frozenset(separator)

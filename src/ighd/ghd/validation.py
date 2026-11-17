"""Independent GHD validator (stage S4; paper §2.2).

Checks exactly the three conditions of a GHD of H:
  (1) every EDGE e of H lies inside some bag (edge coverage; A4: vertex coverage alone is weaker);
  (2) for every vertex v, the nodes whose bags contain v form a connected subtree;
  (3) every bag is contained in the union of its cover: B_u <= B(lambda_u).
plus well-formedness (cover edges exist in H, bag vertices exist in H) and the width.

INDEPENDENCE RULE: this module must not import anything from ighd.static, ighd.update,
ighd.scenes, ighd.constraints or ighd.mutable. It is ground truth for those modules.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ighd.common.types import EdgeName, NodeId, Vertex, VertexSet
from ighd.ghd.tree import GHD
from ighd.hypergraph.core import Hypergraph


@dataclass(frozen=True)
class Violation:
    """Base class of all validation failures."""

    def describe(self) -> str:
        return repr(self)


@dataclass(frozen=True)
class UncoveredEdge(Violation):
    """Condition (1): no bag contains the edge."""

    edge: EdgeName
    vertices: VertexSet


@dataclass(frozen=True)
class DisconnectedVertex(Violation):
    """Condition (2): the occurrence set of ``vertex`` splits into several tree components."""

    vertex: Vertex
    parts: tuple[frozenset[NodeId], ...]


@dataclass(frozen=True)
class UnguardedVertices(Violation):
    """Condition (3): bag vertices of ``node`` not covered by its cover edges."""

    node: NodeId
    missing: VertexSet


@dataclass(frozen=True)
class UnknownCoverEdge(Violation):
    """A cover names an edge that H does not have (e.g. a deleted constraint)."""

    node: NodeId
    edge: EdgeName


@dataclass(frozen=True)
class UnknownBagVertex(Violation):
    """A bag contains a vertex that H does not have."""

    node: NodeId
    vertex: Vertex


@dataclass(frozen=True)
class ValidationReport:
    """Result of ``validate``. ``ok`` iff ``violations`` is empty."""

    violations: tuple[Violation, ...]
    width: int
    edge_cover_map: Mapping[EdgeName, tuple[NodeId, ...]] = field(default_factory=dict)
    """For every edge, the nodes whose bags contain it (empty tuple if uncovered)."""
    warnings: tuple[str, ...] = ()
    """Non-fatal observations, e.g. empty bags."""

    @property
    def ok(self) -> bool:
        return not self.violations


def validate(h: Hypergraph, ghd: GHD) -> ValidationReport:
    """Check that ``ghd`` is a GHD of ``h`` (conditions (1)-(3) plus well-formedness).

    Paper §2.2 (PAPER_ANALYSIS D6): <T, (B_u), (lambda_u)> is a GHD of H iff
      (1) every edge e of H satisfies e <= B_u for some node u   (edge coverage; A4),
      (2) for every vertex v of H, {u : v in B_u} induces a connected subtree of T,
      (3) B_u <= B(lambda_u) for every node u.
    The tree is treated as unrooted (only ``tree_neighbors`` is used). An empty GHD (no nodes)
    is a GHD only of the empty hypergraph: every edge of a non-empty H is reported uncovered.

    Violations are returned in a fixed order: unknown cover edges and unknown bag vertices
    (by node id, then name), uncovered edges (by edge name), disconnected vertices (by vertex),
    unguarded vertices (by node id). Width (D7) is max |lambda_u| over all nodes.
    """
    node_ids = sorted(n.id for n in ghd)
    bags: dict[NodeId, VertexSet] = {}
    covers: dict[NodeId, frozenset[EdgeName]] = {}
    for n in ghd:
        bags[n.id] = frozenset(n.bag)
        covers[n.id] = frozenset(n.cover)
    edges: Mapping[EdgeName, VertexSet] = h.edges
    vertices = h.vertices

    unknown_cover: list[Violation] = []
    unknown_vertex: list[Violation] = []
    for u in node_ids:
        unknown_cover.extend(UnknownCoverEdge(u, e) for e in sorted(covers[u]) if e not in edges)
        unknown_vertex.extend(UnknownBagVertex(u, v) for v in sorted(bags[u]) if v not in vertices)

    # (1) edge coverage
    uncovered: list[Violation] = []
    cover_map: dict[EdgeName, tuple[NodeId, ...]] = {}
    for name in sorted(edges):
        vs = edges[name]
        holders = tuple(u for u in node_ids if vs <= bags[u])
        cover_map[name] = holders
        if not holders:
            uncovered.append(UncoveredEdge(name, frozenset(vs)))

    # (2) connectedness of every vertex's occurrence set, by BFS over the unrooted tree
    disconnected: list[Violation] = []
    for v in sorted(vertices):
        occurrences = frozenset(u for u in node_ids if v in bags[u])
        parts = _tree_pieces(ghd, occurrences)
        if len(parts) > 1:
            disconnected.append(DisconnectedVertex(v, parts))

    # (3) guards: B_u <= union of the (known) cover edges
    unguarded: list[Violation] = []
    for u in node_ids:
        guarded: set[Vertex] = set()
        for e in covers[u]:
            if e in edges:
                guarded |= edges[e]
        missing = bags[u] - guarded
        if missing:
            unguarded.append(UnguardedVertices(u, frozenset(missing)))

    warnings: list[str] = []
    for u in node_ids:
        if not bags[u]:
            warnings.append(f"node {u} has an empty bag")
    in_bags: set[Vertex] = set()
    for u in node_ids:
        in_bags |= bags[u]
    absent = sorted(vertices - in_bags)
    if absent:
        warnings.append(f"vertices {absent} occur in no bag (vertex coverage fails; A4)")

    violations = tuple(unknown_cover + unknown_vertex + uncovered + disconnected + unguarded)
    return ValidationReport(violations=violations, width=width(ghd), edge_cover_map=cover_map,
                            warnings=tuple(warnings))


def _tree_pieces(ghd: GHD, nodes: Iterable[NodeId]) -> tuple[frozenset[NodeId], ...]:
    """Connected pieces of the subgraph of the (unrooted) tree induced by ``nodes``.

    BFS over ``tree_neighbors`` restricted to the set; pieces sorted by their smallest id.
    The empty set has no pieces.
    """
    remaining = set(nodes)
    pieces: list[frozenset[NodeId]] = []
    for start in sorted(remaining):
        if start not in remaining:
            continue
        remaining.discard(start)
        piece = {start}
        queue = deque([start])
        while queue:
            x = queue.popleft()
            for y in ghd.tree_neighbors(x):
                if y in remaining:
                    remaining.discard(y)
                    piece.add(y)
                    queue.append(y)
        pieces.append(frozenset(piece))
    return tuple(sorted(pieces, key=min))


def width(ghd: GHD) -> int:
    """max |lambda_u| over all nodes (paper §2.2, D7: width counts guard edges, never bag size).

    0 for an empty tree.
    """
    return max((len(n.cover) for n in ghd), default=0)

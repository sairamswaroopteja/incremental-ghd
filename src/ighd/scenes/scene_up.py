"""Algorithm 4 (SceneCreationUp) (stage S11).

Post-order over T_n. For nodes whose whole subtree lies outside T*, collect the covered edges
(lines 8-12), compute the [B_n]-components of those edges (line 14) and, if their number equals the
number of children, record an out-scene (lines 15-17) under the key chosen by
Semantics.up_scene_key (A17). Returns the mapping fragment and the covered edges (line 18).

Readings (FAITHFULNESS_LEDGER):
  * L-A17: the key of an up-scene is ``coveredEdges`` by default (COVERED_EDGES); LITERAL_H_PRIME
    uses the argument H' and INTERSECTING_EDGES uses {e in E(H') : e & V(T_n) != {}}, with V(T_n)
    the union of the delta-bags of T_n.
  * L-A20: delta is applied to bags: lines 11 and 13 use delta(B_n) = B_n & V(delta(H)). For a node
    n with T_n disjoint from T* (the only nodes for which lines 10-17 run) this equals B_n under
    EDGEWISE semantics: a vertex v of B(T minus T*) missing from V(delta(H)) would change the
    restriction of an edge containing v, contradicting Lemma 4.2 / Def 4.1(i).
  * L-A25: up-scenes are always OUT (line 9 guarantees T_n & T* = {}).
  * Not covered by the paper (decision of this stage): an up-scene whose key would be the empty
    edge set (a leaf whose bag contains no edge of H') is not recorded; it is logged as
    'A4:L16' with detail "empty key: not recorded". No decomposition ever looks up an empty
    subhypergraph, and recording it would only make different leaves overwrite each other.

The traversal is iterative (post-order of T_n), so arbitrarily deep trees are fine.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ighd.common.config import PAPER_DEFAULT, Semantics, UpSceneKey
from ighd.common.errors import InvalidGHDError
from ighd.common.types import EdgeName, EdgeSet, NodeId, VertexSet
from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult
from ighd.scenes.mapping import SceneEntry, SceneEvent, SceneKind, SceneMapping
from ighd.static.separation import components


def _names(edges: EdgeSet | frozenset[str]) -> str:
    return "{" + ",".join(sorted(edges)) + "}"


@dataclass
class _Context:
    """Shared state of one scene creation run: inputs, delta-images of labels, and the event log.

    ``touches_t_star[n]`` is the test of Alg 3 line 9 / Alg 4 line 9: T_n & T* != {}.
    """

    change: ModificationResult
    ghd: GHD
    t_star: frozenset[NodeId]
    semantics: Semantics
    events: list[SceneEvent] = field(default_factory=list)
    touches_t_star: dict[NodeId, bool] = field(default_factory=dict)
    _dbag: dict[NodeId, VertexSet] = field(default_factory=dict)
    _guard: dict[NodeId, VertexSet] = field(default_factory=dict)
    _subtree_vertices: dict[NodeId, VertexSet] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ids = set(self.ghd.node_ids())
        unknown = sorted(n for n in self.t_star if n not in ids)
        if unknown:
            raise InvalidGHDError(f"T* contains unknown node ids {unknown!r}")
        for x in self.ghd.postorder():
            self.touches_t_star[x] = x in self.t_star or any(
                self.touches_t_star[c] for c in self.ghd.children(x))

    def log(self, line: str, node: NodeId, edges: EdgeSet, detail: str) -> None:
        self.events.append(SceneEvent(line, node, frozenset(edges), detail))

    def dbag(self, n: NodeId) -> VertexSet:
        """delta(B_n) = B_n & V(delta(H)) (paper §5.1; L-A20)."""
        if n not in self._dbag:
            self._dbag[n] = self.ghd.node(n).bag & self.change.new.vertices
        return self._dbag[n]

    def dcover(self, n: NodeId) -> EdgeSet:
        """delta(lambda_n) = {s_delta(e) : e in lambda_n}, deleted edges dropped (L-A20)."""
        out: set[EdgeName] = set()
        for e in self.ghd.node(n).cover:
            if e not in self.change.s_delta:
                raise InvalidGHDError(f"cover of node {n} names {e!r}, which is not an edge of the old hypergraph")
            t = self.change.s_delta[e]
            if t is not None:
                out.add(t)
        return frozenset(out)

    def guard_vertices(self, n: NodeId) -> VertexSet:
        """B(delta(lambda_n)), computed in delta(H) (Alg 3 line 3)."""
        if n not in self._guard:
            self._guard[n] = self.change.new.covered_vertices(self.dcover(n))
        return self._guard[n]

    def subtree_vertices(self, n: NodeId) -> VertexSet:
        """V(T_n): the union of the delta-bags of T_n (INTERSECTING_EDGES key, L-A17)."""
        if n not in self._subtree_vertices:
            for x in self.ghd.postorder(n):
                if x not in self._subtree_vertices:
                    acc = set(self.dbag(x))
                    for c in self.ghd.children(x):
                        acc |= self._subtree_vertices[c]
                    self._subtree_vertices[x] = frozenset(acc)
        return self._subtree_vertices[n]


def _up_key(ctx: _Context, n: NodeId, h_prime: EdgeSet, covered: EdgeSet) -> EdgeSet:
    """The key of the up-scene of Alg 4 line 16 under Semantics.up_scene_key (L-A17)."""
    mode = ctx.semantics.up_scene_key
    if mode is UpSceneKey.COVERED_EDGES:
        return covered
    if mode is UpSceneKey.LITERAL_H_PRIME:
        return h_prime
    assert mode is UpSceneKey.INTERSECTING_EDGES
    vt = ctx.subtree_vertices(n)
    new = ctx.change.new
    return frozenset(e for e in h_prime if new.edge(e) & vt)


def _up(ctx: _Context, node: NodeId, h_prime: EdgeSet) -> tuple[SceneMapping, EdgeSet]:
    """Algorithm 4 on T_node, iteratively in post-order (children before parents, in order)."""
    new = ctx.change.new
    ghd = ctx.ghd
    h_prime = frozenset(h_prime)
    edges_of_h = [(e, new.edge(e)) for e in sorted(h_prime)]
    results: dict[NodeId, tuple[SceneMapping, EdgeSet]] = {}
    for n in ghd.postorder(node):
        sigma = SceneMapping()                                   # line 2
        covered_below: set[EdgeName] = set()                     # line 3
        kids = ghd.children(n)
        for u in kids:                                           # line 4
            sigma_u, covered_u = results.pop(u)                  # line 5
            sigma.merge(sigma_u)                                 # line 6
            covered_below |= covered_u                           # line 7
        covered: set[EdgeName] = set(covered_below)              # line 8
        if not ctx.touches_t_star[n]:                            # line 9
            bag = ctx.dbag(n)                                    # delta(B_n) (L-A20)
            for e, vs in edges_of_h:                             # line 10
                if vs <= bag:                                    # line 11
                    covered.add(e)                               # line 12
            covered_fs = frozenset(covered)
            comps = components(new, covered_fs, bag, ctx.semantics)   # lines 13-14
            if len(comps) == len(kids):                          # line 15
                key = _up_key(ctx, n, h_prime, covered_fs)
                if key:
                    sigma.add(key, SceneEntry(n, SceneKind.OUT, "up"))   # lines 16-17
                    ctx.log("A4:L16", n, key,
                            f"out-scene {_names(key)} -> node {n} (key {ctx.semantics.up_scene_key.value}; "
                            f"covered edges {_names(covered_fs)})")
                else:
                    ctx.log("A4:L16", n, key, "empty key: not recorded")
            else:
                ctx.log("A4:L15", n, covered_fs,
                        f"{len(comps)} [B_n]-components {[_names(c) for c in comps]} of the covered "
                        f"edges but {len(kids)} children: no up-scene")
        results[n] = (sigma, frozenset(covered))
    return results[node]                                         # line 18


def scene_create_up(change: ModificationResult, ghd: GHD, node: NodeId, h_prime: EdgeSet,
                    t_star: frozenset[NodeId], semantics: Semantics = PAPER_DEFAULT
                    ) -> tuple[SceneMapping, EdgeSet]:
    """SceneCreationUp(node, H', T*) (Algorithm 4) as a standalone call.

    Returns (sigma, coveredEdges) as in line 18. The decision log is discarded here; use
    ``scene_create`` for a logged run. No normal-form check is made (this is a sub-step of
    Algorithm 3, whose entry point ``scene_create`` checks the precondition).
    """
    ctx = _Context(change, ghd, frozenset(t_star), semantics)
    return _up(ctx, node, frozenset(h_prime))

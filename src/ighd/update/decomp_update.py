"""DecompUpdate (Algorithm 5, lines 4-12) (stage S12).

Paper (p. 17), line by line:
  5  if sigma(H') is defined (stateful: an in-scene answers only once)
  6    u := sigma(H')                      -- reuse the old node, no separator search
  7    comps := [u.Bag]-components of H'
  8    u.Children := {}
  9-10 for c in comps: u.Children += DecompUpdate(c, sigma)
 11    return u
 12  return D(H', sigma)                    -- the decomposer for this subgraph

Readings (FAITHFULNESS_LEDGER):
  L-A20  the reused node's bag and cover are taken through delta: delta(B_u) = B_u & V(delta(H)),
         delta(lambda_u) = s_delta-images with deleted edges dropped.
  L-A16  if Semantics.scene_guard_check, a scene node whose delta-bag is not covered by its
         delta-cover is not reused (consistent with Alg 3 line 3; matters for up-scenes and for
         the test-only alternative reading).
  L-A21  if Semantics.scene_interface_check, a scene node may root H' only if conn(H') <= its bag;
         conn is the connection to the parent separator (A13), which Alg 5 leaves implicit.
  L-A28  if Semantics.restrict_reused_bags, the reused bag is restricted to V(H') u conn
         (default: literal, no restriction).
  L-A18  if a child fails under a reused node, H' falls back to the decomposer (the in-scene is
         already consumed, so it is not tried again).
  progress  a scene node whose (possibly restricted) bag contains no vertex of V(H') - conn is not
         reused: the recursion would reach (H', conn) again without progress (Lemma A).
  L-A19  decomposer calls receive sigma; for TopDownDecomposer the scenes are offered as candidate
         separators first (peek, never consuming), then the full search continues, so EXACT
         verdicts are unaffected (Theorem E, scene-hint corollary).

The recursion returns a ``Fragment`` (nested nodes) instead of mutating old nodes; the final GHD
is assembled once by ``fragment_to_ghd``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ighd.common.budget import Budget
from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.types import DecomposerMode, EdgeName, EdgeSet, NodeId, SearchStatus, VertexSet
from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult
from ighd.scenes.mapping import SceneKind, SceneMapping
from ighd.static.decomposer import Decomposer, DecompositionTask, DecompResult, TopDownDecomposer
from ighd.static.separation import components, connection


# ----------------------------------------------------------------------------- fragments
@dataclass
class Fragment:
    """A decomposition (sub)tree under construction. ``old_node`` is set for reused old nodes."""

    bag: VertexSet
    cover: EdgeSet
    label: str | None = None
    old_node: NodeId | None = None
    reuse_kind: str | None = None          # "in" / "out" for reused nodes
    children: list["Fragment"] = field(default_factory=list)


def fragment_from_ghd(ghd: GHD, root: NodeId) -> Fragment:
    """Convert a decomposer result (a GHD rooted at ``root``) into a Fragment (iteratively)."""
    top = Fragment(ghd.node(root).bag, ghd.node(root).cover)
    stack = [(root, top)]
    while stack:
        nid, frag = stack.pop()
        for c in ghd.children(nid):
            child = Fragment(ghd.node(c).bag, ghd.node(c).cover)
            frag.children.append(child)
            stack.append((c, child))
    return top


def fragment_to_ghd(frag: Fragment | None) -> tuple[GHD, dict[NodeId, NodeId], frozenset[NodeId]]:
    """Assemble a GHD. Returns (ghd, {old node id -> new id} for reused nodes, ids of new nodes).
    Old labels are kept for reused nodes unless the label is already taken."""
    ghd = GHD()
    reused: dict[NodeId, NodeId] = {}
    new_ids: set[NodeId] = set()
    if frag is None:
        return ghd, reused, frozenset()
    used_labels: set[str] = set()
    stack: list[tuple[Fragment, NodeId | None]] = [(frag, None)]
    while stack:
        f, parent = stack.pop()
        label = f.label if f.label is not None and f.label not in used_labels else None
        if label is not None:
            used_labels.add(label)
        nid = ghd.add_node(f.bag, f.cover, parent=parent, label=label)
        if f.old_node is not None:
            reused[f.old_node] = nid
        else:
            new_ids.add(nid)
        stack.extend((c, nid) for c in reversed(f.children))
    return ghd, reused, frozenset(new_ids)


# ----------------------------------------------------------------------------- delta helpers
def delta_bag(change: ModificationResult, old: GHD, u: NodeId) -> VertexSet:
    """delta(B_u) = B_u & V(delta(H)) (paper §5.1; L-A20)."""
    return old.node(u).bag & change.new.vertices


def delta_cover(change: ModificationResult, old: GHD, u: NodeId) -> EdgeSet:
    """delta(lambda_u) = {s_delta(e) : e in lambda_u} - {None} (paper §5.1; L-A20)."""
    return frozenset(t for e in old.node(u).cover if (t := change.s_delta.get(e)) is not None)


class SceneHintDecomposer(TopDownDecomposer):
    """TopDownDecomposer that offers scene nodes as first candidates (A19).

    For a search state (C, conn) with a scene sigma(C) = u (looked up with ``peek``, so in-scenes
    are not consumed by hints), the candidate is (delta(B_u) restricted to V(C) u conn,
    delta(lambda_u)). The search only tries it if it is a legal step, then continues exhaustively.
    """

    def __init__(self, mode: DecomposerMode, change: ModificationResult, old: GHD) -> None:
        super().__init__(mode)
        self._change = change
        self._old = old

    def _scene_candidates(self, c_key: EdgeSet, conn: VertexSet,
                          scenes: SceneMapping | None) -> list[tuple[VertexSet, EdgeSet]]:
        if scenes is None:
            return []
        entry = scenes.peek(c_key)
        if entry is None:
            return []
        new = self._change.new
        scope = new.covered_vertices(e for e in c_key if e in new.edge_names) | conn
        bag = delta_bag(self._change, self._old, entry.node) & scope
        return [(bag, delta_cover(self._change, self._old, entry.node))]


# ----------------------------------------------------------------------------- DecompUpdate
@dataclass
class _Run:
    change: ModificationResult
    old: GHD
    k: int
    sigma: SceneMapping
    decomposer: Decomposer
    budget: Budget | None
    semantics: Semantics
    calls: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _call_decomposer(run: _Run, edges: EdgeSet, conn: VertexSet) -> tuple[SearchStatus, Fragment | None]:
    """Alg 5 line 12: D(H', sigma), for the edge set H' with connection set ``conn``."""
    res: DecompResult = run.decomposer.decompose(
        DecompositionTask(run.change.new, run.k, edges=edges, conn=conn),
        scenes=run.sigma, budget=run.budget)
    run.calls.append({"edges": edges, "conn": conn, "status": res.status,
                      "scene_hits": res.stats.scene_hits, "expansions": res.stats.expansions})
    if res.status is not SearchStatus.FOUND:
        return res.status, None
    if res.ghd is None or res.root is None:                  # empty edge set
        return SearchStatus.FOUND, None
    return SearchStatus.FOUND, fragment_from_ghd(res.ghd, res.root)


def _reuse_rejection(run: _Run, u: NodeId, edges: EdgeSet, conn: VertexSet,
                     bag: VertexSet, cover: EdgeSet) -> str | None:
    """Why the scene node u may not root (H', conn), or None if it may."""
    new = run.change.new
    sem = run.semantics
    if len(cover) > run.k:
        return f"cover size {len(cover)} exceeds k={run.k}"
    if sem.scene_guard_check and not bag <= new.covered_vertices(cover):
        return f"guard: delta-bag not covered (missing {sorted(bag - new.covered_vertices(cover))}) (L-A16)"
    if sem.scene_interface_check and not conn <= bag:
        return f"interface: conn {sorted(conn - bag)} not in the bag (L-A21)"
    w = new.covered_vertices(edges) - conn
    if not bag & w:
        return "no progress: the bag contains no vertex of V(H') - conn"
    return None


def _decomp_update(run: _Run, edges: EdgeSet, conn: VertexSet) -> tuple[SearchStatus, Fragment | None]:
    new = run.change.new
    if not edges:
        return SearchStatus.FOUND, None
    entry = run.sigma.lookup(edges)                                          # line 5 (stateful)
    if entry is not None:
        u = entry.node                                                       # line 6
        bag = delta_bag(run.change, run.old, u)                              # L-A20
        if run.semantics.restrict_reused_bags:                               # L-A28
            bag = bag & (new.covered_vertices(edges) | conn)
        cover = delta_cover(run.change, run.old, u)
        why = _reuse_rejection(run, u, edges, conn, bag, cover)
        if why is None:
            children: list[Fragment] = []
            ok = True
            for c in components(new, edges, bag, run.semantics):            # lines 7-10
                status, frag = _decomp_update(run, c, connection(new, c, bag))
                if status is not SearchStatus.FOUND:
                    ok = False
                    run.notes.append(f"L-A18: child {sorted(c)} failed under reused node {u}; "
                                     f"falling back to the decomposer for {sorted(edges)}")
                    break
                if frag is not None:
                    children.append(frag)
            if ok:
                return SearchStatus.FOUND, Fragment(                         # line 11
                    bag, cover, run.old.node(u).label, u,
                    "in" if entry.kind is SceneKind.IN else "out", children)
        else:
            run.notes.append(f"scene {sorted(edges)} -> node {u} not reused: {why}")
    return _call_decomposer(run, edges, conn)                               # line 12


def decomp_update(change: ModificationResult, old_ghd: GHD, edges: EdgeSet, conn: VertexSet,
                  k: int, sigma: SceneMapping, decomposer: Decomposer,
                  budget: Budget | None = None, *, semantics: Semantics = PAPER_DEFAULT
                  ) -> DecompResult:
    """DecompUpdate(H', sigma) for H' = ``edges`` with connection set ``conn`` (Alg 5 lines 4-12).

    Returns a DecompResult over change.new. The status is authoritative for (edges, conn) only
    when the final answer came from the decomposer on that same state (always the case for a
    failure, by the A18 fallback); see ``update.pipeline`` for how the top-level verdict is used.
    """
    run = _Run(change, old_ghd, k, sigma, decomposer, budget, semantics)
    status, frag = _decomp_update(run, frozenset(edges), frozenset(conn))
    ghd, _, _ = fragment_to_ghd(frag)
    root = ghd.root if len(ghd) else None
    return DecompResult(status, ghd if status is SearchStatus.FOUND else None, root, decomposer.mode)


def run_decomp_update(change: ModificationResult, old_ghd: GHD, k: int, sigma: SceneMapping,
                      decomposer: Decomposer, budget: Budget | None, semantics: Semantics
                      ) -> tuple[SearchStatus, Fragment | None, list[dict], list[str]]:
    """Top-level call (Alg 5 line 3) used by the pipeline; also returns the call log and notes."""
    run = _Run(change, old_ghd, k, sigma, decomposer, budget, semantics)
    status, frag = _decomp_update(run, change.new.edge_names, frozenset())
    return status, frag, run.calls, run.notes

"""The top-down decomposer: Algorithm 1 made concrete (stage S7).

Search state (C, conn): C is the edge set still to be covered (a component), conn the vertices
the root bag must contain (connection to the parent; Alg 1 leaves this implicit, A13). With
W = V(C) \\ conn, a step chooses a guard set lambda <= guard pool with |lambda| <= k and
conn <= B(lambda), and a bag B with conn <= B <= B(lambda) & (W u conn) and B & W != {}; edges of
C inside B are covered here; recursion on the [B]-components C_i with conn_i = V(C_i) & B.
Soundness, completeness and termination of EXACT mode are proved in
docs/MATHEMATICAL_INVARIANTS.md §2 (Lemmas A-D, Theorem E); outputs are in replay normal form
by Lemma F.

Correspondence with Algorithm 1 (paper p. 5):
  line 2 (``for sep in Separators(H', k)``)   -> ``_candidates`` (the (B, lambda) enumeration)
  line 5 (cover with |lambda| <= k, sep <= B(cover), guards from all of E(H))
                                              -> guard sets drawn from the guard pool
  line 6 ([sep]-components)                   -> ``separation.components`` on H_aug
  lines 7-9 (recurse, reject on failure)      -> ``_solve`` on every child state, memoised
  line 11 (Reject)                            -> a memoised failure

Coverage-only edges model bag constraints (PAPER_ANALYSIS §5.4, Theorem 4.5): they must lie inside
some bag but may never appear in a cover. Guards are always drawn from the guard pool
(E(H) unless restricted; Alg 1 line 5).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING, Protocol

from ighd.common.budget import Budget
from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.errors import BudgetExhausted
from ighd.common.types import DecomposerMode, EdgeName, EdgeSet, NodeId, SearchStatus, VertexSet
from ighd.ghd.tree import GHD
from ighd.hypergraph.core import Hypergraph
from ighd.static.separation import components, connection, inside_edges

if TYPE_CHECKING:  # avoid a runtime import cycle; scenes depend on static.components
    from ighd.scenes.mapping import SceneMapping


@dataclass(frozen=True)
class DecompositionTask:
    """One call of the decomposer.

    hypergraph     H; its edges form the guard pool (unless ``guard_pool`` restricts it)
    k              width bound
    edges          edges to cover (None = all of E(H)); a component in recursive calls
    conn           vertices the root bag must contain
    coverage_only  extra named vertex sets that must be covered but may not guard (bag constraints)
    guard_pool     restrict guard edges (None = E(H))
    """

    hypergraph: Hypergraph
    k: int
    edges: EdgeSet | None = None
    conn: VertexSet = frozenset()
    coverage_only: Mapping[EdgeName, VertexSet] = field(default_factory=dict)
    guard_pool: EdgeSet | None = None


@dataclass
class DecompStats:
    expansions: int = 0
    memo_hits: int = 0
    scene_hits: int = 0
    elapsed_s: float = 0.0


@dataclass
class DecompResult:
    """FOUND: ``ghd`` is a normal-form fragment rooted at ``root`` whose root bag contains conn.
    PROVEN_NO: only from an unbudgeted EXACT search. NOT_FOUND: otherwise."""

    status: SearchStatus
    ghd: GHD | None
    root: NodeId | None
    mode: DecomposerMode
    stats: DecompStats = field(default_factory=DecompStats)


class Decomposer(Protocol):
    """Interface used by GHDUpdate (Alg 5 line 12) and by the Recompute baseline."""

    mode: DecomposerMode

    def decompose(self, task: DecompositionTask, *, scenes: "SceneMapping | None" = None,
                  budget: Budget | None = None) -> DecompResult:
        ...


# --- private search machinery -------------------------------------------------------------------

_StateKey = tuple[EdgeSet, VertexSet]
"""(C, conn): the memo key of a search state (MATHEMATICAL_INVARIANTS §2.1)."""

_Candidate = tuple[VertexSet, EdgeSet]
"""(B, lambda): a bag and its guard set."""


@dataclass(frozen=True)
class _Solution:
    """A memoised success: root bag and cover, plus the child states in components() order."""

    bag: VertexSet
    cover: EdgeSet
    children: tuple[_StateKey, ...]


_RECURSION_FLOOR = 10_000


@contextmanager
def _recursion_limit(minimum: int = _RECURSION_FLOOR) -> Iterator[None]:
    """Temporarily raise the interpreter recursion limit to max(current, ``minimum``).

    The search recursion depth is bounded by |V(C0)| + 1 (Lemma A: |W| drops at every level), so
    this only matters for large inputs; the old limit is always restored.
    """
    old = sys.getrecursionlimit()
    if old < minimum:
        sys.setrecursionlimit(minimum)
    try:
        yield
    finally:
        sys.setrecursionlimit(old)


def _sort_key(bag: VertexSet, w: VertexSet) -> tuple[int, int, tuple[str, ...]]:
    """Candidate order: descending |B & W|, then descending |B|, then the sorted tuple of B."""
    return (-len(bag & w), -len(bag), tuple(sorted(bag)))


def _lambda_key(cover: EdgeSet) -> tuple[int, tuple[str, ...]]:
    """Guard-set preference: smallest by (size, sorted names)."""
    return (len(cover), tuple(sorted(cover)))


class _Search:
    """One run of the search S(C, conn) of MATHEMATICAL_INVARIANTS §2.1 (fixed H, K, k, pool).

    The memo maps a state to a ``_Solution`` (success) or ``None`` (failure). Both are sound to
    cache because the outcome of S(C, conn) depends only on (C, conn) once H, K, k and the guard
    pool are fixed (Theorem E, first corollary). A fresh ``_Search`` is built per decompose call.
    """

    def __init__(self, owner: "TopDownDecomposer", h: Hypergraph, h_aug: Hypergraph, k: int,
                 pool: list[EdgeName], semantics: Semantics, scenes: "SceneMapping | None",
                 budget: Budget, stats: DecompStats) -> None:
        self.owner = owner
        self.h = h
        self.h_aug = h_aug
        self.k = k
        self.pool = pool  # sorted guard-pool names
        self.pool_set = frozenset(pool)
        self.semantics = semantics
        self.scenes = scenes
        self.budget = budget
        self.stats = stats
        self.exact = owner.mode is DecomposerMode.EXACT
        self.memo: dict[_StateKey, _Solution | None] = {}
        self.top: _StateKey | None = None

    # --- candidate generation -------------------------------------------------------------
    def _relevant_guards(self, scope: VertexSet) -> list[EdgeName]:
        """Pool edges meeting ``scope`` = W u conn, one per distinct restriction e & scope.

        An edge with e & scope = {} never contributes to a bag and only enlarges lambda; among
        edges with equal restriction the smallest name is kept. Neither reduction changes the
        set of candidate bags, nor (by the (size, sorted names) order) the lambda chosen for a
        bag: dropping edges shrinks lambda, and replacing an edge by a smaller-named one with
        the same restriction makes the sorted name tuple componentwise smaller.
        """
        seen: dict[VertexSet, EdgeName] = {}
        for name in self.pool:  # sorted, so the first name per restriction is the smallest
            r = self.h.edge(name) & scope
            if r and r not in seen:
                seen[r] = name
        return sorted(seen.values())

    def _enumerated_candidates(self, c: EdgeSet, conn: VertexSet) -> list[_Candidate]:
        """All (B, lambda) of §2.1 (EXACT) or the maximal B = B(lambda) & (W u conn) (HEURISTIC).

        Bags are deduplicated; each bag keeps the lambda smallest by (size, sorted names) among
        the guard sets with conn <= B <= B(lambda). Sorted by ``_sort_key``.
        """
        w = self.h_aug.covered_vertices(c) - conn
        scope = w | conn
        guards = self._relevant_guards(scope)
        restriction = {g: self.h.edge(g) & scope for g in guards}
        best: dict[VertexSet, EdgeSet] = {}
        seen_u: set[VertexSet] = set()
        for size in range(1, min(self.k, len(guards)) + 1):
            for lam in combinations(guards, size):  # lexicographic: (size, sorted names) order
                u: VertexSet = frozenset().union(*(restriction[g] for g in lam))
                if not conn <= u:
                    continue
                free = u & w
                if not free or u in seen_u:
                    continue  # B & W must be non-empty; an equal U was reached by a smaller lambda
                seen_u.add(u)
                cover = frozenset(lam)
                if self.exact:
                    items = sorted(free)
                    for mask in range(1, 1 << len(items)):
                        bag = conn | frozenset(items[i] for i in range(len(items)) if mask >> i & 1)
                        best.setdefault(bag, cover)
                else:
                    best.setdefault(u, cover)
        return sorted(best.items(), key=lambda bc: (_sort_key(bc[0], w), _lambda_key(bc[1])))

    def _conn_root_candidate(self, c: EdgeSet, conn: VertexSet) -> list[_Candidate]:
        """Top-level extension beyond §2.1: the bag B = conn, when Lemma C's hypotheses fail.

        Theorem E is stated for the top call S(E, {}). For a task with conn != {} it relies on
        Lemma C, whose hypotheses are that C is [conn]-connected, conn <= V(C) and no edge of C
        lies inside conn. If any of these fails, a good decomposition may need the root bag
        exactly conn (e.g. C = {e} with e <= conn, or conn & V(C) = {} with a guard covering conn
        but no vertex of C), which §2.1 never enumerates because B & W = {}. Adding (conn,
        smallest lambda covering conn) at the top level only restores completeness: each child
        is a [conn]-component C_i with conn_i = V(C_i) & conn, to which Lemmas C/D apply, and
        soundness is Lemma B (which never used B & W != {}). Termination: the excluded case is
        exactly the one where the only child state would equal (C, conn).
        """
        if not conn:
            return []
        comps = components(self.h_aug, c, conn, self.semantics)
        if (not inside_edges(self.h_aug, c, conn) and len(comps) == 1
                and conn <= self.h_aug.covered_vertices(c)):
            return []  # Lemma C applies; §2.1 is complete here
        for size in range(1, self.k + 1):
            for lam in combinations(self.pool, size):
                if conn <= self.h.covered_vertices(lam):
                    return [(conn, frozenset(lam))]
        return []

    def _admissible(self, bag: VertexSet, cover: EdgeSet, w: VertexSet, conn: VertexSet) -> bool:
        """Is a (possibly externally supplied) candidate a legal §2.1 step for this state?"""
        return (bool(cover) and len(cover) <= self.k and cover <= self.pool_set
                and conn <= bag and bag <= w | conn and bool(bag & w)
                and bag <= self.h.covered_vertices(cover))

    # --- the search -----------------------------------------------------------------------
    def solve(self, key: _StateKey) -> bool:
        """S(C, conn): True iff a good decomposition exists (EXACT) / was found (HEURISTIC)."""
        if key in self.memo:
            self.stats.memo_hits += 1
            return self.memo[key] is not None
        c, conn = key
        w = self.h_aug.covered_vertices(c) - conn

        tried: set[_Candidate] = set()
        for bag, cover in self.owner._scene_candidates(c, conn, self.scenes):
            bag, cover = frozenset(bag), frozenset(cover)
            if (bag, cover) in tried or not self._admissible(bag, cover, w, conn):
                continue  # scene hints are only hints: illegal ones are ignored (A19)
            tried.add((bag, cover))
            if self._try(key, bag, cover):
                self.stats.scene_hits += 1
                return True

        candidates = self._enumerated_candidates(c, conn)
        if key == self.top:
            candidates = candidates + self._conn_root_candidate(c, conn)
        for bag, cover in candidates:
            if (bag, cover) in tried:
                continue
            if self._try(key, bag, cover):
                return True
        self.memo[key] = None
        return False

    def _try(self, key: _StateKey, bag: VertexSet, cover: EdgeSet) -> bool:
        """Expand one candidate (Alg 1 lines 5-9); record the success in the memo."""
        self.budget.charge()
        self.stats.expansions += 1
        c, _ = key
        child_keys: list[_StateKey] = []
        for comp in components(self.h_aug, c, bag, self.semantics):
            child = (comp, connection(self.h_aug, comp, bag))
            if not self.solve(child):
                return False
            child_keys.append(child)
        self.memo[key] = _Solution(bag, cover, tuple(child_keys))
        return True

    def build(self, key: _StateKey) -> tuple[GHD, NodeId]:
        """Assemble the GHD from the memoised solutions (iterative, preorder, children in order)."""
        ghd = GHD()
        stack: list[tuple[_StateKey, NodeId | None]] = [(key, None)]
        root: NodeId | None = None
        while stack:
            k, parent = stack.pop()
            sol = self.memo[k]
            assert sol is not None, "build() reached a failed state"
            nid = ghd.add_node(sol.bag, sol.cover, parent=parent)
            if parent is None:
                root = nid
            stack.extend((ck, nid) for ck in reversed(sol.children))
        assert root is not None
        return ghd, root


class TopDownDecomposer:
    """Memoised top-down search in EXACT or HEURISTIC mode (IMPLEMENTATION_PLAN S7).

    Scene hints (A19) are tried first as candidate separators; the search then continues
    exhaustively, so supplying scenes never changes FOUND/PROVEN_NO in EXACT mode.
    """

    _semantics: Semantics = PAPER_DEFAULT
    """Component semantics (A3) used by the search. DecompositionTask carries no Semantics, so
    the paper default applies; a test-only subclass may override this class attribute."""

    def __init__(self, mode: DecomposerMode = DecomposerMode.EXACT) -> None:
        self.mode = mode

    def _scene_candidates(self, c_key: EdgeSet, conn: VertexSet,
                          scenes: "SceneMapping | None") -> list[tuple[VertexSet, EdgeSet]]:
        """Scene-derived (bag, cover) candidates for state (c_key, conn), tried before the normal
        enumeration (A19). Wired in a later stage; returns [] for now.

        Whatever this returns, only legal §2.1 steps are tried, and the full enumeration follows,
        so EXACT verdicts never depend on it (Theorem E, scene-hint corollary).
        """
        return []

    def decompose(self, task: DecompositionTask, *, scenes: "SceneMapping | None" = None,
                  budget: Budget | None = None) -> DecompResult:
        """Run S(C0, conn) (MATHEMATICAL_INVARIANTS §2.1) with C0 = edges u names(coverage_only).

        FOUND: a constrained GHD fragment of width <= k (Lemma B) in replay normal form (Lemma F),
        whose root bag contains ``task.conn``. PROVEN_NO: EXACT mode, search exhausted without
        hitting the budget (Theorem E). NOT_FOUND: HEURISTIC failure or budget exhaustion.
        """
        result, _ = self._decompose(task, scenes=scenes, budget=budget)
        return result

    def _decompose(self, task: DecompositionTask, *, scenes: "SceneMapping | None",
                   budget: Budget | None) -> tuple[DecompResult, bool]:
        """``decompose`` plus a flag telling whether the budget ran out."""
        started = time.perf_counter()
        stats = DecompStats()
        h = task.hypergraph

        def done(status: SearchStatus, ghd: GHD | None = None, root: NodeId | None = None,
                 exhausted: bool = False) -> tuple[DecompResult, bool]:
            stats.elapsed_s = time.perf_counter() - started
            return DecompResult(status, ghd, root, self.mode, stats), exhausted

        clash = sorted(n for n in task.coverage_only if n in h.edge_names)
        if clash:
            raise ValueError(f"coverage_only names {clash!r} clash with edge names of the hypergraph")
        edges = h.edge_names if task.edges is None else frozenset(task.edges)
        unknown = sorted(edges - h.edge_names)
        if unknown:
            raise KeyError(f"task edges {unknown!r} are not edges of the hypergraph")
        pool_names = h.edge_names if task.guard_pool is None else frozenset(task.guard_pool)
        bad_pool = sorted(pool_names - h.edge_names)
        if bad_pool:
            raise KeyError(f"guard_pool edges {bad_pool!r} are not edges of the hypergraph")
        # An empty constraint lies inside every bag; dropping it keeps H_aug a valid hypergraph.
        coverage = {n: frozenset(vs) for n, vs in task.coverage_only.items() if vs}
        conn = frozenset(task.conn)
        c0: EdgeSet = edges | frozenset(coverage)

        if not c0:
            return done(SearchStatus.FOUND, GHD(), None)
        failure = SearchStatus.PROVEN_NO if self.mode is DecomposerMode.EXACT else SearchStatus.NOT_FOUND
        if task.k < 1:
            return done(failure)

        h_aug = h.with_edges(coverage) if coverage else h
        search = _Search(self, h, h_aug, task.k, sorted(pool_names), self._semantics, scenes,
                         budget if budget is not None else Budget(), stats)
        top: _StateKey = (c0, conn)
        search.top = top
        try:
            with _recursion_limit():
                found = search.solve(top)
        except BudgetExhausted:
            return done(SearchStatus.NOT_FOUND, exhausted=True)
        if not found:
            return done(failure)
        ghd, root = search.build(top)
        return done(SearchStatus.FOUND, ghd, root)


def ghw_by_search(h: Hypergraph, mode: DecomposerMode = DecomposerMode.EXACT,
                  budget: Budget | None = None) -> tuple[int | None, GHD | None, SearchStatus]:
    """Smallest k (1, 2, ...) for which the search finds a GHD. In HEURISTIC mode the value is
    only an upper bound on ghw; a None width means the budget ran out.

    Tries k = 1, ..., |E(H)| with one shared budget (cumulative). In EXACT mode every k below the
    returned one was refuted (PROVEN_NO), so the result equals ghw(H) by Theorem E. HEURISTIC
    mode always succeeds by k = |E(H)| (lambda = E(H), B = V(H)). The empty hypergraph has
    ghw 0 and the empty GHD.
    """
    if not h.edge_names:
        return 0, GHD(), SearchStatus.FOUND
    decomposer = TopDownDecomposer(mode)
    for k in range(1, len(h.edge_names) + 1):
        result, exhausted = decomposer._decompose(DecompositionTask(h, k), scenes=None, budget=budget)
        if exhausted:
            return None, None, SearchStatus.NOT_FOUND
        if result.status is SearchStatus.FOUND:
            return k, result.ghd, SearchStatus.FOUND
    raise AssertionError("unreachable: lambda = E(H) with B = V(H) always succeeds at k = |E(H)|")

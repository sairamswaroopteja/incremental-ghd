"""Online maintenance of a minimum-width GHD under a stream of user modifications.

The user supplies the initial hypergraph and then modifications one at a time; queries may be
asked between modifications. Each modification is handled by the incremental update of the paper
(``update.pipeline.ghd_update``; PAPER strategy by default) and the session keeps

    h        the current hypergraph,
    ghd      a validated GHD of h,
    k        its width,
    exact    True iff k = ghw(h) is established by exact search (never by assumption).

The paper's update only promises a GHD of width <= k, or a proof that none exists. To report
ghw itself after every step (the user's question), the session adds two exact searches over the
whole hypergraph. Both are our additions, not the paper's, and both use the EXACT decomposer
(Theorem E), so "exact" is a proof, never a guess:

  * raise:   after PROVEN_NO (ghw(delta(H)) > k), try k+1, k+2, ... until a GHD is FOUND;
  * tighten: after UPDATED with width w, if the modification can lower ghw, try w-1, w-2, ...
             while a GHD is FOUND; the first PROVEN_NO proves the current width is ghw.
             AddVar never lowers ghw (deleting the new vertex from every bag of a GHD of
             delta(H) gives a GHD of H of no larger width), so it is not tightened.

With a time limit, a search that runs out ends with exact = False and the reason is reported;
a budgeted search never claims PROVEN_NO (invariant I10). With tightening off, k is only an
upper bound after modifications that can lower ghw, and is reported as such.

Normal form: the PAPER strategy needs a normal-form input (Def 5.1). Decomposer outputs are NF
(Lemma F) and Algorithm 5 outputs have been NF in every test, but this is checked: a non-NF
current GHD is updated with THEOREM45 (which needs no NF) and the switch is reported.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ighd.common import Budget, DecomposerMode, SearchStatus, UpdateStatus
from ighd.common.errors import IGHDError, OracleTooLargeError
from ighd.ghd import GHD, check_normal_form, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddVar
from ighd.modifications.base import Modification
from ighd.oracle import exact_ghw
from ighd.static import TopDownDecomposer
from ighd.static.decomposer import DecompositionTask
from ighd.update import Strategy, ghd_update
from ighd.update.decomp_update import delta_bag, delta_cover


@dataclass
class StepReport:
    """What happened to one modification (or to the initial build)."""

    description: str
    edge_changes: list[str]
    status: str                          # updated / proven_no / not_found / built / error
    seconds: float
    k_before: int | None
    width_after: int | None
    exact: bool
    ghw_note: str
    reused_nodes: int = 0
    old_nodes: int = 0
    decomposer_calls: int = 0
    strategy: str = ""
    notes: list[str] = field(default_factory=list)
    oracle_ghw: int | None = None
    changed_edges: list[str] = field(default_factory=list)
    """Names in the new hypergraph of edges that are new or whose vertex set changed."""
    removed_edges: list[str] = field(default_factory=list)
    reused_node_ids: list[int] = field(default_factory=list)
    """Ids, in the CURRENT decomposition, of nodes kept from the previous one (bag and cover
    equal to the delta-image of an old node). Empty when the decomposition was recomputed."""


class OnlineSession:
    """Holds (h, ghd, k, exact) and applies modifications as they arrive."""

    def __init__(self, *, strategy: Strategy = Strategy.PAPER, tighten: bool = True,
                 oracle_check: bool = False, time_limit_s: float | None = None) -> None:
        self.h: Hypergraph | None = None
        self.ghd: GHD | None = None
        self.k: int | None = None
        self.exact = False
        self.strategy = strategy
        self.tighten = tighten
        self.oracle_check = oracle_check
        self.time_limit_s = time_limit_s
        self.history: list[StepReport] = []
        self._undo: list[tuple[Hypergraph | None, GHD | None, int | None, bool]] = []
        self._decomposer = TopDownDecomposer(DecomposerMode.EXACT)

    # ------------------------------------------------------------------------------ helpers
    def _budget(self) -> Budget | None:
        return Budget(time_limit_s=self.time_limit_s).start() if self.time_limit_s else None

    def _solve(self, h: Hypergraph, k: int) -> tuple[SearchStatus, GHD | None]:
        """One EXACT search for a GHD of all of h with width <= k."""
        res = self._decomposer.decompose(DecompositionTask(h, k), budget=self._budget())
        return res.status, res.ghd

    def _oracle(self, h: Hypergraph) -> int | None:
        if not self.oracle_check:
            return None
        try:
            return exact_ghw(h)[0]
        except OracleTooLargeError:
            return None

    @property
    def built(self) -> bool:
        return self.h is not None and self.ghd is not None

    # ------------------------------------------------------------------------------ build
    def build(self, h: Hypergraph) -> StepReport:
        """Set the initial hypergraph and compute a minimum-width GHD from k = 1 upward."""
        if not h.edge_names:
            raise IGHDError("the hypergraph has no edges")
        self._undo.append((self.h, self.ghd, self.k, self.exact))
        t0 = time.perf_counter()
        ghd, k, exact, note = self._raise_from(h, 1)
        self.h, self.ghd, self.k, self.exact = h, ghd, k, exact
        rep = StepReport("initial hypergraph", [f"{len(h.edge_names)} edges, {len(h.vertices)} vertices"],
                         "built" if ghd is not None else "not_found", time.perf_counter() - t0,
                         None, k, exact, note, old_nodes=0, strategy="exact search",
                         oracle_ghw=self._oracle(h))
        self.history.append(rep)
        return rep

    def _raise_from(self, h: Hypergraph, lo: int) -> tuple[GHD | None, int | None, bool, str]:
        """Smallest k >= lo with a GHD, given that every width below lo is impossible."""
        for k in range(lo, len(h.edge_names) + 1):
            status, g = self._solve(h, k)
            if status is SearchStatus.FOUND:
                return g, k, True, f"ghw = {k} (exact: width {k} found, every smaller width refuted)"
            if status is SearchStatus.NOT_FOUND:
                return None, None, False, f"time limit reached while testing width {k}; ghw > {k - 1}"
        raise AssertionError("unreachable: width |E(H)| always succeeds")

    def _tighten(self, h: Hypergraph, g: GHD, w: int) -> tuple[GHD, int, bool, str]:
        """Lower w while a GHD of width w-1 exists; exact iff ended by PROVEN_NO (or w = 1)."""
        while w > 1:
            status, smaller = self._solve(h, w - 1)
            if status is SearchStatus.FOUND:
                g, w = smaller, w - 1
                continue
            if status is SearchStatus.PROVEN_NO:
                return g, w, True, ""
            return g, w, False, f"time limit reached while testing width {w - 1}: ghw <= {w} only"
        return g, w, True, ""

    # ------------------------------------------------------------------------------ modify
    def apply(self, mod: Modification) -> StepReport:
        """Apply one modification incrementally. Invalid modifications raise and change nothing."""
        if self.h is None:
            raise IGHDError("no hypergraph yet: give the initial hypergraph first")
        if self.ghd is None:
            raise IGHDError("the last step hit the time limit, so there is no current "
                            "decomposition: use 'rebuild' (after 'timeout off' or a larger limit)")
        h, g, k = self.h, self.ghd, self.k
        assert h is not None and g is not None and k is not None
        change = mod.apply(h)                      # raises InvalidModificationError: no change
        if not change.new.edge_names:
            raise IGHDError("this modification would leave a hypergraph without edges")
        strategy, notes = self.strategy, []
        if strategy is Strategy.PAPER and not check_normal_form(h, g).ok:
            strategy = Strategy.THEOREM45
            notes.append("current GHD is not in normal form (Def 5.1): used THEOREM45 for this step")
        old_exact = self.exact
        t0 = time.perf_counter()
        r = ghd_update(h, g, mod, k=k, strategy=strategy, delvar_fast_path=False,
                       budget=self._budget())
        notes += [n for n in r.trace.notes if not n.startswith("output in normal form")]
        if r.status is UpdateStatus.UPDATED:
            new_g, w = r.ghd, r.width
            assert new_g is not None and w is not None
            if isinstance(mod, AddVar):
                exact = old_exact               # ghw(delta(H)) >= ghw(H) = k >= w
                note = (f"ghw = {w} (exact: AddVar never lowers ghw and width {w} was found)"
                        if exact and w == k else f"ghw <= {w}")
            elif self.tighten:
                new_g, w, exact, why = self._tighten(change.new, new_g, w)
                note = why or (f"ghw = {w} (exact: width {w} found, width {w - 1} refuted)" if w > 1
                               else "ghw = 1 (exact: 1 is the smallest width of a hypergraph with edges)")
                if w < (r.width or w):
                    notes.append(f"ghw dropped: the update kept width {r.width}; an exact search "
                                 f"found width {w}")
            else:
                exact = False
                note = f"ghw <= {w} (tightening is off)"
            status = "updated"
        elif r.status is UpdateStatus.PROVEN_NO:
            new_g, w, exact, note = self._raise_from(change.new, k + 1)
            note = f"ghw rose: no GHD of width {k} exists (proof by exhaustive search); " + note
            status = "proven_no"
        else:
            new_g, w, exact = None, None, False
            note = "time limit reached: nothing found and nothing proven; decomposition unknown"
            status = "not_found"
        elapsed = time.perf_counter() - t0
        if new_g is not None:
            rep_v = validate(change.new, new_g)
            assert rep_v.ok and rep_v.width == w, rep_v.violations   # never keep an invalid GHD
        reused_ids: list[int] = []
        if new_g is not None and new_g is r.ghd:
            images = {(delta_bag(change, g, u), delta_cover(change, g, u)) for u in r.trace.reused_nodes}
            reused_ids = sorted(n.id for n in new_g if (n.bag, n.cover) in images)
        image = {t for t in change.s_delta.values() if t is not None}
        changed = sorted([e for e in change.new.edge_names if e not in image]
                         + [t for e, t in change.s_delta.items()
                            if t is not None and change.new.edge(t) != h.edge(e)])
        removed = sorted(e for e, t in change.s_delta.items() if t is None)
        self._undo.append((h, g, k, old_exact))
        self.h, self.ghd, self.k, self.exact = change.new, new_g, w, exact
        rep = StepReport(change.description, edge_changes(change), status, elapsed, k, w, exact,
                         note, reused_nodes=len(r.trace.reused_nodes), old_nodes=len(g),
                         decomposer_calls=len(r.trace.decomposer_calls), strategy=strategy.value,
                         notes=notes, oracle_ghw=self._oracle(change.new),
                         changed_edges=changed, removed_edges=removed, reused_node_ids=reused_ids)
        if rep.oracle_ghw is not None and exact and w is not None:
            assert rep.oracle_ghw == w, (rep.oracle_ghw, w)          # cross-check, never silent
        self.history.append(rep)
        return rep

    def undo(self) -> bool:
        if not self._undo:
            return False
        self.h, self.ghd, self.k, self.exact = self._undo.pop()
        self.history.append(StepReport("undo", [], "undo", 0.0, None, self.k, self.exact, ""))
        return True


def edge_changes(change) -> list[str]:
    """Human-readable edge diff: '+ e7{a,d}', '- e3{c,d}', '~ e1{a,b}->{a,b,x}'."""
    def s(xs) -> str:
        return "{" + ",".join(sorted(xs)) + "}"
    old, new = change.old, change.new
    out = []
    for e, vs in sorted(old.edges.items()):
        t = change.s_delta.get(e)
        if t is None:
            out.append(f"- {e}{s(vs)}")
        elif new.edge(t) != vs:
            out.append(f"~ {e}{s(vs)}->{s(new.edge(t))}")
    image = {t for t in change.s_delta.values() if t is not None}
    out += [f"+ {e}{s(vs)}" for e, vs in sorted(new.edges.items()) if e not in image]
    return out

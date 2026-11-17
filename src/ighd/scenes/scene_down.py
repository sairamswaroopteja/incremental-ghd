"""Algorithm 3 (SceneCreationDown) and the entry point ``scene_create`` (stage S11).

Readings (PAPER_ANALYSIS §4, FAITHFULNESS_LEDGER):
  * L-A16: line 3 (delta(B_n) <= B(delta(lambda_n)), B computed in delta(H)) is applied when
    Semantics.scene_guard_check (default). False skips it (test-only: reproduces Example 5.2 as
    printed, whose scene u2 would carry an invalid guard).
  * L-A20: delta is applied to bags and covers: delta(B_n) = B_n & V(delta(H)), delta(lambda_n) =
    the s_delta-images of lambda_n with deleted edges dropped.
  * Line 20 runs when the inner loop of lines 15-19 ends without break (no component matched the
    child); everything built in this call is discarded and Algorithm 4 is used instead.
  * L-A23: with Semantics.strict_child_matching (default) a component already matched to an
    earlier child is skipped in the inner loop, so the matching is injective (hence bijective, as
    line 7 forces |comps| = |children|); if no unmatched component fits, line 20 runs. False is the
    literal first-match rule, under which two children may recurse on the same component (the
    second recursion then overwrites the first in sigma, see SceneMapping.overwritten).
  * L-A25: the kind follows line 9 (IN iff T_n & T* != {}), not Def 5.1 (IN iff n in T*).
  * "add sigma' to sigma" (lines 13, 18) is SceneMapping.add / merge: a later entry for an existing
    key replaces the earlier one and is recorded in ``overwritten``. In particular, when a node's
    single component equals its whole H' (no edge of H' inside B_n), the child's scene for the same
    key replaces the parent's.

Every decision is logged as a SceneEvent so tests can compare traces with the paper's Example 5.2:
'A3:L3' (guard check failed; detail names the uncovered vertices), 'A3:L7' (count mismatch),
'A3:L10' / 'A3:L12' (in-/out-scene recorded), 'A3:L16' (child matched component; node = child),
'A3:L20' (child matched no component), plus 'A4:L16' / 'A4:L15' from Algorithm 4.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.errors import NotNormalFormError
from ighd.common.types import EdgeSet, NodeId
from ighd.ghd.normal_form import check_normal_form
from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult
from ighd.scenes.mapping import SceneEntry, SceneEvent, SceneKind, SceneMapping
from ighd.scenes.scene_up import _Context, _names, _up
from ighd.static.separation import components

__all__ = ["SceneEvent", "scene_create"]


@contextmanager
def _recursion_limit(depth: int) -> Iterator[None]:
    """Algorithm 3 recurses once per tree level; make room for deep trees (long paths)."""
    old = sys.getrecursionlimit()
    needed = 4 * depth + 1000
    if needed > old:
        sys.setrecursionlimit(needed)
    try:
        yield
    finally:
        if needed > old:
            sys.setrecursionlimit(old)


def _tree_depth(ghd: GHD) -> int:
    depth: dict[NodeId, int] = {}
    for x in ghd.preorder():
        p = ghd.parent(x)
        depth[x] = 0 if p is None else depth[p] + 1
    return max(depth.values(), default=0)


def _down(ctx: _Context, n: NodeId, h_prime: EdgeSet) -> SceneMapping:
    """SceneCreationDown(n, H', T*) (Algorithm 3). Returns sigma (line 21) or Alg 4's sigma."""
    new = ctx.change.new
    sem = ctx.semantics
    sigma = SceneMapping()                                                   # line 2
    sep = ctx.dbag(n)                                                        # delta(B_n)
    if sem.scene_guard_check:                                                # line 3 (L-A16)
        uncovered = sep - ctx.guard_vertices(n)
        if uncovered:
            ctx.log("A3:L3", n, h_prime,
                    f"delta(B_n) {_names(sep)} not inside B(delta(lambda_n)) {_names(ctx.guard_vertices(n))} "
                    f"(delta(lambda_n) = {_names(ctx.dcover(n))}): uncovered vertices {_names(uncovered)}; "
                    "going upward")
            return _up(ctx, n, h_prime)[0]                                   # line 4
    comps = components(new, h_prime, sep, sem)                               # lines 5-6
    kids = ctx.ghd.children(n)
    if len(comps) != len(kids):                                              # line 7
        ctx.log("A3:L7", n, h_prime,
                f"{len(comps)} [delta(B_n)]-components {[_names(c) for c in comps]} but "
                f"{len(kids)} children; going upward")
        return _up(ctx, n, h_prime)[0]                                       # line 8
    if ctx.touches_t_star[n]:                                                # line 9 (L-A25)
        kind, line = SceneKind.IN, "A3:L10"
        why = "T_n meets T*" + ("" if n in ctx.t_star else " (n itself is outside T*: ancestor, L-A25)")
    else:
        kind, line = SceneKind.OUT, "A3:L12"
        why = "T_n is disjoint from T*"
    sigma.add(h_prime, SceneEntry(n, kind, "down"))                          # line 13
    ctx.log(line, n, h_prime, f"{kind.value}-scene {_names(h_prime)} -> node {n} ({why})")
    outside = [new.covered_vertices(c) - sep for c in comps]
    used: set[int] = set()
    strict = sem.strict_child_matching
    for u in kids:                                                           # line 14
        b_u = ctx.dbag(u)
        skipped: list[int] = []
        for i, c in enumerate(comps):                                        # line 15
            if not outside[i] & b_u:                                         # line 16
                continue
            if strict and i in used:                                         # L-A23
                skipped.append(i)
                continue
            used.add(i)
            ctx.log("A3:L16", u, c,
                    f"child {u} of node {n} matches component {_names(c)} "
                    f"(shared vertices {_names(outside[i] & b_u)})")
            sigma.merge(_down(ctx, u, c))                                    # lines 17-18
            break                                                            # line 19
        else:
            note = ""
            if skipped:
                note = (" (components " + ", ".join(_names(comps[i]) for i in skipped)
                        + " would match but are already matched to an earlier child: L-A23)")
            ctx.log("A3:L20", n, h_prime,
                    f"child {u} matches no component{note}; discarding this call's scenes and going upward")
            return _up(ctx, n, h_prime)[0]                                   # line 20
    return sigma                                                             # line 21


def scene_create(change: ModificationResult, ghd: GHD, t_star: frozenset[NodeId],
                 semantics: Semantics = PAPER_DEFAULT) -> tuple[SceneMapping, list[SceneEvent]]:
    """Alg 5 line 2: SceneCreationDown(root of ghd, delta(H), T*). ``ghd`` must be in normal form
    w.r.t. change.old (NotNormalFormError otherwise).

    Returns sigma and the decision log. An empty GHD (of a hypergraph without edges) gives an empty
    sigma and no events.
    """
    report = check_normal_form(change.old, ghd, semantics)
    if not report.ok:
        raise NotNormalFormError(f"scene creation needs a normal-form GHD (Def 5.1): {report.reason}")
    if len(ghd) == 0:
        return SceneMapping(), []
    ctx = _Context(change, ghd, frozenset(t_star), semantics)
    with _recursion_limit(_tree_depth(ghd)):
        sigma = _down(ctx, ghd.root, change.new.edge_names)
    return sigma, ctx.events

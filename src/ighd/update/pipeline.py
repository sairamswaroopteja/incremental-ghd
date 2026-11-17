"""GHDUpdate driver (stage S12; paper §3.2 SearchUpdateGHD, Algorithm 5).

Pipeline (IMPLEMENTATION_PLAN S12):
  1. validate the input GHD for H; k := its width unless given; optionally verify minimality (A14)
  2. apply the modification -> ModificationResult (delta(H), s_delta, V_new)
  3. DelVar fast path (paper §3.2, §6.1) for strategies PAPER and THEOREM45
  4. Algorithm 2 -> T*; for a non-elementary delta, check condition (iii) and fall back to
     T* := whole tree if it fails (Theorem 4.5 is only proved for the six classes: L-A26, Lemma G)
  5. strategy PAPER:     scenes (Algs 3-4) + DecompUpdate (Alg 5) + decomposer
     strategy THEOREM45: delta(H)* + T*-induced constraints + constrained decomposer + glue;
                         if the constrained search fails, recompute (Thm 4.5 is only sufficient)
     strategy RECOMPUTE: the decomposer on delta(H) from scratch (the paper's "Classic")
  6. validate the output against delta(H) and check width <= k; an invalid output raises
     InvalidGHDError (under the default semantics this would be a bug; tests use it to pin the
     consequences of alternative readings)
  7. classify: UPDATED / PROVEN_NO / NOT_FOUND. PROVEN_NO is reported only when the verdict comes
     from an EXACT, unbudgeted decomposer search over all of delta(H) (invariant I10).
"""

from __future__ import annotations

import time

from ighd.common.budget import Budget
from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.errors import InvalidGHDError, OracleTooLargeError
from ighd.common.types import DecomposerMode, Minimality, NodeId, SearchStatus, UpdateStatus
from ighd.constraints.constraints import bag_constraints
from ighd.constraints.gluing import glue
from ighd.constraints.target import redecomposition_target
from ighd.ghd.normal_form import check_normal_form
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.modifications.base import Modification, ModificationResult
from ighd.mutable.minimal import minimal_mutable_subtree
from ighd.scenes.scene_down import scene_create
from ighd.static.decomposer import Decomposer, DecompositionTask, TopDownDecomposer
from ighd.update.decomp_update import (
    SceneHintDecomposer, fragment_from_ghd, fragment_to_ghd, run_decomp_update,
)
from ighd.update.delvar import delvar_update
from ighd.update.result import Strategy, UpdateResult, UpdateTrace

ELEMENTARY = frozenset({"AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq"})


def changed_or_new_edges_outside(change: ModificationResult, ghd: GHD,
                                 t_star: frozenset[NodeId]) -> list[str]:
    """Condition (iii) of MATHEMATICAL_INVARIANTS §4: names of new or changed edges of delta(H)
    that are NOT inside V* = delta(B(T*)) u V_new. Empty for the six classes (Lemma G)."""
    v_star = (ghd.bag_union(t_star) & change.new.vertices) | change.new_vertices
    preimage = {t: e for e, t in change.s_delta.items() if t is not None}
    bad = []
    for name, vs in change.new.edges.items():
        pre = preimage.get(name)
        changed = pre is None or change.old.edge(pre) != vs
        if changed and not vs <= v_star:
            bad.append(name)
    return sorted(bad)


def _check_minimality(h: Hypergraph, width: int, trace: UpdateTrace) -> Minimality:
    from ighd.oracle.ghw_dp import exact_ghw   # oracle used only for the optional precondition check
    try:
        ghw, _ = exact_ghw(h)
    except OracleTooLargeError:
        trace.notes.append("minimality not verified: instance too large for the exact oracle")
        return Minimality.ASSUMED
    return Minimality.VERIFIED if ghw == width else Minimality.REFUTED


def ghd_update(
    h: Hypergraph,
    ghd: GHD,
    modification: Modification,
    *,
    k: int | None = None,
    strategy: Strategy = Strategy.PAPER,
    decomposer: Decomposer | None = None,
    semantics: Semantics = PAPER_DEFAULT,
    verify_minimality: bool = False,
    budget: Budget | None = None,
    delvar_fast_path: bool = True,
) -> UpdateResult:
    """Solve SearchUpdateGHD for (h, modification, ghd). Never returns an unvalidated GHD.

    ``delvar_fast_path`` (L-A29): the paper's DelVar rule (delete v from every bag) is valid but
    its output need not be in normal form, which Def 5.1 requires of the NEXT update's input.
    With False, DelVar goes through Algorithm 2 and the chosen strategy like every other class.
    ``trace.notes`` always states whether the output is in normal form.
    """
    trace = UpdateTrace()
    clock = time.perf_counter()

    def lap(name: str) -> None:
        nonlocal clock
        now = time.perf_counter()
        trace.timings_s[name] = trace.timings_s.get(name, 0.0) + now - clock
        clock = now

    # 1. input
    report = validate(h, ghd)
    trace.input_validation = report
    if not report.ok:
        raise InvalidGHDError(f"the input is not a GHD of H: {[v.describe() for v in report.violations]}")
    if k is None:
        k = report.width
    elif k < report.width:
        raise ValueError(f"k={k} is below the input GHD's width {report.width}")
    minimality = _check_minimality(h, report.width, trace) if verify_minimality else Minimality.ASSUMED
    if decomposer is None:
        decomposer = TopDownDecomposer(DecomposerMode.EXACT)
    lap("input")

    # 2. modification
    change = modification.apply(h)
    trace.change = change
    lap("modification")

    def finish(status: SearchStatus, out: GHD | None) -> UpdateResult:
        if status is SearchStatus.FOUND:
            assert out is not None
            rep = validate(change.new, out)
            trace.output_validation = rep
            if not rep.ok:
                raise InvalidGHDError(
                    f"update produced an invalid GHD of delta(H) (strategy {strategy.value}, "
                    f"semantics {semantics}): {[v.describe() for v in rep.violations]}")
            if rep.width > k:
                raise InvalidGHDError(f"update produced width {rep.width} > k={k}")
            nf = check_normal_form(change.new, out, semantics).ok
            trace.notes.append(f"output in normal form: {'yes' if nf else 'no (L-A29)'}")
            lap("output-validation")
            return UpdateResult(UpdateStatus.UPDATED, out, k, rep.width, minimality, strategy, trace)
        lap("classification")
        mapped = UpdateStatus.PROVEN_NO if status is SearchStatus.PROVEN_NO else UpdateStatus.NOT_FOUND
        return UpdateResult(mapped, None, k, None, minimality, strategy, trace)

    def recompute(reason: str) -> UpdateResult:
        """Decomposer on all of delta(H) (authoritative: PROVEN_NO only if EXACT and unbudgeted)."""
        trace.notes.append(reason)
        res = decomposer.decompose(DecompositionTask(change.new, k), budget=budget)
        trace.decomposer_calls.append({"edges": change.new.edge_names, "conn": frozenset(),
                                       "status": res.status, "expansions": res.stats.expansions})
        lap("recompute")
        if res.status is SearchStatus.FOUND:
            out, _, new_ids = fragment_to_ghd(
                fragment_from_ghd(res.ghd, res.root) if res.root is not None else None)
            trace.new_nodes = new_ids
            return finish(SearchStatus.FOUND, out)
        return finish(res.status, None)

    if not change.new.edge_names:
        return finish(SearchStatus.FOUND, GHD())

    # strategy RECOMPUTE (the paper's "Classic" baseline)
    if strategy is Strategy.RECOMPUTE:
        return recompute("RECOMPUTE strategy: decomposing delta(H) from scratch")

    # 3. DelVar fast path
    if change.kind == "DelVar" and delvar_fast_path:
        out = delvar_update(change, ghd)
        trace.notes.append("DelVar fast path: vertex deleted from every bag (paper §3.2)")
        trace.reused_nodes = frozenset(ghd.node_ids())
        lap("delvar")
        return finish(SearchStatus.FOUND, out)

    # 4. Algorithm 2 (+ condition (iii) for non-elementary delta)
    alg2 = minimal_mutable_subtree(change, ghd, semantics)
    t_star = alg2.t_star
    trace.alg2_steps = alg2.steps
    if change.kind not in ELEMENTARY:
        bad = changed_or_new_edges_outside(change, ghd, t_star)
        if bad:
            trace.notes.append(f"L-A26: non-elementary delta ({change.kind}); edges {bad} escape "
                               f"delta(H)*, so T* := whole tree (Theorem 4.5 not applicable)")
            t_star = frozenset(ghd.node_ids())
    trace.t_star = t_star
    lap("algorithm2")

    # 5a. strategy THEOREM45
    if strategy is Strategy.THEOREM45:
        old_mapped = ghd.copy()
        for node in list(old_mapped):                       # L-A20: covers through s_delta
            old_mapped.set_labels(node.id, cover=frozenset(
                t for e in node.cover if (t := change.s_delta.get(e)) is not None))
        target = redecomposition_target(change, ghd, t_star)
        constraints = bag_constraints(old_mapped, t_star)
        trace.constraints = tuple(constraints)
        coverage = {f"__bag_constraint_{c.outer_node}": c.vertices for c in constraints if c.vertices}
        if target.edges:
            d = decomposer.decompose(
                DecompositionTask(Hypergraph(target.edges), k, coverage_only=coverage), budget=budget)
            trace.decomposer_calls.append({"edges": frozenset(target.edges), "conn": frozenset(),
                                           "status": d.status, "expansions": d.stats.expansions,
                                           "constraints": len(coverage)})
            lap("theorem45-decompose")
            if d.status is not SearchStatus.FOUND:
                return recompute(f"Theorem 4.5 hypothesis not met (constrained search: {d.status.value}); "
                                 "recomputing delta(H) to classify")
            d_star = d.ghd
        else:
            d_star = GHD()
        out = glue(d_star, old_mapped, constraints)
        reused_labels = {old_mapped.node(n).label for n in old_mapped.node_ids() if n not in t_star}
        trace.reused_nodes = frozenset(n for n in ghd.node_ids() if n not in t_star)
        trace.new_nodes = frozenset(n.id for n in out if n.label not in reused_labels or n.label is None)
        lap("theorem45-glue")
        return finish(SearchStatus.FOUND, out)

    # 5b. strategy PAPER: scenes (Algs 3-4) + DecompUpdate (Alg 5)
    sigma, events = scene_create(change, ghd, t_star, semantics)
    trace.scenes = sigma
    trace.scene_events = tuple(events)
    lap("scenes")
    worker = (SceneHintDecomposer(decomposer.mode, change, ghd)
              if type(decomposer) is TopDownDecomposer else decomposer)
    status, frag, calls, notes = run_decomp_update(change, ghd, k, sigma, worker, budget, semantics)
    trace.decomposer_calls.extend(calls)
    trace.notes.extend(notes)
    lap("decomp-update")
    if status is not SearchStatus.FOUND:
        # A18 at the top level always ends in the decomposer on (E(delta(H)), {}), so the status is
        # that search's verdict over all of delta(H).
        return finish(status, None)
    out, reused, new_ids = fragment_to_ghd(frag)
    trace.reused_nodes = frozenset(reused)
    trace.new_nodes = new_ids
    return finish(SearchStatus.FOUND, out)

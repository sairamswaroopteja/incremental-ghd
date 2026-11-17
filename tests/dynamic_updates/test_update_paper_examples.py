"""S12, Level 3/4: SearchUpdateGHD end to end on the paper's examples and the guide's cases.

Every output is re-validated here with the independent validator (the pipeline validates too).
Expected statuses come from the exact oracle (tests/paper_examples/test_expected_t_star_oracle.py):
all cases keep their width except AddVar(h) on the join tree of H_P (ghw 1 -> 2: PROVEN_NO).
"""

from __future__ import annotations

import pytest

import ighd.modifications as mods
from ighd.common import Budget, DecomposerMode, Minimality, UpdateStatus
from ighd.common.config import Semantics, UpSceneKey
from ighd.common.errors import InvalidGHDError, NotNormalFormError
from ighd.ghd import GHD, check_normal_form, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelVar, ModificationSequence
from ighd.oracle import exact_ghw
from ighd.static import TopDownDecomposer
from ighd.update import Strategy, ghd_update
from tests.fixtures import expected
from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, H_P2, H_PP

CASES = expected.T_STAR_CASES
IDS = [c[0] for c in CASES]


def labels(ghd: GHD, ids) -> set[str]:
    return {ghd.node(i).label for i in ids}


@pytest.mark.parametrize("strategy", list(Strategy))
@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_every_case_every_strategy(case, strategy) -> None:
    case_id, h, spec, (cls, kwargs), want_t_star, _ = case
    hyper, ghd = Hypergraph(h), GHD.from_spec(spec)
    mod = getattr(mods, cls)(**kwargs)
    r = ghd_update(hyper, ghd, mod, strategy=strategy, verify_minimality=True)
    assert r.minimality is Minimality.VERIFIED        # SearchUpdateGHD precondition holds
    new = mod.apply(hyper).new
    if case_id == "addvar_h_jointree":
        assert r.status is UpdateStatus.PROVEN_NO and r.ghd is None
        assert exact_ghw(new)[0] > r.k
        return
    assert r.status is UpdateStatus.UPDATED
    rep = validate(new, r.ghd)
    assert rep.ok, rep.violations
    assert rep.width <= r.k == ghd.width()
    if strategy is Strategy.PAPER and cls != "DelVar":
        assert labels(ghd, r.trace.t_star) == want_t_star


def test_example_43_52_paper_strategy_trace() -> None:
    """Paper Ex. 4.3/5.2 through Algorithm 5: u1 (in-scene) and u3 (out-scene) are reused with
    their exact bags and covers; u2 is not reused because its renamed guard lost w7 (Alg 3 L3)."""
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    r = ghd_update(h, g, DelConstr("w7"))
    assert r.status is UpdateStatus.UPDATED and r.width == 2
    assert labels(g, r.trace.t_star) == {"u1", "u2"}
    assert labels(g, r.trace.reused_nodes) >= {"u1", "u3"}
    assert "u2" not in labels(g, r.trace.reused_nodes)
    assert any(e.line == "A3:L3" and g.node(e.node).label == "u2" for e in r.trace.scene_events)
    out = r.ghd
    for lab in ("u1", "u3"):
        assert out.node(out.by_label(lab)).bag == g.node(g.by_label(lab)).bag
        assert out.node(out.by_label(lab)).cover == g.node(g.by_label(lab)).cover
    assert check_normal_form(Hypergraph(H_PP), out).ok


def test_example_43_theorem45_strategy() -> None:
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    r = ghd_update(h, g, DelConstr("w7"), strategy=Strategy.THEOREM45)
    assert r.status is UpdateStatus.UPDATED
    got = {g.node(c.outer_node).label: c.vertices for c in r.trace.constraints}
    assert got == expected.EX43_CONSTRAINTS
    for lab in ("u3", "u4"):   # Lemma 4.2: outer trees kept verbatim
        assert r.ghd.node(r.ghd.by_label(lab)).bag == g.node(g.by_label(lab)).bag


def test_addconstr_already_covered_reuses_everything() -> None:
    """w7 = {c, i} lies inside t1's bag {c,e,h,i,k}: the old GHD is still valid for H_P2, and the
    scene machinery discovers it: every old node is reused and the decomposer is never called."""
    h, g = Hypergraph(H_PP), GHD.from_spec(G_PRIME_SPEC)
    r = ghd_update(h, g, AddConstr("w7", frozenset("ci")))
    assert r.status is UpdateStatus.UPDATED
    assert labels(g, r.trace.reused_nodes) == {"t1", "t2", "t3", "t4"}
    assert r.trace.decomposer_calls == []


def test_delvar_fast_path_and_non_optimality() -> None:
    """Paper §3.2: delete h from every bag. Width stays 2 although ghw(H_P) = 1 (allowed: the
    output only needs width <= ghw(H)). The tree is unchanged."""
    h, g = Hypergraph(H_PP), GHD.from_spec(G_PRIME_SPEC)
    r = ghd_update(h, g, DelVar("h"))
    assert r.status is UpdateStatus.UPDATED and r.width == 2
    assert exact_ghw(DelVar("h").apply(h).new)[0] == 1
    assert [n.bag for n in r.ghd] == [n.bag - {"h"} for n in g]


@pytest.mark.paper_discrepancy
def test_a29_delvar_rule_output_is_not_normal_form_and_breaks_chaining() -> None:
    """L-A29 (S15 pin; the smallest case found by a seeded search over random DelVar updates).
    H = {e0: ae, e1: ab}, GHD root {a,b} with child {a,e}. The paper's DelVar rule deletes e from
    every bag: the child becomes {a}. That is a valid GHD of width 1, but not in normal form:
    e0' = {a} lies inside the root bag, so the root has no [B]-component (A3) for its child to
    match. Def 5.1 needs NF, so the NEXT update with scenes is refused. Algorithms 2-5 (fast path
    off) return an NF GHD of the same hypergraph."""
    h = Hypergraph({"e0": "ae", "e1": "ab"})
    g = GHD.from_spec({"root": "r", "nodes": {"r": ("ab", ("e1",)), "c": ("ae", ("e0",))},
                       "children": {"r": ["c"]}})
    new = DelVar("e").apply(h).new
    r = ghd_update(h, g, DelVar("e"))
    assert r.status is UpdateStatus.UPDATED and validate(new, r.ghd).ok
    assert not check_normal_form(new, r.ghd).ok
    assert "output in normal form: no (L-A29)" in r.trace.notes
    with pytest.raises(NotNormalFormError):
        ghd_update(new, r.ghd, AddConstr("f", frozenset("ab")))       # the next update
    r2 = ghd_update(h, g, DelVar("e"), delvar_fast_path=False)
    assert r2.status is UpdateStatus.UPDATED and check_normal_form(new, r2.ghd).ok


def test_minimality_refuted_is_reported_and_answers_stay_exact() -> None:
    """Minimality.REFUTED: the input GHD has width 2 but ghw(H) = 1. The update still answers
    for k = 2 (the input width), exactly: UPDATED iff ghw(delta(H)) <= 2 (here 1)."""
    h = Hypergraph({"e1": "ab", "e2": "bc"})
    g = GHD.from_spec({"root": "r", "nodes": {"r": ("abc", ("e1", "e2"))}, "children": {}})
    assert exact_ghw(h)[0] == 1
    for strategy in Strategy:
        r = ghd_update(h, g, AddVar("z", frozenset({"e1"})), strategy=strategy,
                       verify_minimality=True)
        assert r.minimality is Minimality.REFUTED, strategy
        assert r.k == 2 and r.status is UpdateStatus.UPDATED, strategy
        assert validate(AddVar("z", frozenset({"e1"})).apply(h).new, r.ghd).ok
    assert ghd_update(h, g, AddVar("z", frozenset({"e1"}))).minimality is Minimality.ASSUMED


def test_delvar_without_fast_path_is_normal_form() -> None:
    h, g = Hypergraph(H_PP), GHD.from_spec(G_PRIME_SPEC)
    r = ghd_update(h, g, DelVar("h"), delvar_fast_path=False)
    assert r.status is UpdateStatus.UPDATED
    assert check_normal_form(DelVar("h").apply(h).new, r.ghd).ok
    assert "output in normal form: yes" in r.trace.notes


@pytest.mark.parametrize("strategy", [Strategy.PAPER, Strategy.THEOREM45])
def test_empty_t_star_fresh_edge(strategy) -> None:
    """A12: an edge of fresh vertices is invisible from every old bag, so T* is empty; the root
    scene is keyed by all of E(delta(H)) and the fresh edge becomes its own component."""
    h, g = Hypergraph(H_PP), GHD.from_spec(G_PRIME_SPEC)
    r = ghd_update(h, g, AddConstr("w9", frozenset("xy")), strategy=strategy)
    assert r.trace.t_star == frozenset()
    assert r.status is UpdateStatus.UPDATED
    assert validate(Hypergraph({**H_PP, "w9": "xy"}), r.ghd).ok


@pytest.mark.paper_discrepancy
@pytest.mark.parametrize("strategy", [Strategy.PAPER, Strategy.THEOREM45])
def test_a26_composed_modification_falls_back(strategy) -> None:
    """L-A26: AddVar(z into e1) then AddEq({z,c} -> c) adds the EXISTING vertex c to e1.
    Algorithm 2 alone gives T* = {u2}, for which Theorem 4.5's gluing fails (S10 pins that);
    the pipeline detects condition (iii) and uses the whole tree, so the update succeeds."""
    h = Hypergraph({"e1": "ab", "e2": "bc"})
    g = GHD.from_spec({"root": "u1", "nodes": {"u1": ("ab", ("e1",)), "u2": ("bc", ("e2",))},
                       "children": {"u1": ["u2"]}})
    seq = ModificationSequence((AddVar("z", frozenset({"e1"})), AddEq(frozenset({"z", "c"}), "c")))
    r = ghd_update(h, g, seq, strategy=strategy)
    assert any("L-A26" in n for n in r.trace.notes)
    assert r.trace.t_star == frozenset(g.node_ids())
    assert r.status is UpdateStatus.UPDATED
    assert validate(seq.apply(h).new, r.ghd).ok


@pytest.mark.paper_discrepancy
def test_a16_paper_printed_sigma_yields_invalid_ghd() -> None:
    """L-A16 end to end: skipping Alg 3 line 3 reproduces Example 5.2's printed sigma; DecompUpdate
    then reuses u2 with bag {c,e,i,k} and the renamed guard {w3}: c is unguarded."""
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    with pytest.raises(InvalidGHDError, match="UnguardedVertices"):
        ghd_update(h, g, DelConstr("w7"), semantics=Semantics(scene_guard_check=False))


@pytest.mark.paper_discrepancy
def test_a28_restricting_reused_bags_masks_a16() -> None:
    """Restricting the reused bag to V(H') u conn (L-A28, not in the paper) happens to remove c
    from u2's bag, so even the printed sigma then gives a valid GHD. Recorded, not relied upon."""
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    r = ghd_update(h, g, DelConstr("w7"),
                   semantics=Semantics(scene_guard_check=False, restrict_reused_bags=True))
    assert r.status is UpdateStatus.UPDATED


@pytest.mark.paper_discrepancy
def test_a17_a21_literal_up_key_needs_interface_check() -> None:
    """L-A17/L-A21: with the literal up-scene key, sigma({w3,w6}) = u4. With the interface check
    (default) the scene is rejected (conn {e} not in {j,k,l}) and the result is valid; without it,
    u4 roots {w3,w6} and vertex e becomes disconnected."""
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    ok = ghd_update(h, g, DelConstr("w7"), semantics=Semantics(up_scene_key=UpSceneKey.LITERAL_H_PRIME))
    assert ok.status is UpdateStatus.UPDATED
    assert any("interface" in n for n in ok.trace.notes)
    with pytest.raises(InvalidGHDError, match="DisconnectedVertex"):
        ghd_update(h, g, DelConstr("w7"), semantics=Semantics(
            up_scene_key=UpSceneKey.LITERAL_H_PRIME, scene_interface_check=False))


@pytest.mark.paper_discrepancy
def test_a21_interface_check_is_required_by_the_paper_algorithm() -> None:
    """L-A21, under the DEFAULT readings (found by randomized testing in S12, 37/3000 updates):
    H = path ce - cf - df with the width-1 chain GHD; AddConstr {d,e,f} closes a cycle, so
    ghw rises to 2 and the right answer is PROVEN_NO. Literal Algorithm 5 (no interface check)
    reuses a scene node whose bag misses the connection vertex e and returns a width-1 'GHD' in
    which e is disconnected: a wrong YES. With the check (default) the answer is correct."""
    h = Hypergraph({"w0": "ce", "w1": "df", "w2": "cf"})
    g = GHD.from_spec({"root": "n0", "nodes": {"n0": ("ce", ("w0",)), "n1": ("cf", ("w2",)),
                                               "n2": ("df", ("w1",))},
                       "children": {"n0": ["n1"], "n1": ["n2"]}})
    mod = AddConstr("wnew", frozenset("def"))
    assert exact_ghw(mod.apply(h).new)[0] == 2
    r = ghd_update(h, g, mod)
    assert r.status is UpdateStatus.PROVEN_NO
    assert any("interface" in n for n in r.trace.notes)
    with pytest.raises(InvalidGHDError, match="DisconnectedVertex"):
        ghd_update(h, g, mod, semantics=Semantics(scene_interface_check=False))


def test_a18_fallback_after_child_failure() -> None:
    """L-A18 (found by randomized testing, 159/3000 updates): the root scene is reused, a child
    component then fails, and the whole edge set falls back to the decomposer, whose verdict is
    authoritative (here PROVEN_NO, confirmed by the oracle)."""
    h = Hypergraph({"w0": "ac", "w1": "acd", "w2": "bcd", "w3": "bcd", "w4": "acd"})
    g = GHD.from_spec({"root": "n0", "nodes": {"n0": ("acd", ("w1",)), "n1": ("bcd", ("w2",))},
                       "children": {"n0": ["n1"]}})
    mod = AddConstr("wnew", frozenset("abd"))
    r = ghd_update(h, g, mod)
    assert any("L-A18" in n for n in r.trace.notes)
    assert r.status is UpdateStatus.PROVEN_NO
    assert exact_ghw(mod.apply(h).new)[0] > r.k


def test_heuristic_never_proves_no_and_budget_never_proves_no() -> None:
    case = next(c for c in CASES if c[0] == "addvar_h_jointree")
    hyper, ghd = Hypergraph(case[1]), GHD.from_spec(case[2])
    mod = AddVar("h", frozenset({"w2", "w5"}))
    r = ghd_update(hyper, ghd, mod, decomposer=TopDownDecomposer(DecomposerMode.HEURISTIC))
    assert r.status is UpdateStatus.NOT_FOUND
    r = ghd_update(hyper, ghd, mod, budget=Budget(max_expansions=1))
    assert r.status is UpdateStatus.NOT_FOUND


def test_input_checks() -> None:
    h, g = Hypergraph(H_PP), GHD.from_spec(G_PRIME_SPEC)
    with pytest.raises(InvalidGHDError):                             # Fig. 6(a) guards with w7,
        ghd_update(h, GHD.from_spec(G2_SPEC), DelConstr("w1"))      # which H_P' does not have
    with pytest.raises(ValueError):
        ghd_update(h, g, DelConstr("w1"), k=1)                       # k below the input width
    spec = {**G_PRIME_SPEC, "nodes": {**G_PRIME_SPEC["nodes"], "x": ("k", ("w6",))},
            "children": {**G_PRIME_SPEC["children"], "t4": ["x"], "x": []}}
    non_nf = GHD.from_spec(spec)
    assert validate(h, non_nf).ok and not check_normal_form(h, non_nf).ok
    with pytest.raises(NotNormalFormError):
        ghd_update(h, non_nf, DelConstr("w1"))                       # Def 5.1 precondition
    r = ghd_update(h, non_nf, DelConstr("w1"), strategy=Strategy.THEOREM45)   # needs no NF
    assert r.status is UpdateStatus.UPDATED

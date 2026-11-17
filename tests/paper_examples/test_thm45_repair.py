"""S10: Theorem 4.5 on paper Example 4.3 and on every T_STAR_CASES fixture.

Pipeline (paper §4.1): T* := Algorithm 2; delta(H)* := ``redecomposition_target`` (D19, A11);
C_i := ``bag_constraints`` (D20); D* := the EXACT top-down decomposer on Hypergraph(delta(H)*.edges)
with the C_i as coverage-only sets (Theorem 4.5's hypothesis); result := ``glue``.

Why covers of D* are valid covers in delta(H): D* is built on the restricted edges e & V*, which
keep their delta(H) names. A D* node with cover lambda satisfies B <= U_{e in lambda} (e & V*), and
e & V* <= e, so the same names guard B in delta(H) (condition (3)); coverage of a restricted edge
is irrelevant for delta(H) except for the full edges, which D* covers whole.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from ighd import modifications as mods
from ighd.common.errors import InvalidGHDError
from ighd.common.types import DecomposerMode, NodeId, SearchStatus
from ighd.constraints import (
    BagConstraint,
    RedecompositionTarget,
    bag_constraints,
    glue,
    redecomposition_target,
)
from ighd.ghd import GHD, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import DelConstr, ModificationResult
from ighd.mutable import minimal_mutable_subtree, mutable_conditions
from ighd.oracle import exact_ghw
from ighd.static import DecompositionTask, DecompResult, TopDownDecomposer
from tests.fixtures.expected import EX43_CONSTRAINTS, EX43_REPAIRED_SPEC, T_STAR_CASES
from tests.fixtures.paper import G2_SPEC, H_P2, H_PP

fs = frozenset


# --------------------------------------------------------------------------- shared helpers
@dataclass(frozen=True)
class Thm45Run:
    t_star: frozenset[NodeId]
    target: RedecompositionTarget
    constraints: list[BagConstraint]
    decomp: DecompResult
    glued: GHD | None


def coverage_name(c: BagConstraint) -> str:
    """Name of the coverage-only set for constraint C_i (never clashes with edge names here)."""
    return f"__C_{c.outer_node}"


def thm45_pipeline(change: ModificationResult, old: GHD, k: int) -> Thm45Run:
    """Algorithm 2 -> delta(H)* -> T*-induced constraints -> constrained EXACT search -> glue."""
    t_star = minimal_mutable_subtree(change, old).t_star
    target = redecomposition_target(change, old, t_star)
    constraints = bag_constraints(old, t_star)
    task = DecompositionTask(Hypergraph(target.edges), k,
                             coverage_only={coverage_name(c): c.vertices for c in constraints})
    res = TopDownDecomposer(DecomposerMode.EXACT).decompose(task)
    glued = glue(res.ghd, old, constraints) if res.status is SearchStatus.FOUND else None
    assert res.status is not SearchStatus.NOT_FOUND  # EXACT and unbudgeted (I10)
    return Thm45Run(t_star, target, constraints, res, glued)


def undirected(g: GHD) -> tuple[frozenset[frozenset[str]], dict[str, tuple[frozenset[str], frozenset[str]]]]:
    """(label-level tree edges, label -> (bag, cover)): the unrooted structure of a labelled GHD."""
    def lbl(u: NodeId) -> str:
        n = g.node(u).label
        return n if n is not None else f"#{u}"
    edges = fs(fs({lbl(u), lbl(p)}) for u in g.node_ids() if (p := g.parent(u)) is not None)
    return edges, {lbl(u): (g.node(u).bag, g.node(u).cover) for u in g.node_ids()}


def assert_outer_trees_kept(old: GHD, glued: GHD, constraints: list[BagConstraint]) -> None:
    """Lemma 4.2 reuse: every outer node keeps its exact bag and cover (found by label), and the
    tree edges inside every outer tree are kept."""
    for c in constraints:
        for u in c.outer_tree:
            lbl = old.node(u).label
            assert lbl is not None, "test inputs must be fully labelled"
            v = glued.by_label(lbl)
            assert glued.node(v).bag == old.node(u).bag, lbl
            assert glued.node(v).cover == old.node(u).cover, lbl
        sub_old, _ = undirected(old.extract(c.outer_tree, root=c.outer_node))
        glued_edges, _ = undirected(glued)
        assert sub_old <= glued_edges


def assert_lemma42(change: ModificationResult, old: GHD, constraints: list[BagConstraint]) -> None:
    """Lemma 4.2 / I4: each outer tree T', labels unchanged, is a GHD of delta(H)[T'].

    A cover edge whose restriction to B(T') is empty does not exist in the induced hypergraph
    (Hypergraph.induced drops empty restrictions, A1), so such cover edges are dropped before
    validating; they guard nothing inside B(T')."""
    for c in constraints:
        t = old.extract(c.outer_tree, root=c.outer_node)
        induced = Hypergraph(change.new.induced(old.bag_union(c.outer_tree)))
        for u in t.node_ids():
            t.set_labels(u, cover=t.node(u).cover & induced.edge_names)
        rep = validate(induced, t)
        assert rep.ok, (sorted(c.outer_tree), rep.violations)


def build_change(h: Mapping[str, frozenset[str]], mod: tuple[str, dict]) -> ModificationResult:
    cls_name, kwargs = mod
    return getattr(mods, cls_name)(**kwargs).apply(Hypergraph(h))


def _labels(g: GHD, nodes: frozenset[NodeId]) -> frozenset[str]:
    return fs(str(g.node(u).label) for u in nodes)


# --------------------------------------------------------------------------- Example 4.3
def _ex43() -> tuple[ModificationResult, GHD, frozenset[NodeId]]:
    change = DelConstr("w7").apply(Hypergraph(H_P2))
    old = GHD.from_spec(G2_SPEC)
    t_star = minimal_mutable_subtree(change, old).t_star
    assert _labels(old, t_star) == fs({"u1", "u2"})
    return change, old, t_star


def test_ex43_target() -> None:
    change, old, t_star = _ex43()
    target = redecomposition_target(change, old, t_star)
    assert target.vertices == fs("abcehik")
    assert dict(target.edges) == {"w1": fs("abc"), "w5": fs("ceh"), "w3": fs("eik"),
                                  "w4": fs("a"), "w2": fs("h"), "w6": fs("k")}
    assert target.full_edges == fs({"w1", "w3", "w5"})


def test_ex43_constraints() -> None:
    change, old, t_star = _ex43()
    cs = bag_constraints(old, t_star)
    assert {old.node(c.outer_node).label: c.vertices for c in cs} == EX43_CONSTRAINTS
    inner = {old.node(c.outer_node).label: old.node(c.inner_neighbor).label for c in cs}
    assert inner == {"u3": "u1", "u4": "u2"}
    assert [c.outer_node for c in cs] == sorted(c.outer_node for c in cs)
    for c in cs:
        assert c.outer_tree == fs({c.outer_node})


def test_ex43_hand_built_d_star_gives_repaired_spec() -> None:
    change, old, t_star = _ex43()
    cs = bag_constraints(old, t_star)
    d_star = GHD.from_spec({"root": "n1",
                            "nodes": {"n1": ("abceh", ("w1", "w5")), "n2": ("eik", ("w3",))},
                            "children": {"n1": ["n2"]}})
    glued = glue(d_star, old, cs)
    assert undirected(glued) == undirected(GHD.from_spec(EX43_REPAIRED_SPEC))
    rep = validate(change.new, glued)
    assert rep.ok, rep.violations
    assert rep.width == 2 and change.new == Hypergraph(H_PP)
    assert_outer_trees_kept(old, glued, cs)
    # inputs are not modified
    assert len(d_star) == 2 and undirected(old) == undirected(GHD.from_spec(G2_SPEC))


def test_ex43_full_pipeline() -> None:
    change, old, _ = _ex43()
    run = thm45_pipeline(change, old, k=2)
    assert run.decomp.status is SearchStatus.FOUND
    assert run.glued is not None
    rep = validate(change.new, run.glued)
    assert rep.ok, rep.violations
    assert rep.width <= 2
    assert_outer_trees_kept(old, run.glued, run.constraints)


def test_ex43_glue_rejects_unsatisfied_constraint() -> None:
    change, old, t_star = _ex43()
    cs = bag_constraints(old, t_star)
    d_star = GHD.from_spec({"root": "n1", "nodes": {"n1": ("abceh", ("w1", "w5"))}, "children": {}})
    with pytest.raises(InvalidGHDError, match=r"\['k'\]"):  # C_u4 = {k} lies in no bag
        glue(d_star, old, cs)


# --------------------------------------------------------------------------- every fixture case
CASE_IDS = [c[0] for c in T_STAR_CASES]


@pytest.mark.parametrize("case", T_STAR_CASES, ids=CASE_IDS)
def test_thm45_pipeline_on_fixture(case: tuple) -> None:
    cid, h, spec, mod, expected_t_star, _prov = case
    change = build_change(h, mod)
    old = GHD.from_spec(spec)
    k = old.width()
    run = thm45_pipeline(change, old, k)
    assert _labels(old, run.t_star) == expected_t_star
    # every constraint is a subset of V(delta(H)*) (D20)
    for c in run.constraints:
        assert c.vertices <= run.target.vertices
    assert_lemma42(change, old, run.constraints)
    if cid == "addvar_h_jointree":
        # k = 1 and delta closes the cycle a-c-e-h-f: no width-1 GHD of delta(H) exists at all.
        assert run.decomp.status is SearchStatus.PROVEN_NO
        assert exact_ghw(change.new)[0] == 2 > k
        return
    assert run.decomp.status is SearchStatus.FOUND
    assert run.glued is not None and run.decomp.ghd is not None
    rep = validate(change.new, run.glued)
    assert rep.ok, (cid, rep.violations)
    assert rep.width <= k
    assert_outer_trees_kept(old, run.glued, run.constraints)
    for c in run.constraints:
        assert any(c.vertices <= n.bag for n in run.decomp.ghd), (cid, c)


# --------------------------------------------------------------------------- paper discrepancy
@pytest.mark.paper_discrepancy
def test_thm45_fails_for_a_general_modification() -> None:
    """Def 3.1 allows any function delta, but Theorem 4.5 (with the D19/A11 reading of
    delta(H)*) fails for "extend an edge by an existing vertex": H = {e1: ab, e2: bc},
    T = u1({a,b}) - u2({b,c}), delta: e1 := {a,b,c}. T* = {u2} is delta-mutable (H[{a,b}] =
    delta(H)[{a,b}] edgewise, no new vertex) and Algorithm 2 returns it; delta(H)* = {e1: bc,
    e2: bc}, C = {b}; D* = ({b,c}, {e1}) satisfies C, but the glued tree covers delta(e1) = abc in
    no bag. The six classes of Defs 3.2-3.4 cannot produce this (an edge of delta(H) changed only by
    vertices of B(T*) minus B(T minus T*) would violate (i) or contain a new vertex), so the update
    framework stays correct for them; the random S10 run confirms it empirically."""
    old_h = Hypergraph({"e1": "ab", "e2": "bc"})
    new_h = Hypergraph({"e1": "abc", "e2": "bc"})
    change = ModificationResult(kind="ExtendEdge", old=old_h, new=new_h,
                                s_delta={"e1": "e1", "e2": "e2"}, new_edges=fs(),
                                new_vertices=fs(), removed_vertices=fs(),
                                description="extend e1 by the existing vertex c")
    old = GHD.from_spec({"root": "u1", "nodes": {"u1": ("ab", ("e1",)), "u2": ("bc", ("e2",))},
                         "children": {"u1": ["u2"]}})
    t_star = fs({old.by_label("u2")})
    assert mutable_conditions(change, old, t_star).mutable
    run = thm45_pipeline(change, old, k=1)
    assert run.t_star == t_star
    assert run.decomp.status is SearchStatus.FOUND and run.glued is not None
    rep = validate(change.new, run.glued)
    assert not rep.ok  # e1 = {a,b,c} is covered nowhere
    assert any(getattr(v, "edge", None) == "e1" for v in rep.violations)

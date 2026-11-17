"""S10 unit tests for Theorem 4.5 gluing (``ighd.constraints.glue``)."""

from __future__ import annotations

import pytest

from ighd.common.errors import InvalidGHDError
from ighd.common.types import DecomposerMode, SearchStatus
from ighd.constraints import BagConstraint, bag_constraints, glue, redecomposition_target
from ighd.ghd import GHD, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, DelVar
from ighd.mutable import minimal_mutable_subtree
from ighd.static import DecompositionTask, TopDownDecomposer
from tests.fixtures.paper import G_PRIME_SPEC, H_PP
from tests.paper_examples.test_thm45_repair import assert_outer_trees_kept, undirected

fs = frozenset


def test_empty_t_star_decompose_and_glue_attaches_whole_old_tree() -> None:
    change = AddConstr("w9", fs({"x", "y"})).apply(Hypergraph(H_PP))
    old = GHD.from_spec(G_PRIME_SPEC)
    t_star = minimal_mutable_subtree(change, old).t_star
    assert t_star == fs()
    target = redecomposition_target(change, old, t_star)
    cs = bag_constraints(old, t_star)
    res = TopDownDecomposer(DecomposerMode.EXACT).decompose(
        DecompositionTask(Hypergraph(target.edges), 2,
                          coverage_only={f"__C_{c.outer_node}": c.vertices for c in cs}))
    assert res.status is SearchStatus.FOUND and res.ghd is not None
    glued = glue(res.ghd, old, cs)
    assert len(glued) == len(old) + len(res.ghd)
    rep = validate(change.new, glued)
    assert rep.ok, rep.violations
    assert rep.width == 2
    assert_outer_trees_kept(old, glued, cs)
    # the old tree hangs below D*'s smallest-id node by one edge at its old root
    t1 = glued.by_label("t1")
    assert glued.parent(t1) == min(res.ghd.node_ids())


def test_empty_d_star_with_pseudo_constraint_returns_old_tree() -> None:
    old = GHD.from_spec(G_PRIME_SPEC)
    (c,) = bag_constraints(old, [])
    out = glue(GHD(), old, [c])
    assert out is not old
    assert out.root == old.root
    assert undirected(out) == undirected(old)
    assert out.to_spec() == old.to_spec()


def test_empty_d_star_without_constraints_is_empty() -> None:
    assert len(glue(GHD(), GHD.from_spec(G_PRIME_SPEC), [])) == 0


def test_empty_d_star_with_nonempty_constraint_rejected() -> None:
    old = GHD.from_spec(G_PRIME_SPEC)
    cs = bag_constraints(old, [old.by_label("t4")])  # C = {k}
    with pytest.raises(InvalidGHDError, match="D\\* is empty"):
        glue(GHD(), old, cs)


def test_empty_d_star_with_several_empty_constraints_joins_disjoint_trees() -> None:
    # H = {e1: ab, e2: v, e3: cd}; T = u1(ab) - u2(v) - u3(cd). DelVar v deletes e2 (A6); T* = {u2},
    # V* = {} so D* is empty, and the two outer trees (vertex-disjoint) are joined directly.
    h = Hypergraph({"e1": "ab", "e2": "v", "e3": "cd"})
    old = GHD.from_spec({"root": "u1",
                         "nodes": {"u1": ("ab", ("e1",)), "u2": ("v", ("e2",)), "u3": ("cd", ("e3",))},
                         "children": {"u1": ["u2"], "u2": ["u3"]}})
    change = DelVar("v").apply(h)
    t_star = minimal_mutable_subtree(change, old).t_star
    assert t_star == fs({old.by_label("u2")})
    target = redecomposition_target(change, old, t_star)
    assert target.vertices == fs() and dict(target.edges) == {}
    cs = bag_constraints(old, t_star)
    assert [c.vertices for c in cs] == [fs(), fs()]
    res = TopDownDecomposer(DecomposerMode.EXACT).decompose(
        DecompositionTask(Hypergraph(target.edges), 1,
                          coverage_only={f"__C_{c.outer_node}": c.vertices for c in cs}))
    assert res.status is SearchStatus.FOUND and res.ghd is not None and len(res.ghd) == 0
    glued = glue(res.ghd, old, cs)
    rep = validate(change.new, glued)
    assert rep.ok, rep.violations
    assert undirected(glued)[0] == fs({fs({"u1", "u3"})})


def test_glue_picks_smallest_satisfying_node_and_keeps_inputs() -> None:
    old = GHD.from_spec(G_PRIME_SPEC)
    t4 = old.by_label("t4")
    cs = bag_constraints(old, [old.by_label("t1"), old.by_label("t2"), old.by_label("t3")])
    assert [old.node(c.outer_node).label for c in cs] == ["t4"]
    d_star = GHD.from_spec({"root": "n1",
                            "nodes": {"n1": ("ab", ("w1",)), "n2": ("eik", ("w3",)), "n3": ("cek", ("w5", "w3"))},
                            "children": {"n1": ["n2"], "n2": ["n3"]}})
    before = d_star.to_spec()
    out = glue(d_star, old, cs)
    assert d_star.to_spec() == before and len(old) == 4
    assert out.parent(out.by_label("t4")) == d_star.by_label("n2")  # n2 (id 1) < n3 (id 2)
    assert out.node(out.by_label("t4")).cover == old.node(t4).cover


def test_glue_remaps_colliding_ids() -> None:
    old = GHD.from_spec(G_PRIME_SPEC)
    cs = [BagConstraint(outer_node=old.by_label("t4"), inner_neighbor=old.by_label("t1"),
                        outer_tree=fs({old.by_label("t4")}), vertices=fs("k"))]
    # D* has 4 nodes (ids 0..3), so t4's id (3) collides and must be remapped
    d_star = GHD.from_spec({"root": "a", "nodes": {"a": ("x", ()), "b": ("y", ()), "c": ("k", ()), "d": ("k", ())},
                            "children": {"a": ["b", "c", "d"]}})
    out = glue(d_star, old, cs)
    assert len(out) == 5
    t4 = out.by_label("t4")
    assert t4 not in d_star.node_ids()
    assert out.parent(t4) == d_star.by_label("c")


def test_glue_label_clash_rejected() -> None:
    old = GHD.from_spec(G_PRIME_SPEC)
    cs = bag_constraints(old, [old.by_label("t1"), old.by_label("t2"), old.by_label("t3")])
    d_star = GHD.from_spec({"root": "t4", "nodes": {"t4": ("k", ())}, "children": {}})
    with pytest.raises(InvalidGHDError, match="labels"):
        glue(d_star, old, cs)

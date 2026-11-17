"""S10 unit tests: delta(H)* (D19, A11, invariant I8) and T*-induced bag constraints (D20, I5)."""

from __future__ import annotations

import pytest

from ighd.common.errors import InvalidGHDError
from ighd.constraints import BagConstraint, bag_constraints, redecomposition_target
from ighd.ghd import GHD
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddVar
from ighd.mutable import minimal_mutable_subtree, mutable_conditions
from tests.fixtures.expected import T_STAR_CASES
from tests.fixtures.paper import G_PRIME_SPEC, H_PP
from tests.paper_examples.test_thm45_repair import build_change

fs = frozenset
CASE_IDS = [c[0] for c in T_STAR_CASES]


# --------------------------------------------------------------------------- invariant I5
@pytest.mark.parametrize("case", T_STAR_CASES, ids=CASE_IDS)
def test_i5_one_constraint_per_outer_tree(case: tuple) -> None:
    _cid, h, spec, mod, _exp, _prov = case
    change = build_change(h, mod)
    old = GHD.from_spec(spec)
    t_star = minimal_mutable_subtree(change, old).t_star
    cs = bag_constraints(old, t_star)
    comps = old.components_without(t_star)
    assert sorted(c.outer_tree for c in cs) == sorted(comps)        # one-to-one with outer trees
    assert [c.outer_node for c in cs] == sorted(c.outer_node for c in cs)
    b_star = old.bag_union(t_star)
    for c in cs:
        links = [(u, w) for u in c.outer_tree for w in old.tree_neighbors(u) if w in t_star]
        assert links == [(c.outer_node, c.inner_neighbor)]          # exactly one tree edge (I5)
        assert c.vertices == old.node(c.outer_node).bag & b_star
        # the interface of the whole outer tree with T* is C_i (connectedness of the old tree)
        assert old.bag_union(c.outer_tree) & b_star == c.vertices


def test_whole_tree_gives_no_constraints() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    assert bag_constraints(g, g.node_ids()) == []


def test_empty_ghd_gives_no_constraints() -> None:
    assert bag_constraints(GHD(), []) == []


def test_disconnected_t_star_rejected() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    with pytest.raises(InvalidGHDError, match="not a connected subtree"):
        bag_constraints(g, [g.by_label("t3"), g.by_label("t4")])


def test_unknown_node_rejected() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    with pytest.raises(InvalidGHDError):
        bag_constraints(g, [99])


def test_leaf_t_star_constraint() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    t4 = g.by_label("t4")
    (c,) = bag_constraints(g, [t4])
    assert c == BagConstraint(outer_node=g.by_label("t1"), inner_neighbor=t4,
                              outer_tree=fs(g.node_ids()) - {t4}, vertices=fs("k"))


# --------------------------------------------------------------------------- T* = {} (A12)
def _empty_t_star_case():
    change = AddConstr("w9", fs({"x", "y"})).apply(Hypergraph(H_PP))
    old = GHD.from_spec(G_PRIME_SPEC)
    t_star = minimal_mutable_subtree(change, old).t_star
    return change, old, t_star


def test_empty_t_star_pseudo_constraint() -> None:
    change, old, t_star = _empty_t_star_case()
    assert t_star == fs()
    (c,) = bag_constraints(old, t_star)
    assert c.outer_node == c.inner_neighbor == old.root
    assert c.outer_tree == fs(old.node_ids())
    assert c.vertices == fs()


def test_empty_t_star_target_is_the_new_edge() -> None:
    change, old, t_star = _empty_t_star_case()
    target = redecomposition_target(change, old, t_star)
    assert target.vertices == fs("xy")
    assert dict(target.edges) == {"w9": fs("xy")}
    assert target.full_edges == fs({"w9"})


# --------------------------------------------------------------------------- delta(H)* (D19)
def test_target_whole_tree_is_all_of_new_h() -> None:
    change = AddVar("m", fs({"w6"})).apply(Hypergraph(H_PP))
    old = GHD.from_spec(G_PRIME_SPEC)
    target = redecomposition_target(change, old, old.node_ids())
    assert target.vertices == change.new.vertices
    assert dict(target.edges) == dict(change.new.edges)
    assert target.full_edges == change.new.edge_names


def test_target_drops_removed_vertices() -> None:
    # DelVar h on G': T* = {t1, t2}; h is in B(T*) but not in V(delta(H)).
    from ighd.modifications import DelVar
    change = DelVar("h").apply(Hypergraph(H_PP))
    old = GHD.from_spec(G_PRIME_SPEC)
    t_star = minimal_mutable_subtree(change, old).t_star
    target = redecomposition_target(change, old, t_star)
    assert target.vertices == fs("abcefgik")
    assert "h" not in target.vertices
    assert all(vs <= target.vertices for vs in target.edges.values())
    assert target.full_edges == fs(n for n, vs in change.new.edges.items() if vs <= target.vertices)


def test_i8_fires_on_non_mutable_t_star() -> None:
    # AddVar m into w6 = {j,k,l}: w6 becomes {j,k,l,m}, and j,l lie only in t4. T* = {t1} is a
    # subtree but violates Def 4.1(ii) (m is adjacent to j,k,l in B(T minus T*)), so the restriction
    # of w6 to V* = {c,e,h,i,k,m} would cut through an edge containing a new vertex.
    change = AddVar("m", fs({"w6"})).apply(Hypergraph(H_PP))
    old = GHD.from_spec(G_PRIME_SPEC)
    bad = [old.by_label("t1")]
    assert not mutable_conditions(change, old, bad).mutable
    with pytest.raises(AssertionError, match=r"invariant I8 violated: edge 'w6'"):
        redecomposition_target(change, old, bad)
    # the delta-mutable T* = {t1, t4} passes
    good = minimal_mutable_subtree(change, old).t_star
    assert {old.node(u).label for u in good} == {"t1", "t4"}
    assert redecomposition_target(change, old, good).edges["w6"] == fs("jklm")

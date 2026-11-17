"""S9: Def 4.1 condition checker and Algorithm 2 (minimal delta-mutable subtree, Lemma 4.4)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

import ighd.modifications as mods
from ighd.common.config import PAPER_DEFAULT, InducedComparison, Semantics
from ighd.common.errors import InvalidGHDError
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.modifications import AddConstr, AddVar, DelConstr, DelVar, ModificationResult
from ighd.mutable import MutableResult, minimal_mutable_subtree, mutable_conditions
from ighd.oracle import all_mutable_subtrees
from tests.fixtures.expected import T_STAR_CASES
from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, H_P2, H_PP

fs = frozenset
EDGEWISE = Semantics(induced_comparison=InducedComparison.EDGEWISE)
SET = Semantics(induced_comparison=InducedComparison.SET)


def labels(g: GHD, nodes: frozenset[int]) -> frozenset[str]:
    return fs(g.node(u).label for u in nodes)  # type: ignore[misc]


def ids(g: GHD, *lbls: str) -> frozenset[int]:
    return fs(g.by_label(x) for x in lbls)


def apply_case(h: Mapping[str, Any], spec: Any, mod: tuple[str, dict[str, Any]]) -> tuple[ModificationResult, GHD]:
    cls, kwargs = mod
    return getattr(mods, cls)(**kwargs).apply(Hypergraph(h)), GHD.from_spec(spec)


def check_log_invariants(g: GHD, res: MutableResult) -> None:
    """Structural invariants of an Alg 2 step log (lines 4-13)."""
    all_nodes = fs(g.node_ids())
    t_prime = all_nodes
    rnd = 1
    tested: list[int] = []
    for s in res.steps:
        assert s.round == rnd
        # line 5: leaves of the working tree, tried in increasing id order
        assert s.leaf == g.leaves_of(t_prime)[len(tested)]
        assert s.outside == all_nodes - (t_prime - {s.leaf})
        assert s.outside_vertices == g.bag_union(s.outside)
        assert s.accepted == (s.induced_equal and not s.adjacent_new)
        tested.append(s.leaf)
        if s.accepted:  # lines 11-12: shrink and restart in a new round
            t_prime = t_prime - {s.leaf}
            rnd += 1
            tested = []
    assert t_prime == res.t_star
    # line 13: the final round tested every leaf of T* (none if T* is empty) and rejected all
    assert tested == g.leaves_of(res.t_star)
    assert all(not s.accepted for s in res.steps if s.round == rnd)


# ------------------------------------------------------------------ L-A8 pin (S15)
def test_a8_merge_target_inside_or_outside_u_changes_t_star() -> None:
    """L-A8: Def 3.4 does not say whether the merged vertex w is one of U or new; the modification
    names it explicitly, and the choice changes T*. Path a-b-c-d, chain GHD n1{a,b}-n2{b,c}-n3{c,d},
    merge U = {a,b}.
      w = b (in U): only e1 changes (it loses a), so X may be {b,c,d} and T* = {n1}.
      w = z (new):  e1 -> {z}, e2 -> {z,c}; X must avoid a and b (both vanish) and c (adjacent
                    to the new z, condition (ii)); no outer node fits, so T* = T.
    Both agree with the brute-force minimum (Lemma 4.4)."""
    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd"})
    g = GHD.from_spec({"root": "n1", "nodes": {"n1": ("ab", ("e1",)), "n2": ("bc", ("e2",)),
                                               "n3": ("cd", ("e3",))},
                       "children": {"n1": ["n2"], "n2": ["n3"]}})
    want = {"b": fs({"n1"}), "z": fs({"n1", "n2", "n3"})}
    for w, expected_t_star in want.items():
        change = mods.AddEq(fs("ab"), w).apply(Hypergraph(h.edges))
        t_star = minimal_mutable_subtree(change, g).t_star
        assert labels(g, t_star) == expected_t_star, w
        assert t_star == all_mutable_subtrees(change, g)[0], w        # the unique minimum
    assert want["b"] != want["z"]


# ------------------------------------------------------------------ mutable_conditions
def test_conditions_ex43_true_subtree() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    c = mutable_conditions(ch, g, ids(g, "u1", "u2"))
    assert c.is_subtree and c.condition_i and c.condition_ii and c.mutable
    assert c.outside_vertices == fs("adfghjkl")
    assert c.diff.equal and c.adjacent_new == fs()


def test_conditions_ex43_u2_alone_fails_i() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    c = mutable_conditions(ch, g, ids(g, "u2"))
    assert c.is_subtree
    assert not c.condition_i
    assert c.condition_ii
    assert not c.mutable
    # u1's bag {a,b,c,e,h} is outside, so w7 & X = {c} in H_P2 but empty after deletion.
    assert ("w7", fs("c"), fs()) in c.diff.changed


def test_conditions_addvar_m_fails_ii_only() -> None:
    ch = AddVar("m", fs({"w6"})).apply(Hypergraph(H_PP))
    g = GHD.from_spec(G_PRIME_SPEC)
    c = mutable_conditions(ch, g, ids(g, "t1"))
    assert c.is_subtree
    assert c.condition_i            # w6 & X = {j,k,l} before and after
    assert not c.condition_ii
    assert c.adjacent_new == fs({"m"})
    assert not c.mutable


def test_conditions_non_subtree() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    c = mutable_conditions(ch, g, ids(g, "u3", "u4"))  # u3 and u4 are not adjacent
    assert not c.is_subtree
    assert not c.mutable


def test_conditions_empty_and_whole_tree() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    whole = mutable_conditions(ch, g, g.node_ids())
    assert whole.mutable and whole.outside_vertices == fs()
    empty = mutable_conditions(ch, g, [])
    assert empty.is_subtree and not empty.condition_i
    assert empty.outside_vertices == fs("abcdefghijkl")


def test_conditions_unknown_node_raises() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    with pytest.raises(InvalidGHDError):
        mutable_conditions(ch, g, [0, 99])


def test_conditions_set_mode_uses_set_diff() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    c = mutable_conditions(ch, g, ids(g, "u1"), SET)
    # X = B(u2,u3,u4) = {a,c,d,e,f,g,h,i,j,k,l}: {c,i} is a restriction only in H_P2
    assert not c.condition_i
    assert fs("ci") in c.diff.only_old and c.diff.changed == ()


# ------------------------------------------------------------------ T_STAR_CASES
@pytest.mark.parametrize("case", T_STAR_CASES, ids=[c[0] for c in T_STAR_CASES])
def test_expected_t_star(case: tuple[Any, ...]) -> None:
    _, h, spec, mod, expected, _prov = case
    ch, g = apply_case(h, spec, mod)
    res = minimal_mutable_subtree(ch, g)
    assert labels(g, res.t_star) == expected
    assert mutable_conditions(ch, g, res.t_star).mutable
    # local minimality: removing any single leaf of T* breaks mutability
    for u in g.leaves_of(res.t_star):
        assert not mutable_conditions(ch, g, res.t_star - {u}).mutable, g.node(u).label
    # agrees with the brute-force oracle's unique minimum (Lemma 4.4)
    found = all_mutable_subtrees(ch, g, EDGEWISE)
    assert [t for t in found if len(t) == len(found[0])] == [res.t_star]
    check_log_invariants(g, res)


# ------------------------------------------------------------------ edge cases
def test_fresh_edge_gives_empty_t_star() -> None:
    """A12: AddConstr of an edge made only of fresh vertices is invisible from every bag:
    condition (i) holds for X = V(H) (the new edge misses X) and (ii) holds (x, y are adjacent
    only to each other). Alg 2 therefore removes every node, the last one as a single-node
    leaf, and T* is EMPTY. The new part is attached separately later (S12)."""
    ch = AddConstr("w9", fs({"x", "y"})).apply(Hypergraph(H_PP))
    g = GHD.from_spec(G_PRIME_SPEC)
    res = minimal_mutable_subtree(ch, g)
    assert res.t_star == fs()
    assert mutable_conditions(ch, g, []).mutable
    assert sum(s.accepted for s in res.steps) == len(g)
    assert all_mutable_subtrees(ch, g)[0] == fs()
    check_log_invariants(g, res)


def _single_node() -> GHD:
    g = GHD()
    g.add_node("ab", ["e1"], label="r")
    return g


def test_single_node_visible_change() -> None:
    h = Hypergraph({"e1": "ab"})
    g = _single_node()
    assert validate(h, g).ok
    ch = AddVar("c", fs({"e1"})).apply(h)
    res = minimal_mutable_subtree(ch, g)
    assert res.t_star == fs(g.node_ids())
    assert len(res.steps) == 1 and not res.steps[0].accepted
    assert res.steps[0].induced_equal and res.steps[0].adjacent_new == fs("c")
    check_log_invariants(g, res)


def test_single_node_invisible_change() -> None:
    h = Hypergraph({"e1": "ab"})
    g = _single_node()
    ch = AddConstr("f", fs("xy")).apply(h)
    res = minimal_mutable_subtree(ch, g)
    assert res.t_star == fs()
    assert len(res.steps) == 1 and res.steps[0].accepted
    check_log_invariants(g, res)


def test_change_visible_from_every_bag_gives_whole_tree() -> None:
    """DelVar of v, which lies in every bag: removing any leaf leaves an outside bag containing v,
    and the edge of that bag loses v there, so no removal is accepted and T* = T."""
    h = Hypergraph({"e1": "va", "e2": "vb", "e3": "vc", "e4": "vd"})
    g = GHD.from_spec({
        "root": "r",
        "nodes": {"r": ("va", ("e1",)), "x": ("vb", ("e2",)), "y": ("vc", ("e3",)), "z": ("vd", ("e4",))},
        "children": {"r": ["x", "z"], "x": ["y"], "y": [], "z": []},
    })
    assert validate(h, g).ok
    ch = DelVar("v").apply(h)
    res = minimal_mutable_subtree(ch, g)
    assert res.t_star == fs(g.node_ids())
    assert all(not s.accepted and not s.induced_equal for s in res.steps)
    assert [s.leaf for s in res.steps] == g.leaves_of(g.node_ids())
    assert all(s.round == 1 for s in res.steps)
    assert all_mutable_subtrees(ch, g) == [fs(g.node_ids())]


def test_delconstr_w5_result_is_mutable() -> None:
    """DelConstr(w5) on H_P' (all of c, e, h stay covered by other edges): the result is a
    mutable subtree per the oracle, and the log satisfies the Alg 2 invariants."""
    ch = DelConstr("w5").apply(Hypergraph(H_PP))
    g = GHD.from_spec(G_PRIME_SPEC)
    res = minimal_mutable_subtree(ch, g)
    found = set(all_mutable_subtrees(ch, g))
    assert res.t_star in found
    check_log_invariants(g, res)


def test_default_semantics_is_edgewise() -> None:
    ch = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    assert minimal_mutable_subtree(ch, g) == minimal_mutable_subtree(ch, g, EDGEWISE)
    assert PAPER_DEFAULT.induced_comparison is InducedComparison.EDGEWISE

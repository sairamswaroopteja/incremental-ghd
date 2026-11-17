"""Unit tests for the S8 replay normal-form checker (ghd.normal_form; Def 5.1 precondition)."""

from __future__ import annotations

from typing import Any

import pytest

from ighd.common import PAPER_DEFAULT
from ighd.ghd.normal_form import check_normal_form
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, H_P, H_P2, H_P3, H_PP, JOIN_TREE_HP_SPEC, S_SPEC

fs = frozenset
ALL_PP = fs(H_PP)


def build(spec: Any) -> GHD:
    return GHD.from_spec(spec)


def handled_by_label(g: GHD, handled: Any) -> dict[str, frozenset[str]]:
    return {g.node(n).label: es for n, es in handled.items()}


@pytest.mark.parametrize("h, spec", [
    (H_PP, G_PRIME_SPEC), (H_P2, G2_SPEC), (H_P, JOIN_TREE_HP_SPEC), (H_P3, S_SPEC),
], ids=["fig3", "fig6a", "jointree", "S"])
def test_paper_ghds_are_nf(h: Any, spec: Any) -> None:
    hg, g = Hypergraph(h), build(spec)
    assert validate(hg, g).ok
    r = check_normal_form(hg, g, PAPER_DEFAULT)
    assert r.ok, r.reason
    assert set(r.handled) == set(g.node_ids())
    assert r.failed_node is None


def test_fig3_handled_sets() -> None:
    g = build(G_PRIME_SPEC)
    r = check_normal_form(Hypergraph(H_PP), g)
    assert handled_by_label(g, r.handled) == {
        "t1": ALL_PP, "t2": fs({"w1", "w2", "w4"}), "t3": fs({"w4"}), "t4": fs({"w6"})}


def test_fig6a_handled_sets() -> None:
    """Replay of Fig. 6(a) on H_P2 (the definition, step by step):

    u1, bag {a,b,c,e,h}: handles all of E(H_P2). w1 and w5 lie inside the bag (A3: no component).
      w2={f,g,h} and w4={a,d,f} share f outside the bag -> {w2,w4};
      w3={e,i,k}, w7={c,i} share i, w3 and w6={j,k,l} share k -> {w3,w6,w7}.
      u2 (bag {c,e,i,k}) meets {i,k}, so it gets {w3,w6,w7}; u3 (bag {a,d,f,g,h}) gets {w2,w4}.
    u2: w3 and w7 inside {c,e,i,k}; w6 has j,l outside -> {w6} -> u4.
    u3: w2, w4 inside {a,d,f,g,h}: no components, and u3 is a leaf.
    So u2 handles {w3,w6,w7} (with w7, which Example 4.3 then deletes).
    """
    g = build(G2_SPEC)
    r = check_normal_form(Hypergraph(H_P2), g)
    assert r.ok
    assert handled_by_label(g, r.handled) == {
        "u1": fs(H_P2), "u2": fs({"w3", "w6", "w7"}), "u3": fs({"w2", "w4"}), "u4": fs({"w6"})}


def test_jointree_handled_sets() -> None:
    """Each join-tree node p_i removes exactly its own edge (all others meet it in <= 1 vertex)."""
    g = build(JOIN_TREE_HP_SPEC)
    r = check_normal_form(Hypergraph(H_P), g)
    assert r.ok
    got = handled_by_label(g, r.handled)
    assert got["p1"] == fs(H_P)
    assert got["p2"] == fs(H_P) - {"w2"}
    assert got["p6"] == fs({"w6"})


def test_fig3_rerooted_at_t3_is_still_nf() -> None:
    """Rerooting Fig. 3 at the leaf t3 = {a,d,f}: all edges but w4 (inside the bag) form ONE
    [{a,d,f}]-component (b,c,e,g,h,i,j,k,l link w1,w2,w5,w3,w6), and t3 has one child, t2.
    At t2 = {a,b,c,f,g,h} the handled set {w1,w2,w3,w5,w6} loses w1,w2 and leaves the single
    component {w3,w5,w6}, matched by t2's only child t1 (now a child); at t1 the handled set
    {w3,w5,w6} leaves {w6} -> t4. So every node again has exactly one child per component: the
    reversed path t3-t2-t1 never separates two components at one node.
    """
    g = build(G_PRIME_SPEC)
    g.reroot(g.by_label("t3"))
    r = check_normal_form(Hypergraph(H_PP), g)
    assert r.ok, r.reason
    assert handled_by_label(g, r.handled) == {
        "t3": ALL_PP, "t2": ALL_PP - {"w4"}, "t1": fs({"w3", "w5", "w6"}), "t4": fs({"w6"})}


# --- non-NF cases ---------------------------------------------------------------------------
def test_extra_child_without_component() -> None:
    """Fig. 3 plus a child {k}/{w6} under t4: still a valid GHD (k stays connected via t4), but
    t4 handles {w6}, which lies inside its bag, so t4 has no component for the new child."""
    g = build(G_PRIME_SPEC)
    t4 = g.by_label("t4")
    g.add_node("k", {"w6"}, parent=t4, label="x")
    h = Hypergraph(H_PP)
    assert validate(h, g).ok
    r = check_normal_form(h, g)
    assert not r.ok and r.failed_node == t4
    assert "1 children but 0" in r.reason


def test_component_split_over_two_children() -> None:
    """C1 = {w1,w2,w4} split over two children of t1: X = {a,b,c,f,g,h} covers w1,w2 and
    Y = {a,d,f} covers w4, and C2 = {w6} is left without a node. Two children, two components,
    but both children meet only C1 by the line-16 rule: no bijection at t1.
    (A component can never be split in a *valid* GHD: two of its edges sharing a vertex outside
    the bag must sit in one child subtree, MATHEMATICAL_INVARIANTS Lemma D. So this tree is
    not a GHD; the NF checker does not require validity.)"""
    g = GHD.from_spec({
        "root": "t1",
        "nodes": {"t1": ("cehik", ("w5", "w3")), "X": ("abcfgh", ("w1", "w2")), "Y": ("adf", ("w4",))},
        "children": {"t1": ["X", "Y"]},
    })
    h = Hypergraph(H_PP)
    assert not validate(h, g).ok
    r = check_normal_form(h, g)
    assert not r.ok and r.failed_node == g.by_label("t1")
    assert "no bijection" in r.reason


def test_component_split_across_levels_fails_coverage() -> None:
    """Line-16 matches but coverage fails: t1's child X = {a,b,c,f,g,h} meets C1 but w4 = {a,d,f}
    is covered by a node Y under t4 instead (not a GHD: a, f are disconnected)."""
    g = GHD.from_spec({
        "root": "t1",
        "nodes": {"t1": ("cehik", ("w5", "w3")), "X": ("abcfgh", ("w1", "w2")),
                  "t4": ("jkl", ("w6",)), "Y": ("adf", ("w4",))},
        "children": {"t1": ["X", "t4"], "t4": ["Y"]},
    })
    r = check_normal_form(Hypergraph(H_PP), g)
    assert not r.ok and r.failed_node == g.by_label("t1")


def test_child_bag_not_meeting_its_component() -> None:
    """A valid GHD where t1's child Z = {k}/{w3} sits between t1 and {j,k,l}: Z's bag misses
    V({w6}) - B_t1 = {j,l}, so the line-16 rule matches Z to nothing."""
    g = GHD.from_spec({
        "root": "t1",
        "nodes": {"t1": ("cehik", ("w5", "w3")), "t2": ("abcfgh", ("w1", "w2")), "t3": ("adf", ("w4",)),
                  "Z": ("k", ("w3",)), "t4": ("jkl", ("w6",))},
        "children": {"t1": ["t2", "Z"], "t2": ["t3"], "Z": ["t4"]},
    })
    h = Hypergraph(H_PP)
    assert validate(h, g).ok
    r = check_normal_form(h, g)
    assert not r.ok and r.failed_node == g.by_label("t1")


def test_missing_child_for_component() -> None:
    """Fig. 3 without t4: w6 is uncovered and t1 has 1 child for 2 components."""
    g = GHD.from_spec({"root": "t1",
                       "nodes": {"t1": ("cehik", ("w5", "w3")), "t2": ("abcfgh", ("w1", "w2")),
                                 "t3": ("adf", ("w4",))},
                       "children": {"t1": ["t2"], "t2": ["t3"]}})
    r = check_normal_form(Hypergraph(H_PP), g)
    assert not r.ok and r.failed_node == g.by_label("t1")


def test_failure_deeper_in_the_tree() -> None:
    """Fig. 3 with an extra leaf under t3 (bag {d}): the violation is reported at t3, not t1."""
    g = build(G_PRIME_SPEC)
    t3 = g.by_label("t3")
    g.add_node("d", {"w4"}, parent=t3, label="y")
    r = check_normal_form(Hypergraph(H_PP), g)
    assert not r.ok and r.failed_node == t3
    assert r.handled == {}


def test_empty_ghd() -> None:
    assert check_normal_form(Hypergraph({}), GHD()).ok
    r = check_normal_form(Hypergraph(H_PP), GHD())
    assert not r.ok and r.failed_node is None and "empty" in r.reason


def test_single_node() -> None:
    h = Hypergraph({"e": "abc", "f": "bc"})
    g = GHD()
    g.add_node("abc", {"e"})
    r = check_normal_form(h, g)
    assert r.ok and r.handled == {g.root: fs({"e", "f"})}

"""S4: the independent GHD validator (paper §2.2; PAPER_ANALYSIS D6, D7, A4)."""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.ghd.tree import GHD
from ighd.ghd.validation import (
    DisconnectedVertex,
    UncoveredEdge,
    UnguardedVertices,
    UnknownBagVertex,
    UnknownCoverEdge,
    validate,
    width,
)
from ighd.hypergraph.core import Hypergraph
from ighd.oracle.ghw_dp import exact_ghw
from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, H_P, H_P2, H_P3, H_PP, JOIN_TREE_HP_SPEC, S_SPEC

fs = frozenset
SETTINGS = settings(derandomize=True, max_examples=100, deadline=None)


def _spec_copy(spec: dict) -> dict:
    return copy.deepcopy(spec)


# ------------------------------------------------------------------ the paper's GHDs are valid
@pytest.mark.parametrize("spec,edges,w", [
    (G_PRIME_SPEC, H_PP, 2),
    (G2_SPEC, H_P2, 2),
    (JOIN_TREE_HP_SPEC, H_P, 1),
    (S_SPEC, H_P3, 2),
], ids=["G_prime/H_PP", "G2/H_P2", "jointree/H_P", "S/H_P3"])
def test_fixture_ghds_are_valid(spec: dict, edges: dict, w: int) -> None:
    g = GHD.from_spec(spec)
    rep = validate(Hypergraph(edges), g)
    assert rep.ok, rep.violations
    assert rep.violations == ()
    assert rep.width == w == width(g)
    assert rep.warnings == ()


def test_edge_cover_map_of_g_prime() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    t = {lbl: g.by_label(lbl) for lbl in ("t1", "t2", "t3", "t4")}
    rep = validate(Hypergraph(H_PP), g)
    assert dict(rep.edge_cover_map) == {
        "w1": (t["t2"],), "w2": (t["t2"],), "w3": (t["t1"],),
        "w4": (t["t3"],), "w5": (t["t1"],), "w6": (t["t4"],),
    }


def test_edge_cover_map_lists_every_holder_sorted() -> None:
    h = Hypergraph({"e": "ab"})
    g = GHD()
    r = g.add_node("ab", ["e"])
    c1 = g.add_node("ab", ["e"], parent=r)
    g.add_node("ab", ["e"], parent=c1)
    rep = validate(h, g)
    assert rep.ok
    assert rep.edge_cover_map["e"] == (0, 1, 2)


# ------------------------------------------------------------------ Example 4.3: G2 checked against H_P'
def test_g2_against_hpp_reports_deleted_cover_edge() -> None:
    g = GHD.from_spec(G2_SPEC)
    u2 = g.by_label("u2")
    rep = validate(Hypergraph(H_PP), g)
    assert not rep.ok
    assert rep.violations == (UnknownCoverEdge(u2, "w7"), UnguardedVertices(u2, fs("c")))
    assert rep.width == 2


# ------------------------------------------------------------------ single-fault mutants of Fig. 3
def test_mutant_shrunken_bag_uncovers_w6() -> None:
    spec = _spec_copy(G_PRIME_SPEC)
    spec["nodes"]["t4"] = ("jk", ("w6",))
    rep = validate(Hypergraph(H_PP), GHD.from_spec(spec))
    assert rep.violations == (UncoveredEdge("w6", fs("jkl")),)
    assert rep.edge_cover_map["w6"] == ()
    assert any("l" in w for w in rep.warnings)  # vertex-coverage diagnostic (A4)


def test_mutant_moved_node_disconnects_k() -> None:
    spec = _spec_copy(G_PRIME_SPEC)
    spec["children"] = {"t1": ["t2"], "t2": ["t3"], "t3": ["t4"], "t4": []}
    g = GHD.from_spec(spec)
    rep = validate(Hypergraph(H_PP), g)
    assert rep.violations == (DisconnectedVertex("k", (fs({g.by_label("t1")}), fs({g.by_label("t4")}))),)


def test_mutant_dropped_guard_edge() -> None:
    spec = _spec_copy(G_PRIME_SPEC)
    spec["nodes"]["t1"] = ("cehik", ("w3",))
    g = GHD.from_spec(spec)
    rep = validate(Hypergraph(H_PP), g)
    assert rep.violations == (UnguardedVertices(g.by_label("t1"), fs("ch")),)


# ------------------------------------------------------------------ A4: edge vs vertex coverage
def test_a4_vertex_coverage_is_not_enough() -> None:
    h = Hypergraph({"e1": "ab"})
    g = GHD()
    r = g.add_node("a", ["e1"])
    g.add_node("b", ["e1"], parent=r)
    rep = validate(h, g)
    assert rep.violations == (UncoveredEdge("e1", fs("ab")),)
    assert not rep.ok


# ------------------------------------------------------------------ well-formedness
def test_unknown_bag_vertex() -> None:
    spec = _spec_copy(G_PRIME_SPEC)
    spec["nodes"]["t4"] = ("jklz", ("w6",))
    g = GHD.from_spec(spec)
    t4 = g.by_label("t4")
    rep = validate(Hypergraph(H_PP), g)
    assert rep.violations == (UnknownBagVertex(t4, "z"), UnguardedVertices(t4, fs("z")))


def test_violation_order_is_deterministic() -> None:
    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd"})
    g = GHD()
    r = g.add_node("ab", ["e1", "zz"])          # 0: unknown cover edge
    m = g.add_node("cq", ["e3"], parent=r)      # 1: unknown vertex q, unguarded q
    g.add_node("bd", ["e1"], parent=m)          # 2: b disconnected from 0, d unguarded
    rep = validate(h, g)
    assert rep.violations == (
        UnknownCoverEdge(0, "zz"),
        UnknownBagVertex(1, "q"),
        UncoveredEdge("e2", fs("bc")),
        UncoveredEdge("e3", fs("cd")),
        DisconnectedVertex("b", (fs({0}), fs({2}))),
        UnguardedVertices(1, fs("q")),
        UnguardedVertices(2, fs("d")),
    )
    assert rep.width == 2


def test_disconnected_parts_are_sorted_by_smallest_id() -> None:
    h = Hypergraph({"e": "v", "f": "vw"})
    g = GHD()
    r = g.add_node("w", ["f"])
    for _ in range(3):
        g.add_node("vw", ["f"], parent=r)
    g.reroot(3)
    rep = validate(h, g)
    assert rep.violations == (DisconnectedVertex("v", (fs({1}), fs({2}), fs({3}))),)


# ------------------------------------------------------------------ empty cases
def test_empty_ghd_of_empty_hypergraph() -> None:
    rep = validate(Hypergraph({}), GHD())
    assert rep.ok and rep.width == 0 and dict(rep.edge_cover_map) == {} and rep.warnings == ()
    assert width(GHD()) == 0


def test_empty_ghd_of_nonempty_hypergraph() -> None:
    rep = validate(Hypergraph(H_PP), GHD())
    assert rep.violations == tuple(UncoveredEdge(n, fs(vs)) for n, vs in sorted(H_PP.items()))
    assert rep.width == 0


def test_empty_bag_is_a_warning_only() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    g.add_node((), (), parent=g.by_label("t3"))
    rep = validate(Hypergraph(H_PP), g)
    assert rep.ok
    assert rep.warnings == ("node 4 has an empty bag",)


def test_single_empty_node_for_empty_hypergraph() -> None:
    g = GHD()
    g.add_node((), ())
    rep = validate(Hypergraph({}), g)
    assert rep.ok and rep.width == 0


# ------------------------------------------------------------------ properties
@st.composite
def hypergraphs(draw: st.DrawFn, max_vertices: int = 7, max_edges: int = 6) -> Hypergraph:
    n = draw(st.integers(1, max_vertices))
    masks = draw(st.lists(st.integers(1, 2 ** n - 1), min_size=1, max_size=max_edges))
    names = "abcdefghij"
    return Hypergraph({f"e{i}": {names[k] for k in range(n) if m >> k & 1} for i, m in enumerate(masks)})


@SETTINGS
@given(hypergraphs())
def test_exact_ghw_witness_validates(h: Hypergraph) -> None:
    k, g = exact_ghw(h)
    rep = validate(h, g)
    assert rep.ok, rep.violations
    assert rep.width == k == width(g)


def _naive_ok(h: Hypergraph, g: GHD) -> bool:
    """A differently structured check: connectedness via |nodes| - |tree edges inside| == 1."""
    nodes = {n.id: n for n in g}
    tree_edges = [(u, p) for u in nodes if (p := g.parent(u)) is not None]
    for e, vs in h.edges.items():
        if not any(vs <= n.bag for n in nodes.values()):
            return False
    for v in h.vertices:
        occ = {u for u, n in nodes.items() if v in n.bag}
        inside = sum(1 for a, b in tree_edges if a in occ and b in occ)
        if occ and len(occ) - inside != 1:
            return False
    for n in nodes.values():
        if not n.cover <= h.edge_names:
            return False
        if not n.bag <= h.vertices:
            return False
        if not n.bag <= h.covered_vertices(n.cover):
            return False
    return True


@st.composite
def hypergraph_and_random_tree(draw: st.DrawFn) -> tuple[Hypergraph, GHD]:
    h = draw(hypergraphs(max_vertices=5, max_edges=4))
    verts = sorted(h.vertices) + ["z"]
    names = sorted(h.edge_names) + ["ghost"]
    n = draw(st.integers(1, 6))
    g = GHD()
    for i in range(n):
        bag = draw(st.sets(st.sampled_from(verts), max_size=4))
        cover = draw(st.sets(st.sampled_from(names), max_size=2))
        g.add_node(bag, cover, parent=None if i == 0 else draw(st.integers(0, i - 1)))
    return h, g


@settings(derandomize=True, max_examples=300, deadline=None)
@given(hypergraph_and_random_tree())
def test_validator_agrees_with_naive_check(case: tuple[Hypergraph, GHD]) -> None:
    h, g = case
    rep = validate(h, g)
    assert rep.ok == _naive_ok(h, g)
    assert rep.width == max(len(n.cover) for n in g)
    assert validate(h, g) == rep  # deterministic

"""S1: the Hypergraph value type (paper §2.1; PAPER_ANALYSIS D2-D5, A1, A9)."""

from __future__ import annotations

from itertools import combinations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.common.errors import InvalidHypergraphError
from ighd.hypergraph import Hypergraph
from tests.fixtures.expected import HPP_DEGREES, HPP_INDUCED_ADFGH, HPP_RANK
from tests.fixtures.paper import H_P, H_P2, H_P3, H_PP

fs = frozenset
PROPS = settings(derandomize=True, max_examples=200, deadline=None)

VERTICES = st.sampled_from(list("abcdefghij"))
EDGE_NAMES = st.sampled_from([f"e{i}" for i in range(8)])
EDGE_DICTS = st.dictionaries(EDGE_NAMES, st.frozensets(VERTICES, min_size=1, max_size=5), max_size=8)


# ------------------------------------------------------------------- paper fixtures
def test_hpp_rank() -> None:
    assert Hypergraph(H_PP).rank() == HPP_RANK == 3


def test_hpp_degrees() -> None:
    h = Hypergraph(H_PP)
    assert {v: h.degree(v) for v in h.vertices} == HPP_DEGREES


def test_hpp_induced_adfgh() -> None:
    """Paper Fig. 6(b): H_P'[{a,d,f,g,h}]."""
    assert Hypergraph(H_PP).induced(set("adfgh")) == HPP_INDUCED_ADFGH


def test_fixture_vertex_sets() -> None:
    assert Hypergraph(H_PP).vertices == fs("abcdefghijkl")
    assert len(Hypergraph(H_PP).vertices) == 12
    assert Hypergraph(H_P).vertices == fs("abcdefghijkl") - {"h"}
    assert len(Hypergraph(H_P).vertices) == 11


def test_hpp_iwidth_is_one() -> None:
    h = Hypergraph(H_PP)
    iwidth = max(len(h.edge(a) & h.edge(b)) for a, b in combinations(sorted(h), 2))
    assert iwidth == 1


@pytest.mark.parametrize("edges", [H_P, H_PP, H_P2, H_P3])
def test_fixtures_have_no_duplicates(edges: dict[str, frozenset[str]]) -> None:
    h = Hypergraph(edges)
    assert not h.has_duplicate_edges()
    assert dict(h.edges) == edges
    assert len(h) == len(edges)


def test_basic_access_on_hpp() -> None:
    h = Hypergraph(H_PP)
    assert h.edge_names == fs({"w1", "w2", "w3", "w4", "w5", "w6"})
    assert h.edge("w5") == fs("ceh")
    assert h.incident("h") == fs({"w2", "w5"})
    assert h.incident("zzz") == fs()
    assert h.covered_vertices(["w5", "w3"]) == fs("cehik")
    assert h.covered_vertices([]) == fs()
    assert h.neighbors("h") == fs("cefg")
    assert h.neighbors("zzz") == fs()
    assert h.degree("zzz") == 0
    assert list(h) == sorted(H_PP)


def test_adjacent_to_includes_own_vertices_in_h() -> None:
    h = Hypergraph(H_PP)
    assert h.adjacent_to({"h"}) == fs("cefgh")
    assert h.adjacent_to({"h", "zzz"}) == fs("cefgh")
    assert h.adjacent_to({"zzz"}) == fs()
    assert h.adjacent_to(set()) == fs()


def test_induced_drops_empty() -> None:
    """A1: restrictions e & U that are empty are dropped from H[U]."""
    h = Hypergraph(H_PP)
    ind = h.induced({"a", "zzz"})
    assert ind == {"w1": fs("a"), "w4": fs("a")}
    assert all(ind.values())
    assert h.induced(set()) == {}
    assert h.induced({"zzz"}) == {}


def test_derived_hypergraphs() -> None:
    h = Hypergraph(H_PP)
    assert h.subhypergraph(["w1", "w4"]) == Hypergraph({"w1": "abc", "w4": "adf"})
    assert h.with_edges({"w7": "ci"}) == Hypergraph(H_P2)
    assert h.with_edges({"w1": fs("acg")}) == Hypergraph(H_P3)
    assert Hypergraph(H_P2).without_edges(["w7"]) == h
    assert h.without_edges([]) == h
    assert h == Hypergraph(H_PP)  # the original is unchanged


def test_immutability() -> None:
    h = Hypergraph(H_PP)
    with pytest.raises(TypeError):
        h.edges["w1"] = fs("x")  # type: ignore[index]
    with pytest.raises(AttributeError):
        h.foo = 1  # type: ignore[attr-defined]
    src = {"x": {"a"}}
    h2 = Hypergraph(src)
    src["x"].add("b")
    src["y"] = {"c"}
    assert h2 == Hypergraph({"x": "a"})


def test_eq_hash_repr() -> None:
    h1 = Hypergraph({"a": "xy", "b": "z"})
    h2 = Hypergraph({"b": ["z"], "a": ("y", "x")})
    assert h1 == h2 and hash(h1) == hash(h2)
    assert repr(h1) == repr(h2) == "Hypergraph({'a': ['x', 'y'], 'b': ['z']})"
    assert h1 != Hypergraph({"a": "xy", "c": "z"})  # same vertex sets, different names
    assert h1.__eq__({"a": fs("xy"), "b": fs("z")}) is NotImplemented
    assert h1 != {"a": fs("xy"), "b": fs("z")}


# ------------------------------------------------------------------- errors
def test_empty_edge_rejected() -> None:
    with pytest.raises(InvalidHypergraphError, match="w9"):
        Hypergraph({"w1": "ab", "w9": []})


@pytest.mark.parametrize("edges", [{1: "ab"}, {"e": [1, 2]}, {"e": ["a", None]}, {"e": 5}, {None: "a"}])
def test_non_str_rejected(edges: dict) -> None:
    with pytest.raises(InvalidHypergraphError):
        Hypergraph(edges)


def test_with_edges_validates() -> None:
    with pytest.raises(InvalidHypergraphError, match="w1"):
        Hypergraph(H_PP).with_edges({"w1": []})


def test_unknown_edge_errors() -> None:
    h = Hypergraph(H_PP)
    with pytest.raises(KeyError, match="w99"):
        h.edge("w99")
    with pytest.raises(KeyError, match="w99"):
        h.covered_vertices(["w1", "w99"])
    with pytest.raises(KeyError, match="w99"):
        h.subhypergraph(["w1", "w99"])
    with pytest.raises(KeyError, match="w99"):
        h.without_edges(["w1", "w99"])


# ------------------------------------------------------------------- edge cases
def test_empty_hypergraph() -> None:
    h = Hypergraph({})
    assert h.vertices == fs() and h.edge_names == fs()
    assert h.rank() == 0 and len(h) == 0 and list(h) == []
    assert h.induced({"a"}) == {}
    assert h.covered_vertices([]) == fs()
    assert not h.has_duplicate_edges()
    assert h == Hypergraph({}) and repr(h) == "Hypergraph({})"


def test_singleton_edge() -> None:
    h = Hypergraph({"e": ["v"]})
    assert h.vertices == fs("v") and h.rank() == 1
    assert h.neighbors("v") == fs()
    assert h.adjacent_to(["v"]) == fs("v")
    assert h.induced(["v"]) == {"e": fs("v")}


def test_duplicate_vertex_sets_stay_distinct() -> None:
    """A9: equal vertex sets under different names are two edges."""
    h = Hypergraph({"e1": "ab", "e2": "ba", "e3": "c"})
    assert len(h) == 3 and h.has_duplicate_edges()
    assert h.incident("a") == fs({"e1", "e2"})
    assert h.induced("a") == {"e1": fs("a"), "e2": fs("a")}
    assert not h.without_edges(["e2"]).has_duplicate_edges()


def test_disconnected_hypergraph() -> None:
    h = Hypergraph({"x": "ab", "y": "cd"})
    assert h.neighbors("a") == fs("b")
    assert h.adjacent_to({"a"}) == fs("ab")
    assert h.vertices == fs("abcd")
    assert h.induced("ac") == {"x": fs("a"), "y": fs("c")}


# ------------------------------------------------------------------- properties
@PROPS
@given(EDGE_DICTS)
def test_incidence_round_trip(edges: dict[str, frozenset[str]]) -> None:
    h = Hypergraph(edges)
    for e in h:
        for v in "abcdefghijz":
            assert (v in h.edge(e)) == (e in h.incident(v))
    for v in h.vertices:
        assert h.incident(v) and h.degree(v) == len(h.incident(v))
        assert h.neighbors(v) == h.adjacent_to({v}) - {v}


@PROPS
@given(EDGE_DICTS, st.frozensets(VERTICES), st.frozensets(VERTICES))
def test_induced_restriction_commutes(edges: dict[str, frozenset[str]], u: frozenset[str], w0: frozenset[str]) -> None:
    """For W <= U: (H[U])[W] == H[W] (empty restrictions dropped at each step)."""
    h = Hypergraph(edges)
    w = w0 & u
    restricted = {n: r & w for n, r in h.induced(u).items() if r & w}
    assert restricted == h.induced(w)


@PROPS
@given(EDGE_DICTS)
def test_covered_vertices_of_all_edges(edges: dict[str, frozenset[str]]) -> None:
    h = Hypergraph(edges)
    assert h.covered_vertices(h.edge_names) == h.vertices
    assert h.induced(h.vertices) == dict(h.edges)
    assert h.rank() == max((len(v) for v in edges.values()), default=0)


@PROPS
@given(EDGE_DICTS, st.randoms(use_true_random=False))
def test_eq_hash_insertion_order(edges: dict[str, frozenset[str]], rnd) -> None:
    items = list(edges.items())
    rnd.shuffle(items)
    h1, h2 = Hypergraph(edges), Hypergraph(dict(items))
    assert h1 == h2 and hash(h1) == hash(h2) and repr(h1) == repr(h2)
    assert list(h1) == list(h2) == sorted(edges)

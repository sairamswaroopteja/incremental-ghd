"""S6: [U]-components and connection sets (paper §2.3; PAPER_ANALYSIS D9, A3; ledger L-A3)."""

from __future__ import annotations

import pytest

from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.hypergraph import Hypergraph
from ighd.static.separation import components, connection, inside_edges
from tests.fixtures.expected import COMPONENT_CASES
from tests.fixtures.paper import H_PP

fs = frozenset
HPP = Hypergraph(H_PP)
EX23_SEP = fs("cehik")


@pytest.mark.parametrize(("h", "edges", "sep", "expected", "provenance"), COMPONENT_CASES,
                         ids=[c[4] for c in COMPONENT_CASES])
def test_component_cases(h: dict, edges: frozenset | None, sep: frozenset, expected: list,
                         provenance: str) -> None:
    hg = Hypergraph(h)
    got = components(hg, edges if edges is not None else hg.edge_names, sep)
    assert got == expected, provenance


def test_ex23_inside_edges() -> None:
    assert inside_edges(HPP, HPP.edge_names, EX23_SEP) == fs({"w3", "w5"})


def test_ex23_connections() -> None:
    assert connection(HPP, {"w1", "w2", "w4"}, EX23_SEP) == fs("ch")
    assert connection(HPP, {"w6"}, EX23_SEP) == fs("k")


@pytest.mark.paper_discrepancy
def test_a3_literal_reading_makes_inside_edges_singletons() -> None:
    """A3 / ledger L-A3: under the literal §2.3 definition, w3 and w5 (both <= {c,e,h,i,k}) are
    singleton [U]-components. The paper's Examples 2.3 and 5.2 do NOT count them; PAPER_DEFAULT
    (inside_edges_form_components=False) reproduces the examples, this flag only documents the
    difference."""
    literal = Semantics(inside_edges_form_components=True)
    got = components(HPP, HPP.edge_names, EX23_SEP, literal)
    assert got == [fs({"w1", "w2", "w4"}), fs({"w3"}), fs({"w5"}), fs({"w6"})]
    assert components(HPP, HPP.edge_names, EX23_SEP, PAPER_DEFAULT) == [fs({"w1", "w2", "w4"}), fs({"w6"})]


def test_empty_separator_is_plain_edge_connectivity() -> None:
    h = Hypergraph({"a": "xy", "b": "yz", "c": "pq", "d": "q"})
    assert components(h, h.edge_names, ()) == [fs("ab"), fs("cd")]
    # H_P' is connected
    assert components(HPP, HPP.edge_names, ()) == [HPP.edge_names]


def test_separator_covering_everything_gives_no_components() -> None:
    assert components(HPP, HPP.edge_names, HPP.vertices) == []
    assert components(HPP, HPP.edge_names, HPP.vertices | {"zz"}) == []
    assert inside_edges(HPP, HPP.edge_names, HPP.vertices) == HPP.edge_names


def test_edges_sharing_only_separator_vertices_are_separate() -> None:
    # e1, e2 share only y; with y in U they are NOT [U]-adjacent (unlike primal connectivity).
    h = Hypergraph({"e1": "xy", "e2": "yz"})
    assert components(h, h.edge_names, {"y"}) == [fs({"e1"}), fs({"e2"})]
    assert components(h, h.edge_names, set()) == [fs({"e1", "e2"})]


def test_single_edge() -> None:
    h = Hypergraph({"e": "xyz"})
    assert components(h, ["e"], {"x"}) == [fs({"e"})]
    assert components(h, ["e"], "xyz") == []
    assert connection(h, ["e"], {"x", "q"}) == fs("x")


def test_empty_edge_selection() -> None:
    assert components(HPP, [], EX23_SEP) == []
    assert inside_edges(HPP, [], EX23_SEP) == fs()
    assert connection(HPP, [], EX23_SEP) == fs()


def test_edge_subset_ignores_other_edges() -> None:
    # w1 and w2 are linked in H_P' only through w4 (via a and f); without w4 they split.
    assert components(HPP, {"w1", "w2"}, ()) == [fs({"w1"}), fs({"w2"})]
    assert components(HPP, {"w1", "w2", "w4"}, ()) == [fs({"w1", "w2", "w4"})]


def test_unknown_edge_name_raises() -> None:
    with pytest.raises(KeyError, match="nope"):
        components(HPP, {"w1", "nope"}, ())
    with pytest.raises(KeyError, match="nope"):
        inside_edges(HPP, {"nope"}, ())
    with pytest.raises(KeyError, match="nope"):
        connection(HPP, {"nope"}, ())


def test_foreign_separator_vertices_are_ignored() -> None:
    assert components(HPP, HPP.edge_names, EX23_SEP | {"zz", "yy"}) == components(HPP, HPP.edge_names, EX23_SEP)
    assert connection(HPP, {"w6"}, EX23_SEP | {"zz"}) == fs("k")


def test_input_iterables_are_accepted_once() -> None:
    """Generators (single-pass iterables) work for every argument."""
    got = components(HPP, (e for e in HPP.edge_names), (v for v in EX23_SEP))
    assert got == [fs({"w1", "w2", "w4"}), fs({"w6"})]
    assert connection(HPP, (e for e in ["w6"]), (v for v in EX23_SEP)) == fs("k")


def test_order_is_by_smallest_edge_name() -> None:
    h = Hypergraph({"b": "xy", "z": "y", "a": "pq", "c": "q"})
    assert components(h, h.edge_names, ()) == [fs("ac"), fs("bz")]

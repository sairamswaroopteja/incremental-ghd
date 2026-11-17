"""S1: HyperBench text format."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.common.errors import InvalidHypergraphError
from ighd.hypergraph import Hypergraph, parse_hyperbench, to_hyperbench
from tests.fixtures.paper import H_P, H_P2, H_P3, H_PP

PROPS = settings(derandomize=True, max_examples=200, deadline=None)


def test_parse_with_comments_whitespace_and_period() -> None:
    text = """% HyperBench-style instance
    % another comment line
    w1 (a, b,c),
      w2(f,
         g, h),
    E_3:x(V-1, v_2.0) ,
    w4(a)
    .
    """
    h = parse_hyperbench(text)
    assert h == Hypergraph({"w1": "abc", "w2": "fgh", "E_3:x": ["V-1", "v_2.0"], "w4": "a"})


def test_parse_without_period_and_empty() -> None:
    assert parse_hyperbench("a(x,y),b(y)") == Hypergraph({"a": "xy", "b": "y"})
    assert parse_hyperbench("") == Hypergraph({})
    assert parse_hyperbench("% only a comment\n") == Hypergraph({})
    assert parse_hyperbench(".") == Hypergraph({})


@pytest.mark.parametrize("text,fragment", [
    ("a(x,y", "a(x,y"),            # unclosed
    ("a(x,(y))", "a(x,(y)"),       # nested
    ("a(x)),b(y)", ")"),           # stray ')'
    ("a(x) b(y)", "b(y)"),         # missing comma (whitespace is ignored -> "a(x)b(y)")
    ("a(),b(y)", "a()"),           # edge with no vertices
    ("a(x),a(y)", "a(y)"),         # duplicate edge name
    ("a(x,,y)", "a(x,,y)"),        # empty vertex
    ("(x)", "(x)"),                # no edge name
    ("a(x),", "a(x)"),             # trailing comma
    ("a(x),b", "b"),               # term without parentheses
    ("a(x)..", "."),               # two periods
])
def test_malformed_input(text: str, fragment: str) -> None:
    with pytest.raises(InvalidHypergraphError) as exc:
        parse_hyperbench(text)
    assert fragment in str(exc.value)


def test_to_hyperbench_format() -> None:
    h = Hypergraph({"w2": "gf", "w1": "cab"})
    assert to_hyperbench(h) == "w1(a,b,c),\nw2(f,g)."
    assert to_hyperbench(Hypergraph({})) == "."


@pytest.mark.parametrize("edges", [H_P, H_PP, H_P2, H_P3])
def test_paper_round_trip(edges: dict[str, frozenset[str]]) -> None:
    h = Hypergraph(edges)
    assert parse_hyperbench(to_hyperbench(h)) == h


@pytest.mark.parametrize("edges", [{"a b": "x"}, {"e": ["x,y"]}, {"%e": "x"}, {"e": ["(x"]}, {"": "x"}])
def test_unserialisable_names(edges: dict) -> None:
    with pytest.raises(InvalidHypergraphError):
        to_hyperbench(Hypergraph(edges))


NAMES = st.text(alphabet="abcxyzABC0189_", min_size=1, max_size=5)


@PROPS
@given(st.dictionaries(NAMES, st.frozensets(NAMES, min_size=1, max_size=5), max_size=8))
def test_round_trip_property(edges: dict[str, frozenset[str]]) -> None:
    h = Hypergraph(edges)
    assert parse_hyperbench(to_hyperbench(h)) == h

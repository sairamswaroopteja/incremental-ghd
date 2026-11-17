"""S6 property tests: [U]-components against a naive reference (paper §2.3, D9, A3)."""

from __future__ import annotations

from collections import deque

from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.common.config import Semantics
from ighd.hypergraph import Hypergraph
from ighd.static.separation import components, connection, inside_edges

PROPS = settings(derandomize=True, max_examples=150, deadline=None)
ALPHABET = "abcdefghij"


@st.composite
def instances(draw: st.DrawFn) -> tuple[Hypergraph, frozenset[str], frozenset[str]]:
    """A random small hypergraph, a random edge subset and a random separator (may contain foreign vertices)."""
    n = draw(st.integers(1, 9))
    masks = draw(st.lists(st.integers(1, 2 ** len(ALPHABET) - 1), min_size=n, max_size=n))
    # sparsify: most edges get 1-3 vertices
    edges = {}
    for i, m in enumerate(masks):
        vs = [v for k, v in enumerate(ALPHABET) if m >> k & 1]
        edges[f"e{i}"] = frozenset(vs[: draw(st.integers(1, 3))])
    h = Hypergraph(edges)
    subset = frozenset(draw(st.sets(st.sampled_from(sorted(h.edge_names)))))
    sep = frozenset(draw(st.sets(st.sampled_from(list(ALPHABET) + ["x1", "x2"]), max_size=6)))
    return h, subset, sep


def naive_components(h: Hypergraph, edges: frozenset[str], u: frozenset[str]) -> set[frozenset[str]]:
    """BFS over pairs of edges, using the §2.3 definition literally, then dropping edges <= U (A3)."""
    live = [e for e in edges if not h.edge(e) <= u]
    seen: set[str] = set()
    out: set[frozenset[str]] = set()
    for start in live:
        if start in seen:
            continue
        comp = {start}
        queue = deque([start])
        seen.add(start)
        while queue:
            e1 = queue.popleft()
            for e2 in live:
                if e2 not in seen and (h.edge(e1) & h.edge(e2)) - u:
                    seen.add(e2)
                    comp.add(e2)
                    queue.append(e2)
        out.add(frozenset(comp))
    return out


@PROPS
@given(instances())
def test_matches_naive_reference(inst: tuple[Hypergraph, frozenset[str], frozenset[str]]) -> None:
    h, edges, u = inst
    got = components(h, edges, u)
    assert set(got) == naive_components(h, edges, u)
    assert len(got) == len(set(got))
    assert got == sorted(got, key=min)


@PROPS
@given(instances())
def test_components_and_inside_edges_partition(inst: tuple[Hypergraph, frozenset[str], frozenset[str]]) -> None:
    h, edges, u = inst
    parts = [*components(h, edges, u), inside_edges(h, edges, u)]
    union: set[str] = set()
    for p in parts:
        assert not (union & p)
        union |= p
    assert union == edges


@PROPS
@given(instances())
def test_separation_invariants(inst: tuple[Hypergraph, frozenset[str], frozenset[str]]) -> None:
    h, edges, u = inst
    comps = components(h, edges, u)
    outside = [h.covered_vertices(c) - u for c in comps]
    for c in comps:
        for e in c:
            assert h.edge(e) - u, "component edge must have a vertex outside U"
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            assert not (outside[i] & outside[j]), "distinct components share no vertex outside U"
    for c in comps:
        conn = connection(h, c, u)
        assert conn <= u
        assert not ((h.covered_vertices(c) - conn) & u)


@PROPS
@given(instances(), st.sets(st.sampled_from(["y1", "y2", "y3"]), min_size=1))
def test_invariant_under_foreign_separator_vertices(
        inst: tuple[Hypergraph, frozenset[str], frozenset[str]], extra: set[str]) -> None:
    h, edges, u = inst
    assert components(h, edges, u | extra) == components(h, edges, u)


@PROPS
@given(instances())
def test_literal_reading_adds_exactly_the_inside_singletons(
        inst: tuple[Hypergraph, frozenset[str], frozenset[str]]) -> None:
    h, edges, u = inst
    literal = components(h, edges, u, Semantics(inside_edges_form_components=True))
    expected = components(h, edges, u) + [frozenset({e}) for e in inside_edges(h, edges, u)]
    assert literal == sorted(expected, key=min)

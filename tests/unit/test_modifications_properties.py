"""S2 properties: invariants, inverse pairs and composition of the six modifications
(paper Defs 3.1-3.4) on random small hypergraphs with random *valid* parameters."""

from __future__ import annotations

from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.hypergraph import Hypergraph
from ighd.modifications import (
    AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar, ModificationResult, ModificationSequence, compose,
)

fs = frozenset
PROPS = settings(derandomize=True, max_examples=100, deadline=None)

VERTICES = list("abcdefg")
EDGE_NAMES = [f"e{i}" for i in range(6)]
HYPERGRAPHS = st.dictionaries(
    st.sampled_from(EDGE_NAMES), st.frozensets(st.sampled_from(VERTICES), min_size=1, max_size=4),
    min_size=1, max_size=6,
).map(Hypergraph)
KINDS = ["AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq"]


def fresh_vertices(h: Hypergraph, n: int) -> list[str]:
    out: list[str] = []
    i = 0
    while len(out) < n:
        if f"n{i}" not in h.vertices:
            out.append(f"n{i}")
        i += 1
    return out


def fresh_edge_name(h: Hypergraph) -> str:
    return next(f"f{i}" for i in range(len(h) + 1) if f"f{i}" not in h.edge_names)


def nonempty_subset(data: st.DataObject, xs: frozenset[str]) -> frozenset[str]:
    return data.draw(st.frozensets(st.sampled_from(sorted(xs)), min_size=1))


def draw_modification(data: st.DataObject, h: Hypergraph, kind: str) -> Any:
    """A modification of class ``kind`` whose parameters are valid for ``h`` (h is non-empty)."""
    vs = h.vertices
    if kind == "AddVar":
        return AddVar(fresh_vertices(h, 1)[0], nonempty_subset(data, h.edge_names))
    if kind == "DelVar":
        return DelVar(data.draw(st.sampled_from(sorted(vs))))
    if kind == "AddConstr":
        pool = sorted(vs | set(fresh_vertices(h, 2)))
        return AddConstr(fresh_edge_name(h), data.draw(st.frozensets(st.sampled_from(pool), min_size=1)))
    if kind == "DelConstr":
        return DelConstr(data.draw(st.sampled_from(sorted(h.edge_names))))
    if kind == "AddEq":
        merge = nonempty_subset(data, vs)
        if len(merge) >= 2 and data.draw(st.booleans()):
            return AddEq(merge, data.draw(st.sampled_from(sorted(merge))))
        return AddEq(merge, fresh_vertices(h, 1)[0])
    assert kind == "DelEq"
    v = data.draw(st.sampled_from(sorted(vs)))
    inc = h.incident(v)
    keep = data.draw(st.booleans())
    n_new = data.draw(st.integers(1 if keep else 2, 3))
    keys = ([v] if keep else []) + fresh_vertices(h, n_new)
    parts = {k: set(nonempty_subset(data, inc)) for k in keys}
    for e in inc - set().union(*parts.values()):
        parts[data.draw(st.sampled_from(keys))].add(e)
    return DelEq(v, {k: fs(es) for k, es in parts.items()})


def check_invariants(r: ModificationResult, h: Hypergraph, snapshot: dict[str, frozenset[str]]) -> None:
    assert r.old is h and dict(h.edges) == snapshot                 # input untouched
    assert set(r.s_delta) == set(h.edge_names)
    image = [t for t in r.s_delta.values() if t is not None]
    assert len(image) == len(set(image))                             # injective
    assert set(image) <= r.new.edge_names
    assert r.new_edges == r.new.edge_names - set(image)
    assert r.new_vertices == r.new.vertices - h.vertices
    assert r.removed_vertices == h.vertices - r.new.vertices


@PROPS
@given(HYPERGRAPHS, st.sampled_from(KINDS), st.data())
def test_invariants_of_every_class(h: Hypergraph, kind: str, data: st.DataObject) -> None:
    snapshot = dict(h.edges)
    m = draw_modification(data, h, kind)
    r = m.apply(h)
    assert r.kind == kind
    check_invariants(r, h, snapshot)
    assert all(t is None or t == e for e, t in r.s_delta.items())   # names preserved
    # class-specific shape of the change
    if kind in ("AddVar", "AddEq", "DelEq"):
        assert r.removed_edges == set() and r.new_edges == set()
    if kind == "AddVar":
        assert r.new_vertices == {m.vertex}
        assert r.new.incident(m.vertex) == m.edges
    if kind == "DelVar":
        assert r.removed_vertices == {m.vertex} and r.new_edges == set()
        assert r.removed_edges == {e for e in h.edge_names if h.edge(e) == {m.vertex}}
    if kind == "AddConstr":
        assert r.new_edges == {m.name} and r.new.edge(m.name) == m.vertices
    if kind == "DelConstr":
        assert r.removed_edges == {m.name} and r.new_edges == set()
    if kind == "AddEq":
        assert r.removed_vertices == m.merge - {m.into}
        assert r.new.incident(m.into) == {e for e in h.edge_names if h.edge(e) & m.merge}
    if kind == "DelEq":
        for p, es in m.parts.items():
            assert r.new.incident(p) == es


@PROPS
@given(HYPERGRAPHS, st.data())
def test_addconstr_then_delconstr_is_identity(h: Hypergraph, data: st.DataObject) -> None:
    m = draw_modification(data, h, "AddConstr")
    r1 = m.apply(h)
    r2 = DelConstr(m.name).apply(r1.new)
    assert r2.new == h
    assert r2.removed_vertices == r1.new_vertices


@PROPS
@given(HYPERGRAPHS, st.data())
def test_addvar_then_delvar_is_identity(h: Hypergraph, data: st.DataObject) -> None:
    m = draw_modification(data, h, "AddVar")
    r1 = m.apply(h)
    r2 = DelVar(m.vertex).apply(r1.new)
    assert r2.new == h
    assert r2.removed_edges == set()


@PROPS
@given(HYPERGRAPHS, st.data())
def test_addeq_pair_then_deleq_is_identity(h: Hypergraph, data: st.DataObject) -> None:
    """AddEq({x, y}, x) is undone by DelEq(x, {x: I_H(x), y: I_H(y)}).

    Edge names are preserved (A9), so this holds even when the merge made two edges equal.
    """
    vs = sorted(h.vertices)
    if len(vs) < 2:
        return
    x, y = data.draw(st.lists(st.sampled_from(vs), min_size=2, max_size=2, unique=True))
    r1 = AddEq(fs({x, y}), x).apply(h)
    r2 = DelEq(x, {x: h.incident(x), y: h.incident(y)}).apply(r1.new)
    assert r2.new == h
    assert r2.new_vertices == {y}


@PROPS
@given(HYPERGRAPHS, st.lists(st.sampled_from(KINDS), min_size=1, max_size=5), st.data())
def test_compose_equals_stepwise_application(h: Hypergraph, kinds: list[str], data: st.DataObject) -> None:
    steps: list[Any] = []
    results: list[ModificationResult] = []
    cur = h
    for kind in kinds:
        if len(cur) == 0:
            kind = "AddConstr"                                         # only valid class on the empty hypergraph
        m = draw_modification(data, cur, kind)
        r = m.apply(cur)
        steps.append(m)
        results.append(r)
        cur = r.new
    seq = ModificationSequence(tuple(steps)).apply(h)
    composed = compose(results)
    assert seq == composed
    assert seq.kind == "Sequence" and seq.old is h and seq.new == cur
    check_invariants(seq, h, dict(h.edges))
    # composed s_delta equals the chained maps
    for e in h.edge_names:
        t: str | None = e
        for r in results:
            t = None if t is None else r.s_delta[t]
        assert seq.s_delta[e] == t
    assert seq.description == "; ".join(r.description for r in results)

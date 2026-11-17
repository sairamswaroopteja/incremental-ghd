"""S14: the §6.1 modification generator produces exactly the paper's shapes, deterministically."""

from __future__ import annotations

import math

import pytest

from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq

from benchmarks.generator import (
    ALL_CLASSES, PAPER_CLASSES, from_spec, generate, to_spec,
)
from benchmarks.loader import InstanceInfo, family_of, stats

# 6 vertices, 5 edges, 13 incidences: avg degree 13/6 = 2.17 -> 3 edges; avg rank 13/5 = 2.6 -> 3 vertices
H = Hypergraph({"e1": "abc", "e2": "cd", "e3": "def", "e4": "fa", "e5": "bdf"})


def info_of(h: Hypergraph, name: str = "toy.hg") -> InstanceInfo:
    nv, ne, rank, ad, ar = stats(h)
    return InstanceInfo(name, name, family_of(name), nv, ne, rank, ad, ar)


INFO = info_of(H)


def mods(cls: str, seed: int = 0, per_class: int = 25, h: Hypergraph = H, info: InstanceInfo = INFO):
    return [m for m in generate(h, info, seed, per_class, (cls,))]


def test_stats_arithmetic() -> None:
    assert (INFO.n_vertices, INFO.n_edges, INFO.rank) == (6, 5, 3)
    assert INFO.avg_degree == pytest.approx(13 / 6) and INFO.avg_rank == pytest.approx(13 / 5)


def test_addvar_fresh_vertex_into_ceil_avg_degree_edges() -> None:
    for m in mods("AddVar"):
        mod = from_spec(m.spec)
        assert isinstance(mod, AddVar)
        assert mod.vertex not in H.vertices
        assert len(mod.edges) == math.ceil(13 / 6) == 3
        assert mod.edges <= H.edge_names


def test_addvar_capped_at_number_of_edges() -> None:
    star = Hypergraph({"x": "ab", "y": "ac"})          # avg degree 4/3 -> 2 = |E|
    for m in mods("AddVar", h=star, info=info_of(star)):
        assert from_spec(m.spec).edges == star.edge_names


def test_addeq_merges_two_distinct_existing_vertices() -> None:
    for m in mods("AddEq"):
        mod = from_spec(m.spec)
        assert isinstance(mod, AddEq)
        assert len(mod.merge) == 2 and mod.merge <= H.vertices and mod.into in mod.merge


def test_deleq_splits_into_two_fresh_halves() -> None:
    for m in mods("DelEq"):
        mod = from_spec(m.spec)
        assert isinstance(mod, DelEq)
        inc = H.incident(mod.vertex)
        assert len(inc) >= 2
        (y1, a), (y2, b) = sorted(mod.parts.items())
        assert y1 not in H.vertices and y2 not in H.vertices and y1 != y2
        assert a | b == inc and not (a & b)                        # a partition of x's edges
        assert sorted((len(a), len(b))) == [len(inc) // 2, len(inc) - len(inc) // 2]


def test_deleq_redraws_degree_one_vertices_and_counts_them() -> None:
    # only 'b' has degree 2; every other draw must be redrawn and counted
    h = Hypergraph({"e1": "ab", "e2": "bc"})
    ms = mods("DelEq", h=h, info=info_of(h), per_class=10)
    assert all(from_spec(m.spec).vertex == "b" for m in ms)
    assert sum(m.redraws for m in ms) > 0
    assert all(set(m.redraw_reasons) <= {"DelEq: drawn vertex has degree < 2 (a half would receive no edge)"}
               for m in ms)


def test_deleq_not_applicable_is_reported_not_dropped() -> None:
    h = Hypergraph({"e1": "ab", "e2": "cd"})
    ms = mods("DelEq", h=h, info=info_of(h), per_class=5)
    assert len(ms) == 5 and all(m.spec is None and m.failure.startswith("not applicable") for m in ms)


def test_addconstr_uses_existing_vertices_and_ceil_avg_rank() -> None:
    for m in mods("AddConstr"):
        mod = from_spec(m.spec)
        assert isinstance(mod, AddConstr)
        assert mod.name not in H.edge_names
        assert mod.vertices <= H.vertices
        assert len(mod.vertices) == math.ceil(13 / 5) == 3
        assert mod.vertices not in set(H.edges.values())          # duplicates are redrawn


def test_addconstr_duplicate_scope_is_redrawn() -> None:
    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "ac"})          # every 2-subset is an edge
    ms = mods("AddConstr", h=h, info=info_of(h), per_class=3)
    assert all(m.spec is None and "no valid draw" in m.failure for m in ms)
    assert all(m.redraw_reasons == {"AddConstr scope equals an existing edge": m.redraws} for m in ms)


def test_delconstr_deletes_an_existing_edge() -> None:
    for m in mods("DelConstr"):
        mod = from_spec(m.spec)
        assert isinstance(mod, DelConstr) and mod.name in H.edge_names


def test_five_per_class_and_determinism() -> None:
    a = generate(H, INFO, 7, 5)
    b = generate(H, INFO, 7, 5)
    assert [m.to_dict() for m in a] == [m.to_dict() for m in b]
    assert [m.mod_class for m in a] == [c for c in PAPER_CLASSES for _ in range(5)]
    assert "DelVar" not in {m.mod_class for m in a}
    c = generate(H, INFO, 8, 5)
    assert [m.spec for m in a] != [m.spec for m in c]
    # each class has its own stream: generating one class alone gives the same draws
    alone = generate(H, INFO, 7, 5, ("DelEq",))
    assert [m.spec for m in alone] == [m.spec for m in a if m.mod_class == "DelEq"]


def test_every_generated_modification_applies_and_round_trips() -> None:
    for m in generate(H, INFO, 3, 5, ALL_CLASSES):
        mod = from_spec(m.spec)
        assert to_spec(mod) == m.spec
        assert mod.apply(H).description == m.description


def test_family_names() -> None:
    assert family_of("Kakuro-easy-001-ext.xml.hg") == "Kakuro"
    assert family_of("rand_q0040.hg") == "rand_q"
    assert family_of("rand-3-20-20-60-632-24.xml.hg") == "rand"
    assert family_of("2bitcomp_5.hg") == "other"

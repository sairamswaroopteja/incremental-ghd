"""S2: the six elementary modifications (paper Defs 3.2-3.4, Example 3.5; PAPER_ANALYSIS A5-A9)."""

from __future__ import annotations

from typing import Any

import pytest

from ighd.common.config import InducedComparison
from ighd.common.errors import InvalidModificationError
from ighd.hypergraph import Hypergraph, induced_equal
from ighd.modifications import (
    AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar, ModificationResult, ModificationSequence, compose,
)
from tests.fixtures.expected import T_STAR_CASES
from tests.fixtures.paper import H_P, H_P2, H_P3, H_PP

fs = frozenset
CLASSES: dict[str, Any] = {c.__name__: c for c in (AddVar, DelVar, AddConstr, DelConstr, AddEq, DelEq)}


def check_invariants(r: ModificationResult) -> None:
    """The ModificationResult invariants (base.py), recomputed independently."""
    assert set(r.s_delta) == set(r.old.edge_names)
    image = [t for t in r.s_delta.values() if t is not None]
    assert len(image) == len(set(image))
    assert set(image) <= r.new.edge_names
    assert all(t is None or t == e for e, t in r.s_delta.items())     # names preserved
    assert r.new_edges == r.new.edge_names - set(image)
    assert r.new_vertices == r.new.vertices - r.old.vertices
    assert r.removed_vertices == r.old.vertices - r.new.vertices
    assert r.removed_edges == {e for e, t in r.s_delta.items() if t is None}
    assert isinstance(r.description, str) and r.description


def identity(h: Hypergraph) -> dict[str, str]:
    return {e: e for e in h.edge_names}


# ------------------------------------------------------------------- paper Example 3.5
def test_ex35_addvar_h() -> None:
    r = AddVar("h", fs({"w2", "w5"})).apply(Hypergraph(H_P))
    check_invariants(r)
    assert r.kind == "AddVar"
    assert r.new == Hypergraph(H_PP)
    assert r.new_vertices == {"h"} and r.removed_vertices == set() and r.new_edges == set()
    assert dict(r.s_delta) == identity(Hypergraph(H_P))


def test_ex35_delvar_h() -> None:
    r = DelVar("h").apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.kind == "DelVar"
    assert r.new == Hypergraph(H_P)
    assert r.removed_vertices == {"h"} and r.new_vertices == set()
    assert dict(r.s_delta) == identity(Hypergraph(H_PP))


def test_ex35_addconstr_w7() -> None:
    r = AddConstr("w7", fs("ci")).apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new == Hypergraph(H_P2)
    assert r.new_edges == {"w7"} and r.new_vertices == set() and r.removed_vertices == set()


def test_ex35_delconstr_w7() -> None:
    r = DelConstr("w7").apply(Hypergraph(H_P2))
    check_invariants(r)
    assert r.new == Hypergraph(H_PP)
    assert r.s_delta["w7"] is None and r.removed_edges == {"w7"}
    assert r.removed_vertices == set()


def test_ex35_addeq_b_into_g() -> None:
    r = AddEq(fs("bg"), "g").apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new == Hypergraph(H_P3)
    assert r.new_vertices == set() and r.removed_vertices == {"b"}
    assert dict(r.s_delta) == identity(Hypergraph(H_PP))


def test_ex35_deleq_g() -> None:
    r = DelEq("g", {"g": fs({"w2"}), "b": fs({"w1"})}).apply(Hypergraph(H_P3))
    check_invariants(r)
    assert r.new == Hypergraph(H_PP)
    assert r.new_vertices == {"b"} and r.removed_vertices == set()


def test_edgewise_comparison_accepts_s_delta() -> None:
    """s_delta is directly usable by ighd.hypergraph.compare (D21)."""
    r = AddVar("h", fs({"w2", "w5"})).apply(Hypergraph(H_P))
    assert induced_equal(r.old, r.new, fs("abcdeijkl"), r.s_delta, InducedComparison.EDGEWISE)
    assert not induced_equal(r.old, r.new, fs("fgh"), r.s_delta, InducedComparison.EDGEWISE)


# ------------------------------------------------------------------- T* cases (S9 inputs)
EXPECTED_NEW_VERTICES = {"addvar_m": {"m"}, "deleq_g": {"b"}, "addvar_h_jointree": {"h"}}


@pytest.mark.parametrize("case", T_STAR_CASES, ids=[c[0] for c in T_STAR_CASES])
def test_t_star_case_modifications_apply(case: tuple[Any, ...]) -> None:
    case_id, base, _spec, (cls, kwargs), _t_star, _prov = case
    r = CLASSES[cls](**kwargs).apply(Hypergraph(base))
    check_invariants(r)
    assert r.kind == cls
    assert r.new_vertices == EXPECTED_NEW_VERTICES.get(case_id, set())


# ------------------------------------------------------------------- edge cases
def test_delvar_empties_singleton_edge() -> None:
    """A6: an edge equal to {v} is deleted."""
    h = Hypergraph({"e1": {"v"}, "e2": {"v", "a"}, "e3": {"a", "b"}})
    r = DelVar("v").apply(h)
    check_invariants(r)
    assert r.s_delta == {"e1": None, "e2": "e2", "e3": "e3"}
    assert r.new == Hypergraph({"e2": {"a"}, "e3": {"a", "b"}})
    assert r.removed_edges == {"e1"} and "A6" in r.description


def test_delvar_can_create_duplicate_edges() -> None:
    h = Hypergraph({"e1": {"a", "v"}, "e2": {"a"}})
    r = DelVar("v").apply(h)
    check_invariants(r)
    assert r.new == Hypergraph({"e1": {"a"}, "e2": {"a"}})
    assert r.new.has_duplicate_edges() and "A9" in r.description


def test_delconstr_w6_removes_j_and_l() -> None:
    """A7: j and l lie only in w6 and vanish with it (k is still in w3)."""
    r = DelConstr("w6").apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.removed_vertices == {"j", "l"}
    assert "k" in r.new.vertices
    assert r.new == Hypergraph({n: vs for n, vs in H_PP.items() if n != "w6"})


def test_addeq_two_edges_become_equal() -> None:
    """A9: merging b, c in {a,b}, {a,c} keeps both names with equal vertex sets."""
    h = Hypergraph({"e1": {"a", "b"}, "e2": {"a", "c"}})
    r = AddEq(fs("bc"), "b").apply(h)
    check_invariants(r)
    assert r.new.edge_names == {"e1", "e2"}
    assert r.new.edge("e1") == r.new.edge("e2") == {"a", "b"}
    assert r.new.has_duplicate_edges()
    assert "A9" in r.description and "e1=e2" in r.description
    assert r.removed_vertices == {"c"}


def test_addeq_into_fresh_vertex() -> None:
    r = AddEq(fs("bg"), "x").apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new_vertices == {"x"} and r.removed_vertices == {"b", "g"}
    assert r.new.edge("w1") == {"a", "c", "x"} and r.new.edge("w2") == {"f", "h", "x"}


def test_addeq_single_vertex_into_fresh_is_a_rename() -> None:
    r = AddEq(fs("b"), "x").apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new_vertices == {"x"} and r.removed_vertices == {"b"}


def test_addconstr_with_fresh_vertices() -> None:
    r = AddConstr("w7", fs({"x", "y"})).apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new_edges == {"w7"} and r.new_vertices == {"x", "y"}
    assert r.new.edge("w7") == {"x", "y"}


def test_addconstr_partly_fresh_vertices() -> None:
    r = AddConstr("w7", fs({"a", "x"})).apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new_vertices == {"x"}


def test_addconstr_duplicate_vertex_set_is_allowed() -> None:
    r = AddConstr("w7", fs("abc")).apply(Hypergraph(H_PP))
    check_invariants(r)
    assert r.new.has_duplicate_edges()
    assert "w1" in r.description and "A9" in r.description


def test_deleq_both_parts_new_removes_vertex() -> None:
    r = DelEq("g", {"x": fs({"w2"}), "y": fs({"w1"})}).apply(Hypergraph(H_P3))
    check_invariants(r)
    assert r.new_vertices == {"x", "y"} and r.removed_vertices == {"g"}


def test_deleq_edge_may_receive_several_parts() -> None:
    h = Hypergraph({"e1": {"a", "v"}, "e2": {"v", "b"}})
    r = DelEq("v", {"v": fs({"e1", "e2"}), "w": fs({"e2"})}).apply(h)
    check_invariants(r)
    assert r.new == Hypergraph({"e1": {"a", "v"}, "e2": {"v", "w", "b"}})


def test_input_hypergraph_is_unchanged() -> None:
    h = Hypergraph(H_PP)
    snapshot = dict(h.edges)
    for m in (AddVar("x", fs({"w1"})), DelVar("a"), AddConstr("w9", fs("ab")), DelConstr("w1"),
              AddEq(fs("ab"), "a"), DelEq("a", {"a": fs({"w1"}), "z": fs({"w4"})})):
        r = m.apply(h)
        assert r.old is h
    assert dict(h.edges) == snapshot and h == Hypergraph(H_PP)


def test_s_delta_is_read_only() -> None:
    r = DelConstr("w1").apply(Hypergraph(H_PP))
    with pytest.raises(TypeError):
        r.s_delta["w1"] = "w2"  # type: ignore[index]


# ------------------------------------------------------------------- error conditions
HPP = Hypergraph(H_PP)

ERROR_CASES: list[tuple[str, Any, str]] = [
    ("addvar_existing_vertex", AddVar("a", fs({"w1"})), "already in V"),
    ("addvar_empty_edges", AddVar("x", fs()), "empty"),
    ("addvar_unknown_edge", AddVar("x", fs({"w1", "nope"})), "nope"),
    ("delvar_unknown_vertex", DelVar("x"), "not in V"),
    ("addconstr_existing_name", AddConstr("w1", fs("ab")), "already in E"),
    ("addconstr_empty", AddConstr("w9", fs()), "no vertices"),
    ("delconstr_unknown", DelConstr("w9"), "w9"),
    ("addeq_empty_merge", AddEq(fs(), "a"), "empty"),
    ("addeq_merge_not_in_v", AddEq(fs({"a", "zz"}), "a"), "zz"),
    ("addeq_into_existing_outside_merge", AddEq(fs("ab"), "c"), "not in the merge set"),
    ("addeq_noop", AddEq(fs("a"), "a"), "no-op"),
    ("deleq_unknown_vertex", DelEq("x", {"x": fs({"w1"}), "y": fs({"w1"})}), "not in V"),
    ("deleq_one_part", DelEq("a", {"a": fs({"w1", "w4"})}), "at least 2"),
    ("deleq_empty_part", DelEq("a", {"a": fs({"w1", "w4"}), "x": fs()}), "receives no edge"),
    ("deleq_non_incident_edge", DelEq("a", {"a": fs({"w1", "w4"}), "x": fs({"w2"})}), "not incident"),
    ("deleq_uncovered_edge", DelEq("a", {"a": fs({"w1"}), "x": fs({"w1"})}), "receive no part"),
    ("deleq_part_existing_vertex", DelEq("a", {"a": fs({"w1"}), "b": fs({"w4"})}), "already in V"),
    ("addvar_non_str_vertex", AddVar(3, fs({"w1"})), "not a str"),  # type: ignore[arg-type]
]


@pytest.mark.parametrize("mod,match", [c[1:] for c in ERROR_CASES], ids=[c[0] for c in ERROR_CASES])
def test_invalid_parameters_raise(mod: Any, match: str) -> None:
    with pytest.raises(InvalidModificationError, match=match):
        mod.apply(HPP)
    assert HPP == Hypergraph(H_PP)


# ------------------------------------------------------------------- sequences
def test_sequence_ex35_round_trip() -> None:
    """H_P -> AddVar h -> AddConstr w7 -> DelConstr w7 -> DelVar h is the identity on H_P."""
    seq = ModificationSequence((AddVar("h", fs({"w2", "w5"})), AddConstr("w7", fs("ci")),
                                DelConstr("w7"), DelVar("h")))
    r = seq.apply(Hypergraph(H_P))
    check_invariants(r)
    assert r.kind == "Sequence"
    assert r.new == Hypergraph(H_P)
    assert r.new_vertices == set() and r.removed_vertices == set() and r.new_edges == set()
    assert dict(r.s_delta) == identity(Hypergraph(H_P))
    assert r.description.count("; ") >= 3


def test_compose_chains_deletions() -> None:
    h = Hypergraph(H_PP)
    r1 = DelVar("j").apply(h)
    r2 = DelConstr("w6").apply(r1.new)
    r3 = AddConstr("w6", fs("xy")).apply(r2.new)
    r = compose([r1, r2, r3])
    check_invariants(r)
    assert r.s_delta["w6"] is None          # deleted at step 2; the new w6 is a different edge
    assert r.new_edges == {"w6"}
    assert r.new_vertices == {"x", "y"} and r.removed_vertices == {"j", "l"}


def test_compose_rejects_empty_and_broken_chain() -> None:
    with pytest.raises(ValueError, match="empty"):
        compose([])
    r1 = DelVar("h").apply(Hypergraph(H_PP))
    r2 = DelVar("h").apply(Hypergraph(H_PP))
    with pytest.raises(ValueError, match="does not end"):
        compose([r1, r2])


def test_empty_sequence_raises() -> None:
    with pytest.raises(InvalidModificationError, match="no steps"):
        ModificationSequence(()).apply(HPP)


def test_sequence_accepts_list_of_steps() -> None:
    seq = ModificationSequence([DelVar("h")])  # type: ignore[arg-type]
    assert isinstance(seq.steps, tuple)
    assert seq.apply(Hypergraph(H_PP)).new == Hypergraph(H_P)

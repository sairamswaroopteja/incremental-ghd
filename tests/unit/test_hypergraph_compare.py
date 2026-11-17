"""S1: comparing induced subhypergraphs across a modification (PAPER_ANALYSIS A2, ledger L-A2)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.common.config import InducedComparison
from ighd.hypergraph import Hypergraph, InducedDiff, induced_diff, induced_equal
from tests.fixtures.paper import H_P2, H_PP

fs = frozenset
EDGEWISE, SET = InducedComparison.EDGEWISE, InducedComparison.SET
BOTH = [EDGEWISE, SET]
PROPS = settings(derandomize=True, max_examples=200, deadline=None)

EX43_S_DELTA = {**{f"w{i}": f"w{i}" for i in range(1, 7)}, "w7": None}
"""Example 4.3: DelConstr(w7) on H_P2 gives H_P'."""


# ------------------------------------------------------------------- paper Example 4.3
@pytest.mark.parametrize("mode", BOTH)
def test_ex43_equal_on_adfgh(mode: InducedComparison) -> None:
    old, new = Hypergraph(H_P2), Hypergraph(H_PP)
    d = induced_diff(old, new, set("adfgh"), EX43_S_DELTA, mode)
    assert d.equal and d == InducedDiff((), (), ())
    assert induced_equal(old, new, set("adfgh"), EX43_S_DELTA, mode)


@pytest.mark.parametrize("mode", BOTH)
def test_ex43_not_equal_on_abcdefgh(mode: InducedComparison) -> None:
    old, new = Hypergraph(H_P2), Hypergraph(H_PP)
    assert not induced_equal(old, new, set("abcdefgh"), EX43_S_DELTA, mode)


def test_ex43_edgewise_diff_names_w7() -> None:
    d = induced_diff(Hypergraph(H_P2), Hypergraph(H_PP), set("abcdefgh"), EX43_S_DELTA, EDGEWISE)
    assert d.changed == (("w7", fs({"c"}), fs()),)
    assert d.only_old == () and d.only_new == ()


def test_ex43_set_diff() -> None:
    d = induced_diff(Hypergraph(H_P2), Hypergraph(H_PP), set("abcdefgh"), EX43_S_DELTA, SET)
    assert d.changed == ()
    assert d.only_old == (fs({"c"}),) and d.only_new == ()


# ------------------------------------------------------------------- A2 counterexample
@pytest.mark.paper_discrepancy
def test_a2_counterexample_edgewise_vs_set() -> None:
    """A2: H = {e: {y,z}} and delta(H) = {f1: {y}, f2: {z}} (e deleted, f1, f2 added).

    For U = {y} (or {z}) the SETS of restrictions agree ({{y}} on both sides), but edge by edge
    they do not: e & U = {y} while e has no counterpart, and the new edge f1 meets U. For
    U = {y,z} both readings see a difference. Lemma 4.4's proof takes the union of the
    agreeing parts H[X1] = delta(H)[X1] and H[X2] = delta(H)[X2] to get agreement on X1 | X2;
    under SET that step is false here (equal on {y} and on {z}, unequal on {y,z}), whereas
    EDGEWISE agreement is closed under union of the vertex sets. Hence the edge-wise reading.
    """
    old, new = Hypergraph({"e": "yz"}), Hypergraph({"f1": "y", "f2": "z"})
    s = {"e": None}
    for u in ({"y"}, {"z"}):
        assert induced_equal(old, new, u, s, SET)
        assert not induced_equal(old, new, u, s, EDGEWISE)
    for mode in BOTH:
        assert not induced_equal(old, new, {"y", "z"}, s, mode)
    d = induced_diff(old, new, {"y"}, s, EDGEWISE)
    assert d.changed == (("e", fs("y"), fs()), ("f1", fs(), fs("y")))
    d = induced_diff(old, new, {"y", "z"}, s, SET)
    assert d.only_old == (fs("yz"),) and d.only_new == (fs("y"), fs("z"))


# ------------------------------------------------------------------- errors
@pytest.mark.parametrize("s_delta,match", [
    ({"w1": "w1"}, "lacks"),
    ({**EX43_S_DELTA, "w8": None}, "w8"),
    ({**EX43_S_DELTA, "w1": "w99"}, "w99"),
    ({**EX43_S_DELTA, "w7": "w7"}, "w7"),
])
@pytest.mark.parametrize("mode", BOTH)
def test_bad_s_delta(s_delta: dict, match: str, mode: InducedComparison) -> None:
    with pytest.raises(ValueError, match=match):
        induced_diff(Hypergraph(H_P2), Hypergraph(H_PP), set("a"), s_delta, mode)


def test_empty_hypergraphs_and_empty_u() -> None:
    e = Hypergraph({})
    for mode in BOTH:
        assert induced_equal(e, e, {"a"}, {}, mode)
        assert induced_equal(Hypergraph(H_P2), Hypergraph(H_PP), set(), EX43_S_DELTA, mode)
    assert not induced_equal(e, Hypergraph({"f": "a"}), {"a"}, {}, EDGEWISE)


def test_renamed_edge_identity() -> None:
    """s_delta may map an edge to a differently named one; EDGEWISE follows it."""
    old, new = Hypergraph({"e": "ab"}), Hypergraph({"g": "ab"})
    assert induced_equal(old, new, "ab", {"e": "g"}, EDGEWISE)
    assert not induced_equal(old, new, "ab", {"e": None}, EDGEWISE)
    assert induced_equal(old, new, "ab", {"e": None}, SET)


# ------------------------------------------------------------------- properties
VERTICES = st.sampled_from(list("abcdefgh"))
EDGE_DICTS = st.dictionaries(st.sampled_from([f"e{i}" for i in range(6)]),
                             st.frozensets(VERTICES, min_size=1, max_size=4), max_size=6)


@PROPS
@given(EDGE_DICTS, st.frozensets(VERTICES))
def test_identity_edgewise_equal(edges: dict[str, frozenset[str]], u: frozenset[str]) -> None:
    h = Hypergraph(edges)
    s = {e: e for e in h}
    for mode in BOTH:
        assert induced_diff(h, h, u, s, mode) == InducedDiff((), (), ())


@st.composite
def modifications(draw: st.DrawFn) -> tuple[Hypergraph, Hypergraph, dict[str, str | None], frozenset[str]]:
    """A random hypergraph, a random perturbation of it with a consistent s_delta, and a U."""
    old = draw(EDGE_DICTS)
    new: dict[str, frozenset[str]] = {}
    s_delta: dict[str, str | None] = {}
    for i, (name, vs) in enumerate(sorted(old.items())):
        action = draw(st.sampled_from(["keep", "keep", "modify", "delete", "rename"]))
        if action == "delete":
            s_delta[name] = None
            continue
        if action == "modify":
            vs = (vs | draw(st.frozensets(VERTICES, max_size=2))) - draw(st.frozensets(VERTICES, max_size=2))
            if not vs:
                s_delta[name] = None
                continue
        target = f"r{i}" if action == "rename" else name
        new[target] = vs
        s_delta[name] = target
    for j in range(draw(st.integers(0, 2))):
        new[f"n{j}"] = draw(st.frozensets(VERTICES, min_size=1, max_size=3))
    u = draw(st.frozensets(VERTICES, max_size=4))
    return Hypergraph(old), Hypergraph(new), s_delta, u


@PROPS
@given(modifications())
def test_edgewise_equal_implies_set_equal(case: tuple[Hypergraph, Hypergraph, dict, frozenset[str]]) -> None:
    old, new, s, u = case
    ew = induced_diff(old, new, u, s, EDGEWISE)
    st_ = induced_diff(old, new, u, s, SET)
    assert ew.only_old == ew.only_new == () and st_.changed == ()
    if ew.equal:
        assert st_.equal
    # Edge-wise agreement on U implies agreement on every subset of U.
    if ew.equal and u:
        sub = frozenset(sorted(u)[:-1])
        assert induced_equal(old, new, sub, s, EDGEWISE)

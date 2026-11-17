"""S5: brute-force delta-mutable subtrees (Def 4.1; Lemma 4.4; A2).

ModificationResults are built by hand here, so the oracle is checked independently of
ighd.modifications.ops.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Mapping

import pytest

from ighd.common.config import PAPER_DEFAULT, InducedComparison, Semantics
from ighd.common.errors import InvalidModificationError, OracleTooLargeError
from ighd.ghd.tree import GHD
from ighd.hypergraph.core import Hypergraph
from ighd.modifications.base import ModificationResult
from ighd.oracle.brute_mutable import MAX_BRUTE_NODES, all_mutable_subtrees
from ighd.oracle.ghw_dp import exact_ghw
from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, H_P2, H_PP

fs = frozenset
EDGEWISE = Semantics(induced_comparison=InducedComparison.EDGEWISE)
SET = Semantics(induced_comparison=InducedComparison.SET)


def change(old: Mapping, new: Mapping, s_delta: Mapping[str, str | None] | None = None,
           kind: str = "hand") -> ModificationResult:
    """A ModificationResult derived from the definitions (s_delta defaults to the identity on
    surviving names, None for vanished names)."""
    ho, hn = Hypergraph(old), Hypergraph(new)
    if s_delta is None:
        s_delta = {e: (e if e in hn.edge_names else None) for e in ho.edge_names}
    image = {t for t in s_delta.values() if t is not None}
    return ModificationResult(
        kind=kind, old=ho, new=hn, s_delta=dict(s_delta),
        new_edges=fs(hn.edge_names - image),
        new_vertices=hn.vertices - ho.vertices,
        removed_vertices=ho.vertices - hn.vertices,
        description=kind,
    )


def labels(g: GHD, nodes: frozenset[int]) -> frozenset[str]:
    return fs(g.node(u).label for u in nodes)  # type: ignore[misc]


def minima(found: list[frozenset[int]]) -> list[frozenset[int]]:
    k = len(found[0])
    return [t for t in found if len(t) == k]


# ------------------------------------------------------------------ paper / guide cases
EX43 = (change(H_P2, H_PP), G2_SPEC, fs({"u1", "u2"}))
ADDVAR_M = (change(H_PP, {**H_PP, "w6": fs("jklm")}), G_PRIME_SPEC, fs({"t1", "t4"}))
ADDCONSTR_W7 = (change(H_PP, {**H_PP, "w7": fs("ci")}), G_PRIME_SPEC, fs({"t1", "t2"}))
CASES = {"ex43_delconstr": EX43, "addvar_m": ADDVAR_M, "addconstr_w7": ADDCONSTR_W7}


@pytest.mark.parametrize("name", sorted(CASES))
def test_unique_minimum_matches_expected(name: str) -> None:
    ch, spec, expected_labels = CASES[name]
    g = GHD.from_spec(spec)
    found = all_mutable_subtrees(ch, g)
    mins = minima(found)
    assert len(mins) == 1, mins
    assert labels(g, mins[0]) == expected_labels
    assert fs(g.node_ids()) in found          # whole tree: X is empty
    assert fs() not in found                  # the change is visible from every bag set


@pytest.mark.parametrize("name", sorted(CASES))
def test_set_and_edgewise_agree_on_paper_cases(name: str) -> None:
    ch, spec, _ = CASES[name]
    g = GHD.from_spec(spec)
    assert all_mutable_subtrees(ch, g, SET) == all_mutable_subtrees(ch, g, EDGEWISE)
    assert all_mutable_subtrees(ch, g) == all_mutable_subtrees(ch, g, PAPER_DEFAULT)


def test_ex43_full_family() -> None:
    """Every connected superset of {u1, u2}, and nothing else."""
    ch, spec, _ = EX43
    g = GHD.from_spec(spec)
    got = {labels(g, t) for t in all_mutable_subtrees(ch, g)}
    assert got == {fs({"u1", "u2"}), fs({"u1", "u2", "u3"}), fs({"u1", "u2", "u4"}),
                   fs({"u1", "u2", "u3", "u4"})}


def test_output_order() -> None:
    ch, spec, _ = EX43
    found = all_mutable_subtrees(ch, GHD.from_spec(spec))
    assert found == sorted(found, key=lambda t: (len(t), sorted(t)))


# ------------------------------------------------------------------ edge cases
def test_identity_change_makes_empty_set_mutable() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    found = all_mutable_subtrees(change(H_PP, H_PP), g)
    assert found[0] == fs()
    assert len(found) == sum(1 for k in range(5) for c in itertools.combinations(g.node_ids(), k)
                             if g.is_connected(c))


def test_fresh_edge_of_new_vertices_gives_empty_t_star() -> None:
    """A12: an added edge made only of fresh vertices is invisible from every bag."""
    g = GHD.from_spec(G_PRIME_SPEC)
    found = all_mutable_subtrees(change(H_PP, {**H_PP, "w9": fs("xy")}), g)
    assert found[0] == fs()


def test_condition_ii_alone() -> None:
    """AddVar m into w6: for T* = {t4}, (i) holds (w6 & X = {k} before and after) but (ii)
    fails, since m shares w6 with k, which t1 still shows."""
    ch, spec, _ = ADDVAR_M
    g = GHD.from_spec(spec)
    t4 = fs({g.by_label("t4")})
    assert t4 not in all_mutable_subtrees(ch, g)   # k is still visible in t1


def test_size_guard() -> None:
    g = GHD()
    r = g.add_node("a", ["e"])
    for _ in range(MAX_BRUTE_NODES):
        g.add_node("a", ["e"], parent=r)
    with pytest.raises(OracleTooLargeError):
        all_mutable_subtrees(change({"e": "a"}, {"e": "a"}), g)


def test_malformed_change_rejected() -> None:
    g = GHD.from_spec(G_PRIME_SPEC)
    good = change(H_PP, {**H_PP, "w6": fs("jklm")})
    bad = ModificationResult(kind="x", old=good.old, new=good.new, s_delta=good.s_delta,
                             new_edges=good.new_edges, new_vertices=fs(), removed_vertices=fs(),
                             description="")
    with pytest.raises(InvalidModificationError):
        all_mutable_subtrees(bad, g)
    bad2 = ModificationResult(kind="x", old=good.old, new=good.new, s_delta={"w1": "w1"},
                              new_edges=fs(), new_vertices=fs("m"), removed_vertices=fs(), description="")
    with pytest.raises(InvalidModificationError):
        all_mutable_subtrees(bad2, g)


# ------------------------------------------------------------------ A2: SET vs EDGEWISE differ
def test_a2_duplicate_constraint_differs() -> None:
    """AddConstr of a copy of w3 = {e,i,k}. SET: the restriction of the copy always equals that of
    w3, so the empty set is mutable. EDGEWISE: the new edge must miss X, so T* must hide e, i, k."""
    g = GHD.from_spec(G_PRIME_SPEC)
    ch = change(H_PP, {**H_PP, "w7": fs("eik")})
    set_found = all_mutable_subtrees(ch, g, SET)
    edge_found = all_mutable_subtrees(ch, g, EDGEWISE)
    assert set_found[0] == fs()
    assert minima(edge_found) == [fs({g.by_label("t1"), g.by_label("t4")})]
    assert set(edge_found) < set(set_found)


def test_a2_swapped_names_differ() -> None:
    """delta swaps the vertex sets of e1 = {a,b} and e2 = {b,c} (an arbitrary delta, Def 3.1)."""
    g = GHD()
    r = g.add_node("ab", ["e1"])
    g.add_node("bc", ["e2"], parent=r)
    ch = change({"e1": "ab", "e2": "bc"}, {"e1": "bc", "e2": "ab"})
    assert all_mutable_subtrees(ch, g, SET)[0] == fs()
    assert all_mutable_subtrees(ch, g, EDGEWISE) == [fs({0, 1})]


def test_a2_set_reading_can_lose_unique_minimum() -> None:
    """Lemma 4.4's union step fails under SET (PAPER_ANALYSIS A2 counterexample shape).

    old: p={x,y,z}, q={y}, r={z}; new: p={x}, q={y,z}, r={z}. Tree a{y} - b{x,y,z} - c{z}.
    T*={a,b} leaves X={z}: SET {{z}} = {{z}}. T*={b,c} leaves X={y}: SET {{y}} = {{y}}.
    Their intersection {b} leaves X={y,z}: old {yz, y, z} vs new {yz, z} -- not mutable.
    So SET has two incomparable minima; EDGEWISE (p changes on any non-empty X) only the whole tree.
    """
    old = {"p": "xyz", "q": "y", "r": "z"}
    new = {"p": "x", "q": "yz", "r": "z"}
    g = GHD()
    a = g.add_node("y", ["q"])
    b = g.add_node("xyz", ["p"], parent=a)
    c = g.add_node("z", ["r"], parent=b)
    ch = change(old, new)
    set_found = all_mutable_subtrees(ch, g, SET)
    assert set_found == [fs({a, b}), fs({b, c}), fs({a, b, c})]
    assert all_mutable_subtrees(ch, g, EDGEWISE) == [fs({a, b, c})]


# ------------------------------------------------------------------ Lemma 4.4 on random instances
def _random_case(rng: random.Random) -> tuple[ModificationResult, GHD]:
    """A random hypergraph, its exact_ghw witness, and a light random delta: most edges kept,
    some deleted, some perturbed by one vertex (possibly a fresh one), maybe one new edge."""
    n = rng.randint(4, 7)
    vs = "abcdefg"[:n]
    old = {f"e{i}": rng.sample(vs, rng.randint(1, 3)) for i in range(rng.randint(3, 6))}
    pool = vs + "xy"
    new: dict[str, list[str]] = {}
    for e, members in old.items():
        roll = rng.random()
        if roll < 0.7:
            new[e] = members
        elif roll < 0.78:
            continue  # deleted
        elif len(members) > 1 and rng.random() < 0.5:
            drop = rng.choice(members)
            new[e] = [v for v in members if v != drop]
        else:
            new[e] = sorted(set(members) | {rng.choice(pool)})
    if rng.random() < 0.3:
        new["f0"] = rng.sample(pool, rng.randint(1, 3))
    _, g = exact_ghw(Hypergraph(old))
    return change(old, new, kind="random"), g


def _connected_supersets(g: GHD, base: frozenset[int]) -> set[frozenset[int]]:
    ids = g.node_ids()
    out = set()
    for k in range(len(ids) + 1):
        for c in itertools.combinations(ids, k):
            s = fs(c)
            if base <= s and g.is_connected(s):
                out.add(s)
    return out


@pytest.mark.parametrize("seed", range(60))
def test_lemma_4_4_edgewise_family_is_upward_closure_of_unique_minimum(seed: int) -> None:
    """EDGEWISE mutability is closed under intersection (X(T1 & T2) = X(T1) | X(T2) and edgewise
    equality is preserved by unions of X) and under connected supersets, so the family equals the
    connected supersets of a unique minimum (Lemma 4.4)."""
    ch, g = _random_case(random.Random(seed))
    found = all_mutable_subtrees(ch, g, EDGEWISE)
    assert fs(g.node_ids()) in found
    assert len(minima(found)) == 1
    assert set(found) == _connected_supersets(g, found[0])
    # EDGEWISE implies SET (equal named restrictions give equal sets)
    assert set(found) <= set(all_mutable_subtrees(ch, g, SET))


def test_random_search_for_a2_divergence() -> None:
    """A2 (c): seeded search for instances where SET and EDGEWISE give different families."""
    diverging = 0
    for seed in range(200):
        ch, g = _random_case(random.Random(seed))
        if all_mutable_subtrees(ch, g, SET) != all_mutable_subtrees(ch, g, EDGEWISE):
            diverging += 1
    assert diverging > 0

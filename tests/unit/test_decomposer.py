"""Unit tests for the S7 top-down decomposer (MATHEMATICAL_INVARIANTS §2, Algorithm 1)."""

from __future__ import annotations

import sys

import pytest

from ighd.common import Budget, DecomposerMode, SearchStatus
from ighd.ghd.normal_form import check_normal_form
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.static.decomposer import DecompositionTask, TopDownDecomposer, ghw_by_search
from tests.fixtures.expected import GHW
from tests.fixtures.paper import H_P, H_P2, H_P3, H_PP

fs = frozenset
EXACT = TopDownDecomposer(DecomposerMode.EXACT)
HEUR = TopDownDecomposer(DecomposerMode.HEURISTIC)
HPP = Hypergraph(H_PP)
PAPER_HS = {"H_P": H_P, "H_PP": H_PP, "H_P2": H_P2, "H_P3": H_P3}


def bags_containing(g: GHD, vs: frozenset[str]) -> list[int]:
    return [n.id for n in g if vs <= n.bag]


# --- paper hypergraphs ------------------------------------------------------------------------
def test_hpp_k1_proven_no_k2_found() -> None:
    assert EXACT.decompose(DecompositionTask(HPP, 1)).status is SearchStatus.PROVEN_NO
    r = EXACT.decompose(DecompositionTask(HPP, 2))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    assert r.root == r.ghd.root
    rep = validate(HPP, r.ghd)
    assert rep.ok and rep.width <= 2
    assert check_normal_form(HPP, r.ghd).ok
    assert r.mode is DecomposerMode.EXACT and r.stats.expansions > 0


@pytest.mark.parametrize("name", sorted(PAPER_HS))
@pytest.mark.parametrize("mode", list(DecomposerMode))
def test_ghw_by_search_paper(name: str, mode: DecomposerMode) -> None:
    h = Hypergraph(PAPER_HS[name])
    k, g, status = ghw_by_search(h, mode)
    assert status is SearchStatus.FOUND and g is not None
    if mode is DecomposerMode.EXACT:
        assert k == GHW[name]
    else:
        assert k is not None and k >= GHW[name]  # HEURISTIC: an upper bound only
    rep = validate(h, g)
    assert rep.ok and rep.width == k
    assert check_normal_form(h, g).ok


def test_heuristic_never_proven_no() -> None:
    r = HEUR.decompose(DecompositionTask(HPP, 1))
    assert r.status is SearchStatus.NOT_FOUND and r.ghd is None and r.mode is DecomposerMode.HEURISTIC
    assert HEUR.decompose(DecompositionTask(HPP, 0)).status is SearchStatus.NOT_FOUND


# --- edge cases -----------------------------------------------------------------------------
def test_empty_task_is_found_with_empty_ghd() -> None:
    r = EXACT.decompose(DecompositionTask(Hypergraph({}), 1))
    assert r.status is SearchStatus.FOUND and r.root is None and r.ghd is not None and len(r.ghd) == 0
    r = EXACT.decompose(DecompositionTask(HPP, 2, edges=fs()))
    assert r.status is SearchStatus.FOUND and r.root is None
    assert ghw_by_search(Hypergraph({}))[0] == 0


def test_k_zero_is_proven_no_in_exact() -> None:
    assert EXACT.decompose(DecompositionTask(HPP, 0)).status is SearchStatus.PROVEN_NO


def test_conn_not_coverable_is_proven_no() -> None:
    r = EXACT.decompose(DecompositionTask(HPP, 2, edges=fs({"w6"}), conn=fs({"zz"})))
    assert r.status is SearchStatus.PROVEN_NO
    # {a, j, e}: needs w1/w4, w6, w3/w5 -> three edges
    r = EXACT.decompose(DecompositionTask(HPP, 2, edges=fs({"w6"}), conn=fs("aje")))
    assert r.status is SearchStatus.PROVEN_NO


def test_bad_inputs_raise() -> None:
    with pytest.raises(ValueError, match="w1"):
        EXACT.decompose(DecompositionTask(HPP, 2, coverage_only={"w1": fs("ab")}))
    with pytest.raises(KeyError, match="nope"):
        EXACT.decompose(DecompositionTask(HPP, 2, edges=fs({"nope"})))
    with pytest.raises(KeyError, match="nope"):
        EXACT.decompose(DecompositionTask(HPP, 2, guard_pool=fs({"nope"})))


def test_single_edge_base_case() -> None:
    h = Hypergraph({"e": "abc"})
    r = EXACT.decompose(DecompositionTask(h, 1))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    assert [(n.bag, n.cover) for n in r.ghd] == [(fs("abc"), fs({"e"}))]


def test_guard_pool_restriction() -> None:
    # Without w5, a bag containing w5 = {c,e,h} needs w1 (c), w3 (e) and w2 (h): width 3.
    pool = HPP.edge_names - {"w5"}
    assert EXACT.decompose(DecompositionTask(HPP, 2, guard_pool=pool)).status is SearchStatus.PROVEN_NO
    r = EXACT.decompose(DecompositionTask(HPP, 3, guard_pool=pool))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    assert all(n.cover <= pool for n in r.ghd)
    assert validate(HPP, r.ghd).ok
    # path a-b-c-d covered only by the long edge: pool {long} at k=1 works, pool {} cannot
    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd", "long": "abcd"})
    assert EXACT.decompose(DecompositionTask(h, 1, guard_pool=fs({"long"}))).status is SearchStatus.FOUND
    assert EXACT.decompose(DecompositionTask(h, 3, guard_pool=fs())).status is SearchStatus.PROVEN_NO


def test_root_bag_contains_conn_and_fragment_is_restricted() -> None:
    c1 = fs({"w1", "w2", "w4"})
    for mode in DecomposerMode:
        r = TopDownDecomposer(mode).decompose(DecompositionTask(HPP, 2, edges=c1, conn=fs("ch")))
        assert r.status is SearchStatus.FOUND and r.ghd is not None and r.root is not None
        assert fs("ch") <= r.ghd.node(r.root).bag
        assert fragment_ok(HPP, r.ghd, c1)


def fragment_ok(h: Hypergraph, g: GHD, edges: frozenset[str]) -> bool:
    """A fragment is a GHD of the sub-hypergraph ``edges`` whose guards come from all of E(h)."""
    guarded = all(n.cover <= h.edge_names and n.bag <= h.covered_vertices(n.cover) for n in g)
    covered = all(any(h.edge(e) <= n.bag for n in g) for e in edges)
    vertices = h.covered_vertices(edges)
    connected = all(g.is_connected([n.id for n in g if v in n.bag]) for v in vertices)
    return guarded and covered and connected


def test_deterministic_output() -> None:
    a = EXACT.decompose(DecompositionTask(HPP, 2)).ghd
    b = EXACT.decompose(DecompositionTask(HPP, 2)).ghd
    assert a is not None and b is not None and a.to_spec() == b.to_spec()


def test_recursion_limit_is_restored() -> None:
    before = sys.getrecursionlimit()
    EXACT.decompose(DecompositionTask(HPP, 2))
    assert sys.getrecursionlimit() == before


def test_long_path_is_deep_but_fine() -> None:
    n = 60
    h = Hypergraph({f"e{i:03d}": (f"v{i:03d}", f"v{i + 1:03d}") for i in range(n)})
    r = EXACT.decompose(DecompositionTask(h, 1))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    assert validate(h, r.ghd).ok and check_normal_form(h, r.ghd).ok


def test_memo_hits_are_counted() -> None:
    r = EXACT.decompose(DecompositionTask(HPP, 1))  # failing search revisits states
    assert r.status is SearchStatus.PROVEN_NO and r.stats.memo_hits > 0


# --- top-level conn outside Lemma C's hypotheses (decision beyond §2.1, see decomposer) ---------
def test_conn_containing_the_only_edge() -> None:
    r = EXACT.decompose(DecompositionTask(HPP, 1, edges=fs({"w1"}), conn=fs("abc")))
    assert r.status is SearchStatus.FOUND and r.ghd is not None and r.root is not None
    assert fs("abc") <= r.ghd.node(r.root).bag


def test_conn_outside_the_edges_to_cover() -> None:
    h = Hypergraph({"e1": "ab", "f": "xy"})
    r = EXACT.decompose(DecompositionTask(h, 1, edges=fs({"e1"}), conn=fs("x")))
    assert r.status is SearchStatus.FOUND and r.ghd is not None and r.root is not None
    assert r.ghd.node(r.root).bag == fs("x") and r.ghd.node(r.root).cover == fs({"f"})
    assert [r.ghd.node(c).bag for c in r.ghd.children(r.root)] == [fs("ab")]


def test_conn_separating_the_edges_to_cover() -> None:
    """Path a-b-c-d; cover {e1, e3} below conn {b, c}: the only width-1 root is {b,c}/{e2}."""
    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd"})
    r = EXACT.decompose(DecompositionTask(h, 1, edges=fs({"e1", "e3"}), conn=fs("bc")))
    assert r.status is SearchStatus.FOUND and r.ghd is not None and r.root is not None
    assert r.ghd.node(r.root).bag == fs("bc")
    assert len(r.ghd.children(r.root)) == 2


# --- coverage-only constraints (Theorem 4.5) --------------------------------------------------
def test_coverage_only_path() -> None:
    h = Hypergraph({"e1": "ab", "e2": "bc"})
    k_ = {"K": fs("ac")}
    assert EXACT.decompose(DecompositionTask(h, 1, coverage_only=k_)).status is SearchStatus.PROVEN_NO
    assert EXACT.decompose(DecompositionTask(h, 1)).status is SearchStatus.FOUND
    r = EXACT.decompose(DecompositionTask(h, 2, coverage_only=k_))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    assert bags_containing(r.ghd, fs("ac"))
    assert all("K" not in n.cover for n in r.ghd)
    assert validate(h, r.ghd).ok


def test_coverage_only_example_43_target() -> None:
    """Paper Ex. 4.3 / Thm 4.5: re-decompose the target {a,b,c,e,h,i,k} with the restricted
    edges w4&={a}, w2&={h}, w6&={k} and the bag constraints C3={a,h} (from u3), C4={k} (from u4)."""
    h = Hypergraph({"w1": "abc", "w5": "ceh", "w3": "eik", "w4": "a", "w2": "h", "w6": "k"})
    constraints = {"C3": fs("ah"), "C4": fs("k")}
    r = EXACT.decompose(DecompositionTask(h, 2, coverage_only=constraints))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    rep = validate(h, r.ghd)
    assert rep.ok and rep.width <= 2
    for vs in constraints.values():
        assert bags_containing(r.ghd, vs)
    assert all(not (n.cover & set(constraints)) for n in r.ghd)
    assert check_normal_form(h, r.ghd).ok


def test_empty_coverage_only_set_is_ignored() -> None:
    h = Hypergraph({"e1": "ab"})
    r = EXACT.decompose(DecompositionTask(h, 1, coverage_only={"K": fs()}))
    assert r.status is SearchStatus.FOUND


# --- budget ---------------------------------------------------------------------------------
@pytest.mark.parametrize("k", [1, 2])
def test_tiny_budget_gives_not_found(k: int) -> None:
    r = EXACT.decompose(DecompositionTask(HPP, k), budget=Budget(max_expansions=2))
    assert r.status is SearchStatus.NOT_FOUND and r.ghd is None


def test_ghw_by_search_budget() -> None:
    assert ghw_by_search(HPP, DecomposerMode.EXACT, Budget(max_expansions=3)) == (None, None, SearchStatus.NOT_FOUND)
    k, g, status = ghw_by_search(HPP, DecomposerMode.EXACT, Budget(max_expansions=10_000))
    assert (k, status) == (2, SearchStatus.FOUND)


# --- scene hints (A19) ------------------------------------------------------------------------
class _BogusScenes(TopDownDecomposer):
    """Returns illegal and legal-but-useless hints at every state."""

    def _scene_candidates(self, c_key, conn, scenes):  # type: ignore[no-untyped-def]
        return [
            (fs({"zz"}), fs({"w1"})),            # bag not guarded
            (fs("abcdefghijkl"), HPP.edge_names),  # |lambda| > k
            (fs("abc"), fs({"w1"})),              # legal at the top, useless
            (fs("j"), fs({"w6"})),                # legal where j is free
        ]


@pytest.mark.parametrize("k", [1, 2, 3])
def test_scene_hints_never_change_exact_verdict(k: int) -> None:
    plain = EXACT.decompose(DecompositionTask(HPP, k))
    hinted = _BogusScenes(DecomposerMode.EXACT).decompose(DecompositionTask(HPP, k))
    assert hinted.status is plain.status
    if hinted.ghd is not None:
        assert validate(HPP, hinted.ghd).ok and hinted.ghd.width() <= k
        assert check_normal_form(HPP, hinted.ghd).ok

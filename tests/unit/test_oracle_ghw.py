"""S5: exact edge-cover number and exact ghw (elimination-ordering DP).

Cross-checks are deliberately independent of the implementation:
  * rho against a plain combination search over all edges;
  * ghw against a brute force over all vertex permutations that simulates elimination with
    explicit fill-in edges (not the reachability set Q used by the DP);
  * ghw == 1 iff alpha-acyclic, decided by the GYO reduction (theorem-level check: hw = ghw = 1
    exactly for the alpha-acyclic hypergraphs).
"""

from __future__ import annotations

import itertools
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.common.errors import OracleTooLargeError
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.oracle.edge_cover import edge_cover_number, minimum_edge_cover
from ighd.oracle.ghw_dp import MAX_ORACLE_VERTICES, exact_ghw
from tests.fixtures import expected, paper

fs = frozenset


# ------------------------------------------------------------------ independent reference code
def naive_rho(h: Hypergraph, bag: frozenset[str]) -> int | None:
    if not bag:
        return 0
    if not bag <= h.vertices:
        return None
    names = sorted(h.edge_names)
    for k in range(1, len(names) + 1):
        for combo in itertools.combinations(names, k):
            if bag <= frozenset().union(*(h.edge(n) for n in combo)):
                return k
    raise AssertionError("unreachable")


def naive_lex_min_cover(h: Hypergraph, bag: frozenset[str]) -> frozenset[str]:
    k = naive_rho(h, bag)
    assert k is not None
    covers = [c for c in itertools.combinations(sorted(h.edge_names), k)
              if bag <= frozenset().union(*(h.edge(n) for n in c))] if k else [()]
    return frozenset(min(covers))


def brute_ghw(h: Hypergraph) -> int:
    """min over all vertex permutations of max rho(elimination bag), with explicit fill-in."""
    vs = sorted(h.vertices)
    if not vs:
        return 0
    base: dict[str, set[str]] = {v: set() for v in vs}
    for e in h.edges.values():
        for a in e:
            base[a] |= e - {a}
    cache: dict[frozenset[str], int] = {}

    def rho(b: frozenset[str]) -> int:
        if b not in cache:
            r = naive_rho(h, b)
            assert r is not None
            cache[b] = r
        return cache[b]

    best = len(h)
    for perm in itertools.permutations(vs):
        g = {v: set(ns) for v, ns in base.items()}
        worst = 0
        for v in perm:
            nb = g.pop(v)
            worst = max(worst, rho(fs(nb | {v})))
            if worst >= best:
                break
            for a in nb:
                g[a].discard(v)
                g[a] |= nb - {a}
        best = min(best, worst)
    return best


def gyo_acyclic(h: Hypergraph) -> bool:
    """GYO reduction: drop vertices in exactly one edge and edges contained in another edge."""
    edges = [set(e) for e in h.edges.values()]
    changed = True
    while changed and edges:
        changed = False
        count: dict[str, int] = {}
        for e in edges:
            for v in e:
                count[v] = count.get(v, 0) + 1
        for e in edges:
            lonely = {v for v in e if count[v] == 1}
            if lonely:
                e -= lonely
                changed = True
        for i, e in enumerate(edges):
            if any(j != i and e <= f for j, f in enumerate(edges)) or not e:
                del edges[i]
                changed = True
                break
    return not edges


@st.composite
def hypergraphs(draw: st.DrawFn, max_vertices: int = 7, max_edges: int = 6) -> Hypergraph:
    n = draw(st.integers(1, max_vertices))
    masks = draw(st.lists(st.integers(1, 2 ** n - 1), min_size=1, max_size=max_edges))
    return Hypergraph({f"e{i}": {"abcdefg"[k] for k in range(n) if m >> k & 1} for i, m in enumerate(masks)})


def random_instances(count: int, seed: int) -> list[Hypergraph]:
    """Seeded instances with 3..7 vertices, 2..7 edges of size 1..4 (hypothesis alone shrinks
    towards trivial, mostly acyclic inputs, so the cross-checks also run on these)."""
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        n = rng.randint(3, 7)
        vs = "abcdefg"[:n]
        m = rng.randint(2, 7)
        out.append(Hypergraph({f"e{i}": rng.sample(vs, min(n, rng.choice((1, 2, 2, 2, 3, 3, 4))))
                               for i in range(m)}))
    return out


def random_dense_graphs(count: int, seed: int) -> list[Hypergraph]:
    """Seeded graphs on 6..7 vertices with 9..16 binary edges (ghw 2-4)."""
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        n = rng.randint(6, 7)
        pairs = list(itertools.combinations("abcdefg"[:n], 2))
        chosen = rng.sample(pairs, rng.randint(9, min(16, len(pairs))))
        out.append(Hypergraph({f"{a}{b}": (a, b) for a, b in chosen}))
    return out


CROSS = random_instances(60, seed=20220921) + random_dense_graphs(20, seed=2209)


def graph(pairs: str) -> Hypergraph:
    return Hypergraph({p: p for p in pairs.split()})


# ------------------------------------------------------------------ edge cover
def test_edge_cover_basics() -> None:
    h = Hypergraph(paper.H_PP)
    assert edge_cover_number(h, "") == 0
    assert minimum_edge_cover(h, "") == fs()
    assert edge_cover_number(h, "cehik") == 2
    assert minimum_edge_cover(h, "cehik") == fs({"w3", "w5"})
    assert edge_cover_number(h, "abcdefghijkl") == 5
    assert edge_cover_number(h, "az") is None
    assert minimum_edge_cover(h, "az") is None
    assert edge_cover_number(h, "e") == 1
    assert minimum_edge_cover(h, "e") == fs({"w3"})  # w3 < w5 by name


def test_minimum_cover_prefers_lexicographically_smallest() -> None:
    h = Hypergraph({"x": "ab", "b2": "bc", "a1": "ab", "c": "c"})
    assert minimum_edge_cover(h, "abc") == fs({"a1", "b2"})
    assert minimum_edge_cover(h, "ab") == fs({"a1"})


@settings(derandomize=True, max_examples=100, deadline=None)
@given(hypergraphs(), st.integers(0, 2 ** 8 - 1))
def test_edge_cover_matches_naive(h: Hypergraph, bits: int) -> None:
    pool = sorted(h.vertices) + ["zz"]
    bag = fs(v for i, v in enumerate(pool) if bits >> i & 1)
    assert edge_cover_number(h, bag) == naive_rho(h, bag)
    if naive_rho(h, bag) is None:
        assert minimum_edge_cover(h, bag) is None
    else:
        assert minimum_edge_cover(h, bag) == naive_lex_min_cover(h, bag)


# ------------------------------------------------------------------ exact ghw: fixed cases
@pytest.mark.parametrize("name", sorted(expected.GHW))
def test_paper_ghw(name: str) -> None:
    h = Hypergraph(getattr(paper, name))
    k, g = exact_ghw(h)
    assert k == expected.GHW[name]
    rep = validate(h, g)
    assert rep.ok, rep.violations
    assert rep.width == k


@pytest.mark.parametrize("h,k", [
    (Hypergraph({"e": "abc"}), 1),
    (Hypergraph({"e": "ab", "f": "cd"}), 1),
    (graph("ab bc ca"), 2),
    (graph("ab bc cd de ea"), 2),
    (graph(" ".join("".join(p) for p in itertools.combinations("abcde", 2))), 3),
    (graph("ab bc cd da"), 2),
    (Hypergraph({"e1": "abc", "e2": "cde", "e3": "efa"}), 2),            # cyclic triangle of triples
    (Hypergraph({"big": "abcdef", "e1": "ab", "e2": "cd", "e3": "ef"}), 1),  # covered by one edge
    # 3x3 grid graph: treewidth 3, bags of 4 vertices need 2 edges
    (graph("ab bc de ef gh hi ad dg be eh cf fi"), 2),
], ids=["single", "two-disjoint", "triangle", "C5", "K5", "C4", "triple-cycle", "big-edge", "grid3"])
def test_small_ghw(h: Hypergraph, k: int) -> None:
    got, g = exact_ghw(h)
    assert got == k
    rep = validate(h, g)
    assert rep.ok, rep.violations
    assert rep.width == k


def test_disjoint_edges_witness_is_one_tree() -> None:
    h = Hypergraph({"e": "ab", "f": "cd", "g": "xy"})
    k, g = exact_ghw(h)
    assert k == 1
    assert len(g.preorder()) == len(g)  # every node reachable from the single root
    assert validate(h, g).ok


def test_empty_hypergraph() -> None:
    k, g = exact_ghw(Hypergraph({}))
    assert k == 0 and len(g) == 0


def test_size_guard() -> None:
    names = [f"v{i:02d}" for i in range(MAX_ORACLE_VERTICES + 1)]
    path = Hypergraph({f"e{i}": {a, b} for i, (a, b) in enumerate(zip(names, names[1:]))})
    with pytest.raises(OracleTooLargeError):
        exact_ghw(path)
    k, g = exact_ghw(path.without_edges(["e15"]))  # exactly 16 vertices is allowed
    assert k == 1 and validate(path.without_edges(["e15"]), g).ok


def test_witness_is_deterministic() -> None:
    h = Hypergraph(paper.H_P2)
    k1, g1 = exact_ghw(h)
    k2, g2 = exact_ghw(h)
    assert k1 == k2 and g1.to_spec() == g2.to_spec()


# ------------------------------------------------------------------ independent cross-checks
@settings(derandomize=True, max_examples=40, deadline=None)
@given(hypergraphs(max_vertices=7, max_edges=6))
def test_ghw_matches_permutation_brute_force(h: Hypergraph) -> None:
    k, g = exact_ghw(h)
    assert k == brute_ghw(h)
    assert validate(h, g).ok


@settings(derandomize=True, max_examples=60, deadline=None)
@given(hypergraphs(max_vertices=7, max_edges=6))
def test_ghw_one_iff_alpha_acyclic(h: Hypergraph) -> None:
    k, _ = exact_ghw(h)
    assert (k == 1) == gyo_acyclic(h)


def test_seeded_instances_are_varied() -> None:
    ks = [exact_ghw(h)[0] for h in CROSS]
    assert {1, 2, 3} <= set(ks)
    assert sum(len(h.vertices) >= 6 for h in CROSS) >= 15


@pytest.mark.parametrize("idx", range(len(CROSS)))
def test_seeded_cross_checks(idx: int) -> None:
    h = CROSS[idx]
    k, g = exact_ghw(h)
    assert k == brute_ghw(h)
    assert (k == 1) == gyo_acyclic(h)
    rho_all = edge_cover_number(h, h.vertices)
    assert rho_all is not None and 1 <= k <= rho_all
    rep = validate(h, g)
    assert rep.ok and rep.width == k


@settings(derandomize=True, max_examples=60, deadline=None)
@given(hypergraphs(max_vertices=7, max_edges=6))
def test_ghw_bounds(h: Hypergraph) -> None:
    k, _ = exact_ghw(h)
    rho_all = edge_cover_number(h, h.vertices)
    assert rho_all is not None
    assert 1 <= k <= rho_all


def test_gyo_reference_itself() -> None:
    assert gyo_acyclic(Hypergraph(paper.H_P))
    assert not gyo_acyclic(Hypergraph(paper.H_PP))
    assert not gyo_acyclic(graph("ab bc ca"))
    assert gyo_acyclic(Hypergraph({"t": "abc", "x": "ab", "y": "bc", "z": "ca"}))


@pytest.mark.slow
def test_ghw_at_the_size_guard() -> None:
    names = [f"v{i:02d}" for i in range(MAX_ORACLE_VERTICES)]
    h = Hypergraph({f"e{a}{b}": {names[a], names[b]} for a, b in itertools.combinations(range(16), 2)
                    if (a * 7 + b) % 3})
    k, g = exact_ghw(h)
    assert validate(h, g).ok and validate(h, g).width == k

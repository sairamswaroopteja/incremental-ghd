"""Differential tests: the S7 search against independent ground truth.

1. ghw: ``ghw_by_search`` (EXACT) must equal ``oracle.exact_ghw`` (a DP over elimination orderings,
   a different method) on seeded random small hypergraphs. Every FOUND output must pass
   ``validate`` with width <= k and ``check_normal_form`` (Lemma F); k = ghw - 1 must give
   PROVEN_NO (Theorem E); HEURISTIC must return k >= ghw with valid NF outputs (Lemma B).

   Family A (the spec's corpus: <= 7 vertices, <= 6 edges, cyclic ones included) only produces
   ghw 1 and 2: in a 20 000-sample probe (5-7 vertices, 4-6 edges of size 2-4) the oracle never
   returned 3 (ghw 1: 8142, ghw 2: 11858). So family B
   adds dense binary graphs on 6-7 vertices (12-17 edges), plus K_6, to make ghw 3 occur.
   Observed distribution of the default run (seeds below): see ``test_ghw_matches_oracle``'s
   printed line ("ghw distribution"); at the time of writing it was
   A: {1: 281, 2: 69}, B (incl. K_6): {2: 5, 3: 36}.

2. Constrained decompositions (coverage-only sets, Theorem 4.5) and connection sets, on tiny
   instances (<= 5 vertices), against brute force. Ground truth method: a constrained GHD is a
   tree decomposition of the target sets T (E(H) plus the constraints, or the edges C to cover
   plus conn as one extra set: a decomposition with conn inside some bag can be re-rooted there)
   whose bags B have rho_pool(B) <= k, where rho_pool is the edge cover number using ONLY guard
   pool edges (never the constraint sets). Every tree decomposition refines to one obtained from
   an elimination ordering of the primal graph of T with bags inside the old bags, and rho_pool is
   monotone, so the optimum is min over ALL permutations of V(T) of the max rho_pool over the
   elimination bags {v} u N(v) (each target set, being a clique, lies inside some elimination
   bag; we assert that too). We enumerate every permutation (<= 5! = 120) explicitly.
   EXACT FOUND iff brute <= k; HEURISTIC FOUND implies brute <= k; every FOUND output is checked
   directly (coverage of every target set, connectedness, guards from the pool, width <= k,
   constraint names never in a cover, root bag contains conn).
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable
from itertools import combinations, permutations

import pytest

from ighd.common import DecomposerMode, SearchStatus
from ighd.ghd.normal_form import check_normal_form
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.oracle.edge_cover import edge_cover_number
from ighd.oracle.ghw_dp import exact_ghw
from ighd.static.decomposer import DecompositionTask, TopDownDecomposer, ghw_by_search

fs = frozenset
EXACT = TopDownDecomposer(DecomposerMode.EXACT)
HEUR = TopDownDecomposer(DecomposerMode.HEURISTIC)
LETTERS = "abcdefghij"


# --- generators -------------------------------------------------------------------------------
def family_a(rng: random.Random) -> Hypergraph:
    """<= 7 vertices, <= 6 edges; mostly 3-6 edges of size 2-3 so that cycles are common."""
    nv = rng.randint(3, 7)
    vs = LETTERS[:nv]
    ne = rng.randint(1, 6) if rng.random() < 0.2 else rng.randint(3, 6)
    edges = {f"e{i}": rng.sample(vs, rng.choice((1, 2, 2, 3, 3, 4)) if nv >= 4 else rng.randint(1, nv))
             for i in range(ne)}
    return Hypergraph(edges)


def family_b(rng: random.Random) -> Hypergraph:
    """Dense binary graphs on 6-7 vertices with 12-17 distinct edges (ghw 2 or 3)."""
    nv = rng.randint(6, 7)
    pairs = list(combinations(LETTERS[:nv], 2))
    chosen = rng.sample(pairs, rng.randint(12, min(17, len(pairs))))
    return Hypergraph({f"e{i:02d}": p for i, p in enumerate(chosen)})


K6 = Hypergraph({f"e{a}{b}": (a, b) for a, b in combinations("abcdef", 2)})


# --- checks -----------------------------------------------------------------------------------
def check_ghw_instance(h: Hypergraph) -> int:
    """All ghw-level assertions for one hypergraph; returns ghw."""
    g_oracle, _ = exact_ghw(h)
    k, ghd, status = ghw_by_search(h, DecomposerMode.EXACT)
    assert status is SearchStatus.FOUND and ghd is not None
    assert k == g_oracle, (dict(h.edges), k, g_oracle)
    rep = validate(h, ghd)
    assert rep.ok and rep.width <= k, (dict(h.edges), rep.violations)
    nf = check_normal_form(h, ghd)
    assert nf.ok, (dict(h.edges), nf.reason)
    if g_oracle >= 2:
        r = EXACT.decompose(DecompositionTask(h, g_oracle - 1))
        assert r.status is SearchStatus.PROVEN_NO, dict(h.edges)
    kh, gh, sh = ghw_by_search(h, DecomposerMode.HEURISTIC)
    assert sh is SearchStatus.FOUND and gh is not None and kh is not None and kh >= g_oracle
    assert validate(h, gh).ok and gh.width() <= kh
    assert check_normal_form(h, gh).ok
    if kh > 1:
        assert HEUR.decompose(DecompositionTask(h, kh - 1)).status is SearchStatus.NOT_FOUND
    return g_oracle


def brute_width(pool: Hypergraph, targets: Iterable[frozenset[str]]) -> int | None:
    """min over elimination orders of max rho_pool(bag); None if some bag is not coverable."""
    sets = [t for t in targets if t]
    verts = sorted(fs().union(*sets)) if sets else []
    if not verts:
        return 0
    adj0: dict[str, set[str]] = {v: set() for v in verts}
    for t in sets:
        for a in t:
            adj0[a] |= t - {a}
    rho_cache: dict[frozenset[str], int | None] = {}

    def rho(b: frozenset[str]) -> int | None:
        if b not in rho_cache:
            rho_cache[b] = edge_cover_number(pool, b) if pool.edge_names else None
        return rho_cache[b]

    best: int | None = None
    for order in permutations(verts):
        adj = {v: set(n) for v, n in adj0.items()}
        bags: list[frozenset[str]] = []
        worst = 0
        ok = True
        for v in order:
            bag = fs({v} | adj[v])
            bags.append(bag)
            r = rho(bag)
            if r is None or (best is not None and r >= best):
                ok = False
                break
            worst = max(worst, r)
            nbrs = adj.pop(v)
            for a in nbrs:
                adj[a] |= nbrs - {a}
                adj[a].discard(v)
        if ok:
            assert all(any(t <= b for b in bags) for t in sets)  # cliques lie in some bag
            best = worst
    return best


def check_constrained_output(pool: Hypergraph, g: GHD, targets: Iterable[frozenset[str]], k: int,
                             forbidden: Iterable[str] = ()) -> None:
    """Direct check of a constrained decomposition (independent of the code under test)."""
    nodes = list(g)
    tgt = [t for t in targets if t]
    for n in nodes:
        assert n.cover <= pool.edge_names and 1 <= len(n.cover) <= k
        assert not (n.cover & set(forbidden))
        assert n.bag <= pool.covered_vertices(n.cover)
    for t in tgt:
        assert any(t <= n.bag for n in nodes), t
    for v in fs().union(*tgt) if tgt else fs():
        assert g.is_connected([n.id for n in nodes if v in n.bag]), v


# --- 1. ghw against the oracle ------------------------------------------------------------------
def run_ghw_corpus(n_a: int, n_b: int, seed: int) -> tuple[Counter[int], Counter[int]]:
    rng = random.Random(seed)
    dist_a: Counter[int] = Counter()
    dist_b: Counter[int] = Counter()
    for _ in range(n_a):
        dist_a[check_ghw_instance(family_a(rng))] += 1
    for _ in range(n_b):
        dist_b[check_ghw_instance(family_b(rng))] += 1
    dist_b[check_ghw_instance(K6)] += 1
    return dist_a, dist_b


def test_ghw_matches_oracle() -> None:
    dist_a, dist_b = run_ghw_corpus(350, 40, seed=20240917)
    print(f"ghw distribution A: {dict(sorted(dist_a.items()))}, B: {dict(sorted(dist_b.items()))}")
    total = dist_a + dist_b
    assert sum(total.values()) >= 300
    assert total[1] > 0 and total[2] > 0 and total[3] > 0


@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ghw_matches_oracle_large(seed: int) -> None:
    dist_a, dist_b = run_ghw_corpus(1000, 150, seed=seed)
    print(f"seed {seed}: A {dict(sorted(dist_a.items()))}, B {dict(sorted(dist_b.items()))}")


# --- 2. constrained decompositions against brute force ------------------------------------------
def tiny_hypergraph(rng: random.Random) -> Hypergraph:
    nv = rng.randint(2, 5)
    vs = LETTERS[:nv]
    return Hypergraph({f"e{i}": rng.sample(vs, rng.randint(1, min(3, nv)))
                       for i in range(rng.randint(1, 5))})


def random_vertex_set(rng: random.Random, h: Hypergraph, lo: int, hi: int) -> frozenset[str]:
    vs = sorted(h.vertices)
    out = set(rng.sample(vs, min(len(vs), rng.randint(lo, hi))))
    if rng.random() < 0.1:
        out.add("z")  # a vertex no guard can cover
    return fs(out)


def test_brute_force_agrees_with_oracle() -> None:
    """Sanity check of the ground truth itself: without constraints, brute == exact_ghw."""
    rng = random.Random(7)
    for _ in range(60):
        h = tiny_hypergraph(rng)
        assert brute_width(h, h.edges.values()) == exact_ghw(h)[0]


def run_coverage_corpus(n: int, seed: int) -> Counter[str]:
    rng = random.Random(seed)
    seen: Counter[str] = Counter()
    for _ in range(n):
        h = tiny_hypergraph(rng)
        cons = {f"K{i}": random_vertex_set(rng, h, 1, 4) for i in range(rng.randint(1, 2))}
        truth = brute_width(h, [*h.edges.values(), *cons.values()])
        for k in (1, 2, 3):
            task = DecompositionTask(h, k, coverage_only=cons)
            r = EXACT.decompose(task)
            expect = truth is not None and truth <= k
            assert (r.status is SearchStatus.FOUND) == expect, (dict(h.edges), cons, k, truth, r.status)
            if not expect:
                assert r.status is SearchStatus.PROVEN_NO
                seen["no"] += 1
            else:
                assert r.ghd is not None
                check_constrained_output(h, r.ghd, [*h.edges.values(), *cons.values()], k, cons)
                assert validate(h, r.ghd).ok
                seen["yes"] += 1
            rh = HEUR.decompose(task)
            assert rh.status is not SearchStatus.PROVEN_NO
            if rh.status is SearchStatus.FOUND:
                assert expect and rh.ghd is not None
                check_constrained_output(h, rh.ghd, [*h.edges.values(), *cons.values()], k, cons)
    return seen


def test_coverage_only_matches_brute_force() -> None:
    seen = run_coverage_corpus(200, seed=4242)
    assert seen["yes"] > 50 and seen["no"] > 50


def run_conn_corpus(n: int, seed: int) -> Counter[str]:
    rng = random.Random(seed)
    seen: Counter[str] = Counter()
    for _ in range(n):
        h = tiny_hypergraph(rng)
        names = sorted(h.edge_names)
        c = fs(rng.sample(names, rng.randint(1, len(names))))
        conn = random_vertex_set(rng, h, 0, 3)
        targets = [h.edge(e) for e in c] + [conn]
        truth = brute_width(h, targets)
        for k in (1, 2, 3):
            r = EXACT.decompose(DecompositionTask(h, k, edges=c, conn=conn))
            expect = truth is not None and truth <= k
            assert (r.status is SearchStatus.FOUND) == expect, (dict(h.edges), c, conn, k, truth)
            if expect:
                assert r.ghd is not None and r.root is not None
                assert conn <= r.ghd.node(r.root).bag
                check_constrained_output(h, r.ghd, targets, k)
                seen["yes"] += 1
            else:
                assert r.status is SearchStatus.PROVEN_NO
                seen["no"] += 1
    return seen


def test_conn_tasks_match_brute_force() -> None:
    """Tasks with a connection set (decomp_update's use), including conn outside V(C) and C not
    [conn]-connected, where the decomposer's top-level conn-root candidate is needed."""
    seen = run_conn_corpus(200, seed=99)
    assert seen["yes"] > 50 and seen["no"] > 20


def test_conn_root_extension_is_needed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins the gap in applying §2.1 verbatim to tasks with conn != {} (Theorem E covers only the
    top call S(E, {})): with the top-level conn-root candidate disabled, the search wrongly
    reports PROVEN_NO on some instances of the conn corpus (e.g. C = {e1, e3} on the path
    a-b-c-d with conn {b, c} at k = 1)."""
    from ighd.static import decomposer as mod

    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd"})
    task = DecompositionTask(h, 1, edges=fs({"e1", "e3"}), conn=fs("bc"))
    assert brute_width(h, [fs("ab"), fs("cd"), fs("bc")]) == 1
    assert EXACT.decompose(task).status is SearchStatus.FOUND
    monkeypatch.setattr(mod._Search, "_conn_root_candidate", lambda self, c, conn: [])
    assert EXACT.decompose(task).status is SearchStatus.PROVEN_NO  # the verbatim §2.1 answer
    with pytest.raises(AssertionError):
        run_conn_corpus(200, seed=99)


@pytest.mark.slow
def test_constrained_large() -> None:
    run_coverage_corpus(2000, seed=5)
    run_conn_corpus(2000, seed=6)

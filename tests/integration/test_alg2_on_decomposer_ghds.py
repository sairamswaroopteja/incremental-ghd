"""Integration (main agent, W3 review): Algorithm 2 (S9) vs the brute-force Def 4.1 oracle (S5) on
the COMPACT normal-form GHDs produced by the decomposer (S7), i.e. the kind of input the update
algorithm actually receives. Agent D's differential test used the oracle's elimination witnesses
(one node per vertex), where T* is the whole tree in over half the cases; this test checks that
the comparison is non-trivial (many proper, non-empty T*) and that Lemma 4.4 holds on it."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from ighd.common import DecomposerMode
from ighd.common.errors import InvalidModificationError
from ighd.ghd import check_normal_form, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar
from ighd.mutable import minimal_mutable_subtree
from ighd.oracle import all_mutable_subtrees
from ighd.oracle.brute_mutable import MAX_BRUTE_NODES
from ighd.static import ghw_by_search

KINDS = ["AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq"]


def random_hypergraph(rng: random.Random) -> Hypergraph:
    vs = list("abcdefg")[: rng.randint(4, 7)]
    edges = {}
    for i in range(rng.randint(3, 6)):
        edges[f"w{i}"] = rng.sample(vs, rng.randint(2, min(3, len(vs))))
    return Hypergraph(edges)


def random_modification(rng: random.Random, h: Hypergraph, kind: str):
    names, verts = sorted(h.edge_names), sorted(h.vertices)
    if kind == "AddVar":
        return AddVar("z", frozenset(rng.sample(names, rng.randint(1, len(names)))))
    if kind == "DelVar":
        return DelVar(rng.choice(verts))
    if kind == "AddConstr":
        pick = rng.sample(verts, rng.randint(2, min(3, len(verts))))
        if rng.random() < 0.15:
            pick = pick[:1] + ["y"]
        return AddConstr("wnew", frozenset(pick))
    if kind == "DelConstr":
        return DelConstr(rng.choice(names))
    if kind == "AddEq":
        a, b = rng.sample(verts, 2)
        return AddEq(frozenset({a, b}), a)
    deg2 = [v for v in verts if len(h.incident(v)) >= 2]
    if not deg2:
        return None
    v = rng.choice(deg2)
    inc = sorted(h.incident(v))
    keep = frozenset(rng.sample(inc, rng.randint(1, len(inc) - 1)))
    return DelEq(v, {v: keep, "v2": frozenset(inc) - keep})


def run_cases(seed: int, n: int) -> Counter:
    rng = random.Random(seed)
    stats: Counter = Counter()
    while stats["cases"] < n:
        h = random_hypergraph(rng)
        k, ghd, _ = ghw_by_search(h, DecomposerMode.EXACT)
        if ghd is None or len(ghd) > MAX_BRUTE_NODES or len(ghd) < 2:
            continue
        assert validate(h, ghd).ok and check_normal_form(h, ghd).ok
        kind = rng.choice(KINDS)
        mod = random_modification(rng, h, kind)
        if mod is None:
            continue
        try:
            change = mod.apply(h)
        except InvalidModificationError:
            continue
        subs = all_mutable_subtrees(change, ghd)
        size = min(map(len, subs))
        minima = [s for s in subs if len(s) == size]
        t_star = minimal_mutable_subtree(change, ghd).t_star
        assert len(minima) == 1, (kind, h.edges, minima)          # Lemma 4.4: unique minimum
        assert t_star == minima[0], (kind, h.edges, t_star, minima)  # Alg 2 finds it
        stats["cases"] += 1
        stats[f"kind:{kind}"] += 1
        stats["empty" if not t_star else "whole" if len(t_star) == len(ghd) else "proper"] += 1
        stats[f"ghw:{k}"] += 1
    return stats


def test_alg2_equals_unique_oracle_minimum_on_decomposer_ghds() -> None:
    stats = run_cases(seed=20260413, n=300)
    print(dict(sorted(stats.items())))
    # the comparison must be meaningful: many proper non-empty T*, and cyclic inputs present
    assert stats["proper"] >= 0.3 * stats["cases"], stats
    assert stats["ghw:2"] >= 20, stats


@pytest.mark.slow
def test_alg2_equals_unique_oracle_minimum_on_decomposer_ghds_large() -> None:
    for seed in (1, 2, 3):
        print(dict(sorted(run_cases(seed=seed, n=1500).items())))

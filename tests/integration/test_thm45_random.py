"""S10 integration: the Theorem 4.5 pipeline on random small instances (seeded).

For a random hypergraph H (<= 7 vertices, <= 6 edges), the input is a compact minimal-width GHD
from ghw_by_search(EXACT) (k = ghw(H)); a random valid modification of each of the six classes
(Defs 3.2-3.4) is applied, T* comes from Algorithm 2, and the pipeline of
tests/paper_examples/test_thm45_repair.py runs (delta(H)*, T*-induced constraints, constrained
EXACT search at width k, glue).

Assertions:
  * FOUND => the glued GHD validates against delta(H), has width <= k, every outer node keeps its
    exact bag and cover (Lemma 4.2 reuse), and every outer tree is a GHD of delta(H)[T'] (I4);
  * exact_ghw(delta(H)) > k => the pipeline does not return FOUND (soundness of Theorem 4.5);
  * PROVEN_NO is classified as "genuine" (exact_ghw(delta(H)) > k) or "constraint-induced"
    (exact_ghw(delta(H)) <= k: Theorem 4.5 is only a sufficient condition, the T*-induced
    constraints were too strong). The second kind is counted, never a failure.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from ighd.common.errors import InvalidModificationError
from ighd.common.types import DecomposerMode, SearchStatus
from ighd.ghd import GHD, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar
from ighd.oracle import exact_ghw
from ighd.static import ghw_by_search
from tests.paper_examples.test_thm45_repair import assert_lemma42, assert_outer_trees_kept, thm45_pipeline

KINDS = ["AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq"]


def random_hypergraph(rng: random.Random) -> Hypergraph:
    vs = list("abcdefg")[: rng.randint(4, 7)]
    edges: dict[str, list[str]] = {}
    for i in range(rng.randint(3, 6)):
        edges[f"w{i}"] = rng.sample(vs, rng.randint(2, 3))
    return Hypergraph(edges)


def random_modification(rng: random.Random, h: Hypergraph, kind: str):
    """A random valid modification of class ``kind`` for ``h`` (None if none exists)."""
    names, verts = sorted(h.edge_names), sorted(h.vertices)
    if kind == "AddVar":
        return AddVar("z", frozenset(rng.sample(names, rng.randint(1, len(names)))))
    if kind == "DelVar":
        return DelVar(rng.choice(verts))
    if kind == "AddConstr":
        pick = rng.sample(verts, rng.randint(1, min(3, len(verts))))
        r = rng.random()
        if r < 0.15:
            pick = pick[:1] + ["y"]          # edge with a new vertex
        elif r < 0.2:
            pick = ["x", "y"]                # edge made only of new vertices (T* = {}, A12)
        return AddConstr("wnew", frozenset(pick))
    if kind == "DelConstr":
        return DelConstr(rng.choice(names))
    if kind == "AddEq":
        merge = rng.sample(verts, rng.randint(2, min(3, len(verts))))
        into = "z" if rng.random() < 0.3 else merge[0]
        return AddEq(frozenset(merge), into)
    # DelEq: a vertex of degree >= 2, incident edges split into two non-empty parts
    deg2 = [v for v in verts if h.degree(v) >= 2]
    if not deg2:
        return None
    v = rng.choice(deg2)
    inc = sorted(h.incident(v))
    first = frozenset(rng.sample(inc, rng.randint(1, len(inc) - 1)))
    second = frozenset(inc) - first
    if rng.random() < 0.3:
        return DelEq(v, {"v1": first, "v2": second})   # v disappears, both parts new
    return DelEq(v, {v: first, "v2": second})


def run_cases(seed: int, n: int) -> Counter:
    rng = random.Random(seed)
    stats: Counter = Counter()
    i = 0
    while stats["cases"] < n:
        h = random_hypergraph(rng)
        k, ghd0, _ = ghw_by_search(h, DecomposerMode.EXACT)
        assert k is not None and ghd0 is not None
        if len(ghd0) < 2:  # a one-node GHD only ever gives T* in {{}, T}: no gluing to test
            continue
        old = GHD.from_spec(ghd0.to_spec())  # label every node ("#id") so outer nodes can be traced
        kind = KINDS[i % len(KINDS)]
        i += 1
        mod = random_modification(rng, h, kind)
        if mod is None:
            continue
        try:
            change = mod.apply(h)
        except InvalidModificationError:
            continue
        run = thm45_pipeline(change, old, k)
        ghw_new = exact_ghw(change.new)[0]
        for c in run.constraints:
            assert c.vertices <= run.target.vertices
        assert_lemma42(change, old, run.constraints)
        status = run.decomp.status
        ctx = (kind, dict(h.edges), mod, sorted(run.t_star))
        if ghw_new > k:
            assert status is not SearchStatus.FOUND, ctx
        if status is SearchStatus.FOUND:
            assert run.glued is not None
            rep = validate(change.new, run.glued)
            assert rep.ok, (ctx, rep.violations)
            assert rep.width <= k, ctx
            assert_outer_trees_kept(old, run.glued, run.constraints)
            outcome = "found"
        else:
            assert status is SearchStatus.PROVEN_NO, ctx
            outcome = "genuine_no" if ghw_new > k else "constraint_no"
        stats["cases"] += 1
        stats[outcome] += 1
        stats[f"{kind}:{outcome}"] += 1
        shape = "empty" if not run.t_star else "whole" if len(run.t_star) == len(old) else "proper"
        stats[f"t_star:{shape}"] += 1
    return stats


def test_thm45_random() -> None:
    stats = run_cases(seed=20261116, n=1200)
    print(dict(sorted(stats.items())))
    assert stats["found"] + stats["genuine_no"] + stats["constraint_no"] == stats["cases"]
    assert stats["t_star:proper"] >= 0.2 * stats["cases"], stats  # non-trivial gluing happens
    assert stats["found"] >= 0.5 * stats["cases"], stats


@pytest.mark.slow
def test_thm45_random_large() -> None:
    total: Counter = Counter()
    for seed in (1, 2, 3, 4):
        s = run_cases(seed=seed, n=1500)
        print(seed, dict(sorted(s.items())))
        total += s
    print("total", dict(sorted(total.items())))

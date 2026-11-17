"""S9 differential test: Algorithm 2 against the brute-force oracle (Lemma 4.4, A2).

Random small hypergraphs (<= 8 vertices, <= 7 edges), the exact_ghw witness GHD (a valid GHD
with one node per vertex), and a random valid modification of each of the six classes.

  (1) EDGEWISE: Alg 2's T* is the unique minimum of oracle.all_mutable_subtrees (Lemma 4.4);
  (2) T* is mutable by mutable_conditions;
  (3) SET: T* is SET-mutable. How often it is not a SET minimum, and how often the SET
      minimum is not unique, is recorded (printed, run with -s), never asserted;
  (4) leaf order: a reversed-order re-implementation (via mutable_conditions) gives the same T*
      under EDGEWISE (order-independence follows from Lemma 4.4's uniqueness).
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest

from ighd.common.config import InducedComparison, Semantics
from ighd.common.types import NodeId
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar, ModificationResult
from ighd.mutable import minimal_mutable_subtree, mutable_conditions
from ighd.oracle import MAX_BRUTE_NODES, all_mutable_subtrees, exact_ghw

fs = frozenset
EDGEWISE = Semantics(induced_comparison=InducedComparison.EDGEWISE)
SET = Semantics(induced_comparison=InducedComparison.SET)
KINDS = ["AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq"]
VERTEX_POOL = "abcdefgh"


# ------------------------------------------------------------------ generators
def random_hypergraph(rng: random.Random) -> Hypergraph:
    n = rng.randint(3, 8)
    vs = VERTEX_POOL[:n]
    m = rng.randint(1, 7)
    return Hypergraph({f"e{i}": rng.sample(vs, rng.randint(1, min(4, n))) for i in range(m)})


def fresh(h: Hypergraph, k: int) -> list[str]:
    """k vertex names not in V(h) (n0, n1, ... never occur in VERTEX_POOL)."""
    out = [f"n{i}" for i in range(k)]
    assert not set(out) & h.vertices
    return out


def subset(rng: random.Random, xs: frozenset[str], min_size: int = 1) -> frozenset[str]:
    items = sorted(xs)
    return fs(rng.sample(items, rng.randint(min_size, len(items))))


def random_modification(rng: random.Random, h: Hypergraph, kind: str) -> Any:
    """A modification of class ``kind`` with parameters valid for ``h`` (h non-empty)."""
    vs = h.vertices
    if kind == "AddVar":
        return AddVar(fresh(h, 1)[0], subset(rng, h.edge_names))
    if kind == "DelVar":
        return DelVar(rng.choice(sorted(vs)))
    if kind == "AddConstr":
        pool = vs if rng.random() < 0.6 else vs | set(fresh(h, 2))
        return AddConstr("f0", fs(rng.sample(sorted(pool), rng.randint(1, min(4, len(pool))))))
    if kind == "DelConstr":
        return DelConstr(rng.choice(sorted(h.edge_names)))
    if kind == "AddEq":
        merge = fs(rng.sample(sorted(vs), rng.randint(1, min(3, len(vs)))))
        if len(merge) >= 2 and rng.random() < 0.6:
            return AddEq(merge, rng.choice(sorted(merge)))
        return AddEq(merge, fresh(h, 1)[0])
    assert kind == "DelEq"
    v = rng.choice(sorted(vs))
    inc = h.incident(v)
    keep = rng.random() < 0.5
    keys = ([v] if keep else []) + fresh(h, rng.randint(1 if keep else 2, 3))
    parts = {k: set(subset(rng, inc)) for k in keys}
    for e in inc - set().union(*parts.values()):  # pragma: no cover - subsets are non-empty
        parts[rng.choice(keys)].add(e)
    return DelEq(v, {k: fs(es) for k, es in parts.items()})


def random_case(seed: int, kind: str) -> tuple[ModificationResult, GHD]:
    rng = random.Random(f"{kind}-{seed}")
    h = random_hypergraph(rng)
    _, g = exact_ghw(h)
    return random_modification(rng, h, kind).apply(h), g


# ------------------------------------------------------------------ reversed-order Alg 2
def alg2_with_order(change: ModificationResult, g: GHD, semantics: Semantics,
                    order: Callable[[list[NodeId]], list[NodeId]]) -> frozenset[NodeId]:
    """Test-local Algorithm 2 with a pluggable leaf order (lines 2-14, test via Def 4.1)."""
    t_prime = fs(g.node_ids())
    changed = True
    while changed:
        changed = False
        for u in order(g.leaves_of(t_prime)):
            if mutable_conditions(change, g, t_prime - {u}, semantics).mutable:
                t_prime = t_prime - {u}
                changed = True
                break
    return t_prime


def _reverse(xs: list[NodeId]) -> list[NodeId]:
    return list(reversed(xs))


# ------------------------------------------------------------------ the differential check
def check_case(change: ModificationResult, g: GHD, stats: Counter[str]) -> None:
    assert validate(change.old, g).ok
    res = minimal_mutable_subtree(change, g, EDGEWISE)
    t_star = res.t_star
    stats["cases"] += 1
    stats["empty_t_star"] += not t_star
    stats["whole_tree"] += t_star == fs(g.node_ids())

    # (1) Lemma 4.4: unique minimum under EDGEWISE, equal to Alg 2's output
    found = all_mutable_subtrees(change, g, EDGEWISE)
    minima = [t for t in found if len(t) == len(found[0])]
    assert len(minima) == 1, (change.description, minima)
    assert t_star == minima[0], (change.description, sorted(t_star), sorted(minima[0]))

    # (2) Def 4.1 holds for the result
    assert mutable_conditions(change, g, t_star, EDGEWISE).mutable

    # (3) SET reading: record, do not assert minimality / uniqueness
    assert mutable_conditions(change, g, t_star, SET).mutable
    set_found = all_mutable_subtrees(change, g, SET)
    set_minima = [t for t in set_found if len(t) == len(set_found[0])]
    stats["edgewise_t_star_not_set_minimum"] += t_star not in set_minima
    stats["set_minimum_not_unique"] += len(set_minima) > 1
    set_alg2 = minimal_mutable_subtree(change, g, SET).t_star
    assert set_alg2 in set_found
    stats["set_alg2_differs_from_edgewise"] += set_alg2 != t_star
    stats["set_alg2_not_set_minimum"] += set_alg2 not in set_minima

    # (4) order independence under EDGEWISE
    assert alg2_with_order(change, g, EDGEWISE, _reverse) == t_star
    assert alg2_with_order(change, g, EDGEWISE, list) == t_star


def run(seeds: range) -> Counter[str]:
    stats: Counter[str] = Counter()
    for kind in KINDS:
        for seed in seeds:
            change, g = random_case(seed, kind)
            if len(g) > MAX_BRUTE_NODES:  # pragma: no cover - witness has <= 8 nodes
                stats["skipped_large"] += 1
                continue
            check_case(change, g, stats)
            stats[f"kind_{kind}"] += 1
    return stats


def _report(stats: Counter[str]) -> None:
    print("\nS9 differential stats:", dict(sorted(stats.items())))


@pytest.mark.parametrize("kind", KINDS)
def test_alg2_matches_oracle_per_kind(kind: str) -> None:
    stats: Counter[str] = Counter()
    for seed in range(60):
        change, g = random_case(seed, kind)
        check_case(change, g, stats)
    assert stats["cases"] == 60


def test_differential_summary() -> None:
    """Default-size run with recorded SET statistics (print visible with -s)."""
    stats = run(range(60, 460))
    _report(stats)
    assert stats["cases"] == 6 * 400
    # sanity: the generator exercises both extremes of T*
    assert stats["empty_t_star"] > 0 and stats["whole_tree"] > 0


@pytest.mark.slow
def test_differential_large() -> None:
    stats = run(range(1000, 3000))
    _report(stats)
    assert stats["cases"] == 6 * 2000

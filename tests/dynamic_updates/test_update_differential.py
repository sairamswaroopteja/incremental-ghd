"""S12, Level 5: differential testing of SearchUpdateGHD against the exact oracle.

For random small hypergraphs H with a MINIMAL-width normal-form GHD (from the EXACT decomposer)
and a random valid modification of each of the six classes, every strategy must answer:
  UPDATED   iff ghw(delta(H)) <= k   (oracle, S5), with a valid output of width <= k;
  PROVEN_NO iff ghw(delta(H)) >  k;
and never NOT_FOUND (EXACT decomposer, no budget). All strategies must agree. The PAPER strategy's
outputs must be in normal form unless they come from the DelVar fast path (L-A29).
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from ighd.common import DecomposerMode, UpdateStatus
from ighd.common.errors import InvalidModificationError
from ighd.ghd import check_normal_form, validate
from ighd.oracle import exact_ghw
from ighd.static import ghw_by_search
from ighd.testing import KINDS, random_hypergraph, random_modification
from ighd.update import Strategy, ghd_update


def _family(rng: random.Random):
    if rng.random() < 0.2:      # denser rank-2 graphs (at this size they rarely reach ghw 3)
        return random_hypergraph(rng, min_vertices=5, max_vertices=6, min_edges=7, max_edges=10, max_rank=2)
    return random_hypergraph(rng)


def run(seed: int, n: int) -> Counter:
    rng = random.Random(seed)
    st: Counter = Counter()
    while st["cases"] < n:
        h = _family(rng)
        k, base, _ = ghw_by_search(h, DecomposerMode.EXACT)
        if base is None or len(base) < 2:
            continue
        kind = rng.choice(KINDS)
        mod = random_modification(rng, h, kind)
        if mod is None:
            continue
        try:
            new = mod.apply(h).new
        except InvalidModificationError:
            continue
        truth = exact_ghw(new)[0] if new.edge_names else 0
        st["cases"] += 1
        st[f"ghw_in:{k}"] += 1
        st["width_rises" if truth > k else "width_kept"] += 1
        statuses = set()
        for strategy, fast in ((Strategy.PAPER, True), (Strategy.PAPER, False),
                               (Strategy.THEOREM45, True), (Strategy.RECOMPUTE, True)):
            r = ghd_update(h, base, mod, strategy=strategy, delvar_fast_path=fast)
            statuses.add(r.status)
            assert r.status is not UpdateStatus.NOT_FOUND, (kind, h.edges)
            assert (r.status is UpdateStatus.UPDATED) == (truth <= k), (strategy, kind, h.edges, truth, k)
            if r.ghd is not None:
                rep = validate(new, r.ghd)
                assert rep.ok and rep.width <= k, (strategy, kind, rep.violations)
                nf = check_normal_form(new, r.ghd).ok
                if strategy is Strategy.PAPER and not (kind == "DelVar" and fast):
                    assert nf, ("Algorithm 5 output not in normal form", kind, h.edges)
                if strategy is Strategy.PAPER and fast and kind != "DelVar" and r.trace.t_star is not None:
                    st["paper_reused_old_nodes"] += len(r.trace.reused_nodes)
                    st["paper_old_nodes"] += len(base)
                    st["t_star_proper"] += 0 < len(r.trace.t_star) < len(base)
        assert len(statuses) == 1, statuses
    return st


def test_update_agrees_with_oracle() -> None:
    st = run(seed=20261116, n=150)
    print(dict(sorted(st.items())))
    assert st["width_rises"] >= 10 and st["ghw_in:2"] >= 15     # the corpus exercises both answers


@pytest.mark.slow
def test_update_agrees_with_oracle_large() -> None:
    for seed in (11, 12, 13):
        print(dict(sorted(run(seed=seed, n=600).items())))

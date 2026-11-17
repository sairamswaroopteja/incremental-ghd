"""S12, Level 6: randomized SEQUENCES of updates, each step checked independently.

A chain starts from a minimal NF GHD and applies random elementary modifications (and,
occasionally, a composed two-step ModificationSequence; random composites rarely hit the L-A26
condition (iii), which is covered deterministically in test_update_paper_examples.py).
Each step uses the PAPER strategy with the DelVar fast path off (L-A29: keeps every output in
normal form, which Def 5.1 requires of the next step's input). After every step:
  * the answer agrees with the exact oracle (UPDATED iff ghw(delta(H)) <= k);
  * an UPDATED output validates against delta(H), has width <= k, and is in normal form;
  * on PROVEN_NO the oracle confirms ghw(delta(H)) > k, and the chain continues from a fresh
    minimal GHD of delta(H) whose width the oracle confirms (S13);
  * the chain's first GHD has width ghw(H) by the oracle (S13).
Seeds are fixed; a failure message contains the seed, the step, the hypergraph and the modification.
S13 (agent T) added test_random_update_chains_10k: the plan's >= 10^4-step criterion.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from ighd.common import DecomposerMode, UpdateStatus
from ighd.common.errors import InvalidModificationError
from ighd.ghd import check_normal_form, validate
from ighd.modifications import ModificationSequence
from ighd.oracle import exact_ghw
from ighd.static import ghw_by_search
from ighd.testing import KINDS, random_hypergraph, random_modification
from ighd.update import Strategy, ghd_update


def run_chains(seed: int, chains: int, steps: int) -> Counter:
    rng = random.Random(seed)
    st: Counter = Counter()
    done = 0
    while done < chains:
        h = random_hypergraph(rng)
        k, g, _ = ghw_by_search(h, DecomposerMode.EXACT)
        if g is None or len(g) < 2:
            continue
        assert k == exact_ghw(h)[0], (seed, dict(h.edges))   # chain starts from a MINIMAL GHD
        done += 1
        for step in range(steps):
            if len(h.vertices) > 12 or not h.edge_names:
                break
            composite = rng.random() < 0.15
            if composite:
                parts = [random_modification(rng, h, rng.choice(KINDS))]
                if parts[0] is None:
                    continue
                try:
                    mid = parts[0].apply(h).new
                except InvalidModificationError:
                    continue
                second = random_modification(rng, mid, rng.choice(KINDS)) if mid.edge_names else None
                if second is None:
                    continue
                mod = ModificationSequence((parts[0], second))
            else:
                mod = random_modification(rng, h, rng.choice(KINDS))
                if mod is None:
                    continue
            try:
                new = mod.apply(h).new
            except InvalidModificationError:
                st["skipped_invalid"] += 1     # e.g. a second AddVar("z") while z exists
                continue
            if not new.edge_names or len(new.vertices) > 14:
                break
            r = ghd_update(h, g, mod, strategy=Strategy.PAPER, delvar_fast_path=False)
            truth = exact_ghw(new)[0]
            ctx = (seed, step, dict(h.edges), mod)
            assert r.status is not UpdateStatus.NOT_FOUND, ctx
            assert (r.status is UpdateStatus.UPDATED) == (truth <= k), (ctx, truth, k)
            st["steps"] += 1
            st["composite"] += composite
            st[f"kind:{type(mod).__name__}"] += 1
            st[f"k:{k}"] += 1
            st["a26_fallback"] += any("L-A26" in n for n in r.trace.notes)
            if r.status is UpdateStatus.UPDATED:
                rep = validate(new, r.ghd)
                assert rep.ok and rep.width <= k, (ctx, rep.violations)
                assert check_normal_form(new, r.ghd).ok, ctx
                st["updated"] += 1
                h, g = new, r.ghd
                k = rep.width        # the output's width; may exceed ghw(new) (minimality ASSUMED)
                st["non_minimal_input_next"] += rep.width > truth
            else:
                assert r.status is UpdateStatus.PROVEN_NO and truth > k, (ctx, truth, k)
                st["proven_no"] += 1
                k, g, _ = ghw_by_search(new, DecomposerMode.EXACT)
                assert k == truth, (ctx, k, truth)                # restart from a MINIMAL GHD
                h = new
    return st


def test_random_update_chains() -> None:
    st = run_chains(seed=4242, chains=40, steps=8)
    print(dict(sorted(st.items())))
    assert st["steps"] >= 200 and st["proven_no"] >= 5 and st["composite"] >= 10


@pytest.mark.slow
def test_random_update_chains_large() -> None:
    for seed in (1, 2, 3, 4):
        print(dict(sorted(run_chains(seed=seed, chains=100, steps=12).items())))


# S13 done criterion (IMPLEMENTATION_PLAN §C, S13): at least 10^4 seeded chain steps, every step
# with exactly the checks of run_chains. Chains of up to 20 modifications (plan §F, Level 6); a
# chain stops early once delta(H) has more than 12 vertices (oracle size limits), so a seed yields
# about 1,000-1,100 steps. Seeds 101-120 are independent of the seeds above.
SEEDS_10K = tuple(range(101, 121))


@pytest.mark.slow
def test_random_update_chains_10k() -> None:
    total: Counter = Counter()
    for seed in SEEDS_10K:
        st = run_chains(seed=seed, chains=100, steps=20)
        print(seed, dict(sorted(st.items())))
        total += st
    print("total", dict(sorted(total.items())))
    assert total["steps"] >= 10_000, total["steps"]
    assert total["updated"] + total["proven_no"] == total["steps"]
    assert total["proven_no"] > 0 and total["composite"] > 0

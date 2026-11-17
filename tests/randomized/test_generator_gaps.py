"""S13, Levels 5/6: randomized checks for cases the shared generator (ighd.testing) never produces,
and direct tests of two proven lemmas that were previously pinned only indirectly.

The shared generator always merges AddEq into one of the merged vertices (w in U), always keeps
the split vertex in DelEq, and AddConstr only touches at most one fresh vertex. This module
widens the modification distribution (A8: AddEq into a FRESH vertex; DelEq with both parts new;
AddConstr made only of fresh vertices, A12; merges of three vertices) and checks:

  (1) Lemma G (MATHEMATICAL_INVARIANTS §4): for each of the six elementary classes, EVERY
      delta-mutable subtree (brute force, oracle.all_mutable_subtrees, <= 12 nodes) satisfies
      condition (iii): every new or changed edge of delta(H) lies inside
      V* = (B(T*) n V(delta(H))) u V_new. The check is written here from the definition, not
      taken from ighd.update. A non-vacuity check shows it rejects the A26 counterexample.
  (2) Level 5 on the widened distribution: PAPER (fast path off and on), THEOREM45 and RECOMPUTE
      answer UPDATED iff ghw(delta(H)) <= k (exact oracle), never NOT_FOUND; every output
      validates with width <= k; Algorithm 5 outputs are in normal form.
  (3) Lemma H (MATHEMATICAL_INVARIANTS §6): with restrict_reused_bags=True the PAPER strategy
      gives the same, oracle-confirmed answers and only valid outputs.
Seeds are fixed; every assertion carries the instance.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from ighd.common import DecomposerMode, UpdateStatus
from ighd.common.config import Semantics
from ighd.common.errors import InvalidModificationError
from ighd.ghd import GHD, check_normal_form, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import (AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar,
                                ModificationResult, ModificationSequence)
from ighd.oracle import MAX_BRUTE_NODES, all_mutable_subtrees, exact_ghw
from ighd.static import ghw_by_search
from ighd.testing import KINDS, random_hypergraph, random_modification
from ighd.update import Strategy, ghd_update

RESTRICT = Semantics(restrict_reused_bags=True)


def widened_modification(rng: random.Random, h: Hypergraph, kind: str):
    """Like ighd.testing.random_modification, but half of the AddEq/DelEq/AddConstr draws use the
    variants the shared generator never produces."""
    verts = sorted(h.vertices)
    if rng.random() < 0.5:
        return random_modification(rng, h, kind)
    if kind == "AddEq" and len(verts) >= 2:
        merge = frozenset(rng.sample(verts, rng.randint(2, min(3, len(verts)))))
        into = "x" if rng.random() < 0.6 else rng.choice(sorted(merge))   # A8: w not in U
        return AddEq(merge, into)
    if kind == "DelEq":
        deg2 = [v for v in verts if len(h.incident(v)) >= 2]
        if not deg2:
            return None
        v = rng.choice(deg2)
        inc = sorted(h.incident(v))
        first = frozenset(rng.sample(inc, rng.randint(1, len(inc) - 1)))
        return DelEq(v, {"p1": first, "p2": frozenset(inc) - first})   # v disappears, both new
    if kind == "AddConstr":
        return AddConstr("wnew", frozenset({"x", "y"}))                  # only fresh vertices (A12)
    return random_modification(rng, h, kind)


def escaping_edges(change: ModificationResult, ghd: GHD, t_star: frozenset[int]) -> list[str]:
    """Condition (iii) from its definition: new or changed edges of delta(H) not inside V*."""
    bag_union: set[str] = set()
    for u in t_star:
        bag_union |= ghd.node(u).bag
    v_star = (bag_union & change.new.vertices) | change.new_vertices
    preimage = {new: old for old, new in change.s_delta.items() if new is not None}
    out = []
    for name, vs in change.new.edges.items():
        old = preimage.get(name)
        changed = old is None or change.old.edge(old) != vs
        if changed and not vs <= v_star:
            out.append(name)
    return sorted(out)


def _instances(seed: int, n: int):
    """Yield (h, k, minimal NF GHD, modification, kind, change) for n valid random cases."""
    rng = random.Random(seed)
    done = 0
    while done < n:
        if rng.random() < 0.2:     # denser rank-2 graphs, as in Level 5, so that ghw rises occur
            h = random_hypergraph(rng, min_vertices=5, max_vertices=6, min_edges=7, max_edges=10,
                                  max_rank=2)
        else:
            h = random_hypergraph(rng)
        k, g, _ = ghw_by_search(h, DecomposerMode.EXACT)
        if g is None or len(g) < 2 or len(g) > MAX_BRUTE_NODES:
            continue
        kind = rng.choice(KINDS)
        mod = widened_modification(rng, h, kind)
        if mod is None:
            continue
        try:
            change = mod.apply(h)
        except InvalidModificationError:
            continue
        done += 1
        yield h, k, g, mod, kind, change


# ------------------------------------------------------------------------------------ (1) Lemma G
def run_lemma_g(seed: int, n: int) -> Counter:
    st: Counter = Counter()
    for h, _k, g, mod, kind, change in _instances(seed, n):
        subtrees = all_mutable_subtrees(change, g)
        assert subtrees, (kind, dict(h.edges), mod)       # the whole tree is always mutable
        for t in subtrees:
            bad = escaping_edges(change, g, t)
            assert not bad, ("Lemma G violated", kind, dict(h.edges), mod, sorted(t), bad)
        st["cases"] += 1
        st[f"kind:{kind}"] += 1
        st["mutable_subtrees_checked"] += len(subtrees)
        st["fresh_target_addeq"] += kind == "AddEq" and mod.into not in h.vertices
    return st


def test_condition_iii_check_is_not_vacuous() -> None:
    """The A26 counterexample (a composed delta) violates (iii) for T* = {u2}; elementary ones
    cannot (Lemma G)."""
    h = Hypergraph({"e1": "ab", "e2": "bc"})
    g = GHD.from_spec({"root": "u1", "nodes": {"u1": ("ab", ("e1",)), "u2": ("bc", ("e2",))},
                       "children": {"u1": ["u2"]}})
    change = ModificationSequence((AddVar("z", frozenset({"e1"})),
                                   AddEq(frozenset({"z", "c"}), "c"))).apply(h)
    u2 = g.by_label("u2")
    assert frozenset({u2}) in all_mutable_subtrees(change, g)
    assert escaping_edges(change, g, frozenset({u2})) == ["e1"]


def test_lemma_g_every_mutable_subtree_satisfies_condition_iii() -> None:
    st = run_lemma_g(seed=1313, n=300)
    print(dict(sorted(st.items())))
    assert all(st[f"kind:{k}"] >= 20 for k in KINDS), st
    assert st["fresh_target_addeq"] >= 10, st


# ------------------------------------------------------------------- (2) + (3) updates vs oracle
VARIANTS = (
    ("paper", Strategy.PAPER, False, None),
    ("paper_fast", Strategy.PAPER, True, None),
    ("paper_restrict", Strategy.PAPER, False, RESTRICT),      # Lemma H
    ("theorem45", Strategy.THEOREM45, True, None),
    ("recompute", Strategy.RECOMPUTE, True, None),
)


def run_updates(seed: int, n: int) -> Counter:
    st: Counter = Counter()
    for h, k, g, mod, kind, change in _instances(seed, n):
        new = change.new
        truth = exact_ghw(new)[0] if new.edge_names else 0
        st["cases"] += 1
        st[f"kind:{kind}"] += 1
        st["width_rises" if truth > k else "width_kept"] += 1
        for name, strategy, fast, semantics in VARIANTS:
            kwargs = {"semantics": semantics} if semantics is not None else {}
            r = ghd_update(h, g, mod, strategy=strategy, delvar_fast_path=fast, **kwargs)
            ctx = (name, kind, dict(h.edges), mod, truth, k)
            assert r.status is not UpdateStatus.NOT_FOUND, ctx
            assert (r.status is UpdateStatus.UPDATED) == (truth <= k), ctx
            if r.status is UpdateStatus.PROVEN_NO:
                assert truth > k, ctx
                continue
            rep = validate(new, r.ghd)
            assert rep.ok and rep.width <= k, (ctx, rep.violations)
            if strategy is Strategy.PAPER and not (kind == "DelVar" and fast):
                assert check_normal_form(new, r.ghd).ok, ("Alg 5 output not NF", ctx)
            if name == "paper_restrict":
                st["restrict_updated"] += 1
    return st


def test_updates_on_widened_distribution_agree_with_oracle() -> None:
    st = run_updates(seed=2718, n=400)
    print(dict(sorted(st.items())))
    assert st["width_rises"] >= 5 and st["width_kept"] >= 100, st
    assert all(st[f"kind:{k}"] >= 15 for k in KINDS), st


@pytest.mark.slow
def test_widened_distribution_large() -> None:
    for seed in (31, 32, 33):
        print("lemma G", seed, dict(sorted(run_lemma_g(seed=seed, n=1000).items())))
        print("updates", seed, dict(sorted(run_updates(seed=seed, n=1000).items())))

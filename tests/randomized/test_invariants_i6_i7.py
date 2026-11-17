"""S15 gap closure: direct tests of invariants I6 and I7 (MATHEMATICAL_INVARIANTS §1), which the
S13 traceability audit found pinned only indirectly.

I7 (Lemma 4.4): Algorithm 2's working tree is delta-mutable at EVERY step, not only at the end.
    The step log is replayed: after each accepted removal the working tree is T minus
    ``step.outside``; it must be one of the delta-mutable subtrees found by the brute-force oracle
    (oracle.all_mutable_subtrees, an independent implementation of Def 4.1). The initial working
    tree (all of T) must be mutable too. A runtime assertion in ``minimal_mutable_subtree`` guards
    the connectedness part; ``test_i7_assertion_fires`` shows it is live.

I6 (Thm 4.5 (W), Alg 5 L6, L-A20): a reused old node u keeps its cover as delta(lambda_u), so a
    cover is never enlarged and has at most k edges. Checked for every reused node of every UPDATED
    result under PAPER (literal default and restrict_reused_bags=True) and THEOREM45. Bags:
    PAPER literal and THEOREM45 keep delta(B_u) exactly; the restricted variant keeps a subset.
    Reused nodes are identified by label: the old GHD is relabelled uniquely, reused nodes keep
    their label and decomposer-made nodes have none.
Seeds are fixed; every assertion carries the instance.
"""

from __future__ import annotations

import dataclasses
import random
from collections import Counter

import pytest

from ighd.common import DecomposerMode, UpdateStatus
from ighd.common.config import Semantics
from ighd.common.errors import InvalidModificationError
from ighd.ghd import GHD
from ighd.hypergraph import Hypergraph
from ighd.modifications import DelConstr
from ighd.mutable import minimal_mutable_subtree, mutable_conditions
from ighd.oracle import MAX_BRUTE_NODES, all_mutable_subtrees
from ighd.static import ghw_by_search
from ighd.testing import KINDS, random_hypergraph, random_modification
from ighd.update import Strategy, ghd_update
from ighd.update.decomp_update import delta_bag, delta_cover
from tests.fixtures.paper import G2_SPEC, H_P2


def _cases(seed: int, n: int):
    """Yield (h, k, labelled minimal NF GHD, modification, change) for n valid random cases."""
    rng = random.Random(seed)
    done = 0
    while done < n:
        if rng.random() < 0.2:
            h = random_hypergraph(rng, min_vertices=5, max_vertices=6, min_edges=7, max_edges=10,
                                  max_rank=2)
        else:
            h = random_hypergraph(rng)
        k, g, _ = ghw_by_search(h, DecomposerMode.EXACT)
        if g is None or len(g) < 2 or len(g) > MAX_BRUTE_NODES:
            continue
        mod = random_modification(rng, h, rng.choice(KINDS))
        if mod is None:
            continue
        try:
            change = mod.apply(h)
        except InvalidModificationError:
            continue
        if not change.new.edge_names:
            continue
        done += 1
        yield h, k, GHD.from_spec(g.to_spec()), mod, change     # from_spec labels every node


# ------------------------------------------------------------------------------------------ I7
def run_i7(seed: int, n: int) -> Counter:
    st: Counter = Counter()
    for h, _, g, mod, change in _cases(seed, n):
        ctx = (seed, dict(h.edges), mod)
        mutable = set(all_mutable_subtrees(change, g))
        everything = frozenset(g.node_ids())
        assert everything in mutable, ctx                      # the initial working tree
        res = minimal_mutable_subtree(change, g)
        for step in res.steps:
            if step.accepted:
                working = everything - step.outside
                assert working in mutable, (ctx, step)
                st["intermediate_trees"] += 1
        assert res.t_star in mutable, ctx
        st["cases"] += 1
    return st


def test_i7_every_intermediate_working_tree_is_mutable() -> None:
    st = run_i7(seed=7007, n=300)
    print(dict(st))
    assert st["cases"] == 300 and st["intermediate_trees"] >= 100    # not vacuous (153 observed)


@pytest.mark.slow
def test_i7_every_intermediate_working_tree_is_mutable_large() -> None:
    st = run_i7(seed=7008, n=3000)
    print(dict(st))
    assert st["cases"] == 3000 and st["intermediate_trees"] >= 1000


def test_i7_assertion_fires(monkeypatch: pytest.MonkeyPatch) -> None:
    """The runtime guard is live: a broken leaf enumeration offering an inner node (whose
    removal disconnects the tree) is caught instead of silently producing a non-subtree."""
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    change = DelConstr("w7").apply(h)
    inner = [u for u in g.node_ids() if len(g.tree_neighbors(u)) >= 2]
    assert inner
    monkeypatch.setattr(GHD, "leaves_of", lambda self, working: [inner[0]])
    real = mutable_conditions

    def accept_everything(*args, **kwargs):          # make (i) and (ii) pass, keep is_subtree
        return dataclasses.replace(real(*args, **kwargs), condition_i=True, condition_ii=True)

    monkeypatch.setattr("ighd.mutable.minimal.mutable_conditions", accept_everything)
    with pytest.raises(AssertionError, match="I7 violated"):
        minimal_mutable_subtree(change, g)


# ------------------------------------------------------------------------------------------ I6
VARIANTS = (
    ("paper-literal", Strategy.PAPER, Semantics()),
    ("paper-restricted", Strategy.PAPER, Semantics(restrict_reused_bags=True)),
    ("theorem45", Strategy.THEOREM45, Semantics()),
)


def run_i6(seed: int, n: int) -> Counter:
    st: Counter = Counter()
    for h, k, g, mod, change in _cases(seed, n):
        for name, strategy, sem in VARIANTS:
            r = ghd_update(h, g, mod, strategy=strategy, semantics=sem, delvar_fast_path=False)
            if r.status is not UpdateStatus.UPDATED:
                continue
            out = r.ghd
            for u in r.trace.reused_nodes:
                ctx = (seed, name, dict(h.edges), mod, g.node(u))
                label = g.node(u).label
                v = out.node(out.by_label(label))
                assert v.cover == delta_cover(change, g, u), ctx          # never enlarged
                assert len(v.cover) <= k, ctx
                if name == "paper-restricted":
                    assert v.bag <= delta_bag(change, g, u), ctx
                else:
                    assert v.bag == delta_bag(change, g, u), ctx
                st[f"reused:{name}"] += 1
            st[f"updated:{name}"] += 1
    return st


def test_i6_reused_covers_are_delta_images() -> None:
    st = run_i6(seed=6006, n=200)
    print(dict(st))
    for name, _, _ in VARIANTS:
        assert st[f"reused:{name}"] >= 50, (name, dict(st))    # not vacuous (THEOREM45: 93 observed)


@pytest.mark.slow
def test_i6_reused_covers_are_delta_images_large() -> None:
    st = run_i6(seed=6007, n=2000)
    print(dict(st))
    for name, _, _ in VARIANTS:
        assert st[f"reused:{name}"] >= 500, (name, dict(st))

"""S11: scene creation (Algorithms 3 and 4) on crafted and random inputs.

Ledger entries exercised: L-A16 (line 3), L-A17 (up-scene key), L-A20 (delta on labels),
L-A23 (strict matching), L-A25 (kind of a scene at an ancestor of T*).
"""

from __future__ import annotations

import random
import time
from collections import Counter

import pytest

from ighd.common.config import Semantics
from ighd.common.errors import NotNormalFormError
from ighd.common.types import DecomposerMode, EdgeSet, NodeId, VertexSet
from ighd.ghd import GHD, check_normal_form
from ighd.hypergraph.core import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, ModificationResult
from ighd.mutable import minimal_mutable_subtree
from ighd.scenes import SceneEvent, SceneKind, SceneMapping, scene_create, scene_create_up
from ighd.static import components, ghw_by_search
from tests.fixtures.paper import G_PRIME_SPEC, H_PP
from tests.unit.test_mutable_differential import KINDS, random_hypergraph, random_modification

fs = frozenset

# A small width-2 GHD used for the crafted cases: the root bag {v,s,t} is guarded by e1, e2; each
# child holds one edge through v. Every node contains v, so any new vertex next to v puts the
# whole tree in T*.
SMALL = {"a": "vx", "b": "vy", "e1": "vs", "e2": "vt"}
SMALL_SPEC = {
    "root": "r",
    "nodes": {"r": ("vst", ("e1", "e2")), "u1": ("vx", ("a",)), "u2": ("vy", ("b",))},
    "children": {"r": ["u1", "u2"], "u1": [], "u2": []},
}
# SMALL plus a third child u3 = {v, q} holding c = {v, q}.
SMALL3 = {**SMALL, "c": "vq"}
SMALL3_SPEC = {
    "root": "r",
    "nodes": {**SMALL_SPEC["nodes"], "u3": ("vq", ("c",))},
    "children": {"r": ["u1", "u2", "u3"], "u1": [], "u2": [], "u3": []},
}


def _run(h: dict[str, str] | dict[str, frozenset[str]], spec: dict, mod: object,
         semantics: Semantics = Semantics()
         ) -> tuple[ModificationResult, GHD, frozenset[NodeId], SceneMapping, list[SceneEvent]]:
    g = GHD.from_spec(spec)  # type: ignore[arg-type]
    change = mod.apply(Hypergraph(h))  # type: ignore[attr-defined]
    t_star = minimal_mutable_subtree(change, g).t_star
    sigma, events = scene_create(change, g, t_star, semantics)
    return change, g, t_star, sigma, events


def _labels(g: GHD, sigma: SceneMapping) -> dict[frozenset[str], tuple[str | None, str, str]]:
    return {k: (g.node(e.node).label, e.kind.value, e.origin) for k, e in sigma.items()}


def _lines(g: GHD, events: list[SceneEvent]) -> list[tuple[str, str | None]]:
    return [(e.line, g.node(e.node).label) for e in events]


def _identity(h: Hypergraph) -> ModificationResult:
    return ModificationResult(kind="identity", old=h, new=h, s_delta={e: e for e in h.edge_names},
                              new_edges=fs(), new_vertices=fs(), removed_vertices=fs(),
                              description="identity (hand-built)")


# ----------------------------------------------------------------------------- identity change
def test_identity_change_gives_out_scene_for_every_handled_set() -> None:
    h = Hypergraph(H_PP)
    g = GHD.from_spec(G_PRIME_SPEC)
    change = _identity(h)
    assert minimal_mutable_subtree(change, g).t_star == fs()
    sigma, events = scene_create(change, g, fs())
    handled = check_normal_form(h, g).handled
    assert {k: (e.node, e.kind, e.origin) for k, e in sigma.items()} == {
        edges: (n, SceneKind.OUT, "down") for n, edges in handled.items()}
    assert len(sigma) == len(g) and sigma.overwritten == []
    assert {e.line for e in events} == {"A3:L12", "A3:L16"}
    assert sum(e.line == "A3:L12" for e in events) == len(g)


def test_t_star_whole_tree_gives_no_out_scene() -> None:
    """Edge case: T* = T. Every down-scene is IN and Alg 4 records nothing."""
    h = Hypergraph(H_PP)
    g = GHD.from_spec(G_PRIME_SPEC)
    sigma, _ = scene_create(_identity(h), g, fs(g.node_ids()))
    assert {e.kind for _, e in sigma.items()} == {SceneKind.IN}
    assert len(sigma) == len(g)


def test_empty_ghd_of_empty_hypergraph() -> None:
    sigma, events = scene_create(_identity(Hypergraph({})), GHD(), fs())
    assert len(sigma) == 0 and events == []


# ----------------------------------------------------------------------------- A25
@pytest.mark.paper_discrepancy
def test_ancestor_of_t_star_gets_in_scene() -> None:
    """L-A25. Fig. 3 rerooted at t2 (still in normal form); AddVar(m, {w6}) gives T* = {t1, t4}.
    The root t2 is outside T* but T_t2 contains T*: Alg 3 line 9 records an IN-scene (single
    use), whereas Def 5.1 (in-scene iff sigma(H') in T*) would call it an out-scene."""
    h = Hypergraph(H_PP)
    g = GHD.from_spec(G_PRIME_SPEC)
    t2 = g.by_label("t2")
    g.reroot(t2)
    assert check_normal_form(h, g).ok
    change = AddVar("m", fs({"w6"})).apply(h)
    t_star = minimal_mutable_subtree(change, g).t_star
    assert t_star == fs({g.by_label("t1"), g.by_label("t4")})
    assert t2 not in t_star
    sigma, events = scene_create(change, g, t_star)
    root_entry = sigma.peek(change.new.edge_names)
    assert root_entry is not None
    assert (root_entry.node, root_entry.kind, root_entry.origin) == (t2, SceneKind.IN, "down")
    assert any(e.line == "A3:L10" and e.node == t2 and "ancestor, L-A25" in e.detail for e in events)
    assert _labels(g, sigma) == {
        change.new.edge_names: ("t2", "in", "down"),
        fs({"w4"}): ("t3", "out", "down"),
        fs({"w3", "w5", "w6"}): ("t1", "in", "down"),
    }
    # the root's in-scene is single use, unlike an out-scene
    assert sigma.lookup(change.new.edge_names) is not None
    assert sigma.lookup(change.new.edge_names) is None


# ----------------------------------------------------------------------------- A23
def _deleq_two_children_one_component() -> DelEq:
    """DelEq(v): a, b receive the new part v1 (joining them outside the root bag) and e1, e2
    receive v2 (turning the former inside edges into a new component). The count of root
    components stays 2 = |children|, but both children touch the merged component {a, b}."""
    return DelEq("v", {"v": fs({"a", "b", "e1", "e2"}), "v1": fs({"a", "b"}), "v2": fs({"e1", "e2"})})


@pytest.mark.paper_discrepancy
def test_literal_first_match_maps_two_children_to_one_component() -> None:
    """L-A23, literal reading: on a valid NF input after one elementary modification, Alg 3
    lines 14-19 send both children u1 and u2 to the same component {a, b}."""
    change, g, _, sigma, events = _run(SMALL, SMALL_SPEC, _deleq_two_children_one_component(),
                                       Semantics(strict_child_matching=False))
    assert check_normal_form(change.old, g).ok
    root_comps = components(change.new, change.new.edge_names, g.node(g.root).bag)
    assert root_comps == [fs({"a", "b"}), fs({"e1", "e2"})]
    l16 = [(g.node(e.node).label, e.edges) for e in events if e.line == "A3:L16"]
    assert l16 == [("u1", fs({"a", "b"})), ("u2", fs({"a", "b"}))]
    assert not [e for e in events if e.line == "A3:L20"]
    assert _labels(g, sigma) == {change.new.edge_names: ("r", "in", "down")}


def test_strict_matching_goes_upward_instead() -> None:
    """L-A23, default: the component {a, b} is already matched to u1, {e1, e2} does not meet
    u2's bag outside the separator, so line 20 runs and the root's scene is discarded."""
    _, g, t_star, sigma, events = _run(SMALL, SMALL_SPEC, _deleq_two_children_one_component())
    assert t_star == fs(g.node_ids())
    l20 = [e for e in events if e.line == "A3:L20"]
    assert len(l20) == 1 and l20[0].node == g.root
    assert "already matched to an earlier child" in l20[0].detail
    assert len(sigma) == 0


# ----------------------------------------------------------------------------- L7 and L20
def test_line7_count_mismatch_goes_upward() -> None:
    """AddConstr f = {x, y} joins the components {a} and {b} below the root: 2 components for 3
    children, so line 7 sends the root to Algorithm 4. u3 lies outside T* and gets an up-scene."""
    _, g, t_star, sigma, events = _run(SMALL3, SMALL3_SPEC, AddConstr("f", fs("xy")))
    assert t_star == fs({g.by_label(x) for x in ("r", "u1", "u2")})
    assert _lines(g, events) == [("A3:L7", "r"), ("A4:L16", "u3")]
    assert "2 [delta(B_n)]-components" in events[0].detail and "3 children" in events[0].detail
    assert _labels(g, sigma) == {fs({"c"}): ("u3", "out", "up")}


def test_line7_on_fig3() -> None:
    """AddConstr {a, j} on Fig. 3 joins the two root components (count 1 vs 2 children)."""
    _, g, _, sigma, events = _run(H_PP, G_PRIME_SPEC, AddConstr("w7", fs("aj")))
    assert _lines(g, events) == [("A3:L7", "t1")]
    assert len(sigma) == 0  # T* is the whole tree, so Algorithm 4 records nothing


@pytest.mark.parametrize("strict", [True, False])
def test_line20_child_without_component(strict: bool) -> None:
    """AddEq merges y (u2's only vertex outside the root bag) and s (a root-bag vertex) into a new
    vertex z. Root components {a}, {b, e1} for 2 children, but delta(B_u2) = {v} meets neither
    outside the separator: line 20 discards the scenes already built (u1's in-scene) in both
    matching modes."""
    _, g, _, sigma, events = _run(SMALL, SMALL_SPEC, AddEq(fs("ys"), "z"),
                                  Semantics(strict_child_matching=strict))
    assert _lines(g, events) == [("A3:L10", "r"), ("A3:L16", "u1"), ("A3:L10", "u1"), ("A3:L20", "r")]
    assert "child 2 matches no component" in events[-1].detail
    assert len(sigma) == 0 and sigma.overwritten == []


# ----------------------------------------------------------------------------- precondition
def test_non_normal_form_input_is_rejected() -> None:
    spec = {
        "root": "t1",
        "nodes": {**G_PRIME_SPEC["nodes"], "t5": ("k", ("w6",))},  # type: ignore[dict-item]
        "children": {**G_PRIME_SPEC["children"], "t4": ["t5"], "t5": []},  # type: ignore[dict-item]
    }
    g = GHD.from_spec(spec)  # type: ignore[arg-type]
    h = Hypergraph(H_PP)
    assert not check_normal_form(h, g).ok
    with pytest.raises(NotNormalFormError):
        scene_create(_identity(h), g, fs())


# ----------------------------------------------------------------------------- Algorithm 4 alone
def test_scene_create_up_standalone_on_ex52_subtree() -> None:
    """SceneCreationUp(u2, {w3, w6}, T*) of Example 5.2 returns ({w6} -> u4, coveredEdges {w6})."""
    from tests.fixtures.paper import G2_SPEC, H_P2

    change = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    t_star = minimal_mutable_subtree(change, g).t_star
    sigma, covered = scene_create_up(change, g, g.by_label("u2"), fs({"w3", "w6"}), t_star)
    assert covered == fs({"w6"})
    assert _labels(g, sigma) == {fs({"w6"}): ("u4", "out", "up")}


def test_up_count_mismatch_and_empty_key_are_logged() -> None:
    """Alg 4 on Fig. 3 (identity change, T* = {}) entered at t1 with H' = {w4}:
    t3 covers w4 -> scene {w4}; t2 covers w4 (comps [{w4}], 1 child) -> scene {w4} again (overwrites
    t3's, the deeper node is visited first); t4 covers nothing (0 comps = 0 children) -> empty key,
    not recorded; t1: [B_t1]-components of {w4} = 1 for 2 children -> line 15 fails."""
    from ighd.scenes.scene_up import _Context, _up

    h = Hypergraph(H_PP)
    g = GHD.from_spec(G_PRIME_SPEC)
    ctx = _Context(_identity(h), g, fs(), Semantics())
    sigma, covered = _up(ctx, g.by_label("t1"), fs({"w4"}))
    assert covered == fs({"w4"})
    assert _labels(g, sigma) == {fs({"w4"}): ("t2", "out", "up")}
    assert [(o.node, n.node) for _, o, n in sigma.overwritten] == [(g.by_label("t3"), g.by_label("t2"))]
    assert _lines(g, ctx.events) == [("A4:L16", "t3"), ("A4:L16", "t2"), ("A4:L16", "t4"), ("A4:L15", "t1")]
    assert ctx.events[2].detail == "empty key: not recorded" and ctx.events[2].edges == fs()


@pytest.mark.paper_discrepancy
def test_child_scene_overwrites_parent_scene_for_same_key() -> None:
    """Not discussed in the paper: Def 5.1 makes sigma a (partial) function, but Alg 3 can record
    the same subhypergraph at a node and at its child. Here the root bag {a, f} loses both vertices
    (DelConstr e1, A7), so delta(B_root) = {} and the single [{}]-component of H' = {e0, e2} is H'
    itself; the child's OUT scene (line 12) replaces the root's IN scene (line 10). We keep the
    later (deeper) entry and record the replacement in ``overwritten``. Found by the random test."""
    h = {"e0": "be", "e1": "af", "e2": "b"}
    spec = {"root": "r", "nodes": {"r": ("af", ("e1",)), "c": ("be", ("e0",))},
            "children": {"r": ["c"], "c": []}}
    change, g, t_star, sigma, events = _run(h, spec, DelConstr("e1"))
    assert check_normal_form(change.old, g).ok
    assert t_star == fs({g.root})
    key = fs({"e0", "e2"})
    assert _lines(g, events) == [("A3:L10", "r"), ("A3:L16", "c"), ("A3:L12", "c")]
    assert _labels(g, sigma) == {key: ("c", "out", "down")}
    [(k, old, new)] = sigma.overwritten
    assert k == key and (old.node, old.kind) == (g.root, SceneKind.IN)
    assert (new.node, new.kind) == (g.by_label("c"), SceneKind.OUT)


# ----------------------------------------------------------------------------- random property
def _subtree_bags(g: GHD, n: NodeId, vs: VertexSet) -> list[VertexSet]:
    return [g.node(x).bag & vs for x in g.preorder(n)]


def _check_case(change: ModificationResult, g: GHD, t_star: frozenset[NodeId],
                sigma: SceneMapping, events: list[SceneEvent], stats: Counter[str]) -> None:
    new = change.new
    vnew = new.vertices
    all_bags = g.bag_union(g.node_ids()) & vnew
    down_records = [(e.edges, e.node) for e in events if e.line in ("A3:L10", "A3:L12")]
    for key, entry in sigma.items():
        n = entry.node
        sub = g.subtree_nodes(n)
        stats[f"{entry.origin}-{entry.kind.value}"] += 1
        if entry.kind is SceneKind.OUT:
            assert not sub & t_star  # (i) an OUT scene's whole subtree lies outside T*
        else:
            assert sub & t_star  # (ii)
            assert entry.origin == "down"
        if entry.origin == "down":
            assert (key, n) in down_records
            # (iii) line 3 held and line 7 matched at n
            d_bag = g.node(n).bag & vnew
            d_cover = fs(t for e in g.node(n).cover if (t := change.s_delta[e]) is not None)
            assert d_bag <= new.covered_vertices(d_cover)
            assert len(components(new, key, d_bag)) == len(g.children(n))
        if entry.kind is SceneKind.OUT:
            # (iv) Every edge of K lies in a delta-bag of T_n, unless it is disjoint from all bags.
            # Up-scenes (COVERED_EDGES): by construction (lines 10-12). Down-scenes: n is reached
            # from its parent p through a vertex w of delta(B_n) outside delta(B_p); by connectedness
            # w occurs only in T_n, inside B(T minus T*). By Lemma 4.2 / Def 4.1 (EDGEWISE) every edge
            # meeting B(T minus T*) is an old edge with the same restriction there, and it gains no
            # vertex outside (a new vertex would be adjacent, violating (ii)); an old edge through a
            # vertex occurring only in T_n is covered in T_n (GHD condition (1) + connectedness).
            # Induction along [delta(B_p)]-adjacency covers all of K. At the root (only when
            # T* = {}), added edges may be disjoint from every bag (A12).
            bags = _subtree_bags(g, n, vnew)
            for e in key:
                ev = new.edge(e)
                assert any(ev <= b for b in bags) or not ev & all_bags, (e, n)


def _random_instance(seed: int) -> tuple[ModificationResult, GHD] | None:
    rng = random.Random(f"s11-{seed}")
    h = random_hypergraph(rng)
    k, g, _ = ghw_by_search(h, DecomposerMode.EXACT)
    assert g is not None and k is not None
    assert check_normal_form(h, g).ok  # Lemma F: decomposer outputs are in replay normal form
    if rng.random() < 0.3 and len(g) > 1:  # vary the root (NF is root-dependent)
        g.reroot(rng.choice(g.node_ids()))
        if not check_normal_form(h, g).ok:
            return None
    mod = random_modification(rng, h, rng.choice(KINDS))
    return mod.apply(h), g


def test_random_properties() -> None:
    stats: Counter[str] = Counter()
    started = time.perf_counter()
    for seed in range(1500):
        inst = _random_instance(seed)
        if inst is None:
            stats["reroot-not-nf"] += 1
            continue
        change, g = inst
        t_star = minimal_mutable_subtree(change, g).t_star
        sigma, events = scene_create(change, g, t_star)  # (v) never raises on valid NF input
        _check_case(change, g, t_star, sigma, events, stats)
        stats["cases"] += 1
        stats["overwritten"] += len(sigma.overwritten)
        stats.update(e.line for e in events)
    elapsed = time.perf_counter() - started
    print(f"\nS11 random properties: {dict(sorted(stats.items()))} in {elapsed:.1f}s")
    assert stats["cases"] >= 1300
    # the generator reaches every branch of Algorithms 3 and 4
    for line in ("A3:L3", "A3:L7", "A3:L10", "A3:L12", "A3:L16", "A4:L16"):
        assert stats[line] > 0, line


# ----------------------------------------------------------------------------- Prop 5.3 sanity
def _path_instance(n_edges: int) -> tuple[Hypergraph, GHD]:
    h = Hypergraph({f"e{i:03d}": (f"x{i:03d}", f"x{i + 1:03d}") for i in range(n_edges)})
    g = GHD()
    parent = None
    for i in range(n_edges):
        parent = g.add_node((f"x{i:03d}", f"x{i + 1:03d}"), (f"e{i:03d}",), parent=parent)
    return h, g


@pytest.mark.slow
def test_prop53_runtime_on_paths() -> None:
    times: dict[int, float] = {}
    for n in (25, 50, 100, 200):
        h, g = _path_instance(n)
        assert check_normal_form(h, g).ok
        change = DelConstr(f"e{n // 2:03d}").apply(h)
        t_star = minimal_mutable_subtree(change, g).t_star
        best = float("inf")
        for _ in range(3):
            started = time.perf_counter()
            sigma, _ = scene_create(change, g, t_star)
            best = min(best, time.perf_counter() - started)
        assert len(sigma) > 0
        times[n] = best
    print("\nProp 5.3 sanity (scene_create seconds):", {n: round(t, 4) for n, t in times.items()})
    assert times[200] < 16 * times[100] + 0.05  # O(N^3) bound x 2, plus timer noise

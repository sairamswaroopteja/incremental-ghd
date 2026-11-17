"""S3 property tests on random trees (deterministic hypothesis runs).

"Done when" of IMPLEMENTATION_PLAN S3: split + glue = original.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ighd.ghd.tree import GHD

SETTINGS = settings(derandomize=True, max_examples=200, deadline=None)


@st.composite
def random_trees(draw: st.DrawFn, max_nodes: int = 30) -> GHD:
    """A random labelled tree from a random parent array, then rerooted at a random node.

    Node i > 0 gets parent ``r_i mod i``; bag and cover are bitmasks over a small alphabet
    (a compact encoding keeps hypothesis generation fast).
    """
    n = draw(st.integers(1, max_nodes))
    rows = draw(st.lists(st.tuples(st.integers(0, 2**20), st.integers(0, 255), st.integers(0, 31)),
                         min_size=n, max_size=n))
    g = GHD()
    for i, (r, bag_bits, cover_bits) in enumerate(rows):
        bag = {v for k, v in enumerate("abcdefgh") if bag_bits >> k & 1}
        cover = {f"w{k + 1}" for k in range(5) if cover_bits >> k & 1}
        g.add_node(bag, cover, parent=None if i == 0 else r % i, label=f"n{i}")
    g.reroot(draw(st.integers(0, len(rows) - 1)))
    return g


@st.composite
def tree_and_connected_set(draw: st.DrawFn) -> tuple[GHD, frozenset[int]]:
    """A random tree with a non-empty connected node set grown from a random start node."""
    g = draw(random_trees())
    start = draw(st.sampled_from(g.node_ids()))
    s = {start}
    for _ in range(draw(st.integers(0, len(g) - 1))):
        frontier = sorted({y for x in s for y in g.tree_neighbors(x)} - s)
        if not frontier:
            break
        s.add(draw(st.sampled_from(frontier)))
    return g, frozenset(s)


def label_edges(g: GHD) -> frozenset[frozenset[str | None]]:
    return frozenset(frozenset({g.node(p).label, g.node(c).label})
                     for c in g.node_ids() if (p := g.parent(c)) is not None)


def id_edges(g: GHD) -> frozenset[frozenset[int]]:
    return frozenset(frozenset({p, c}) for c in g.node_ids() if (p := g.parent(c)) is not None)


def degree_in(g: GHD, x: int, s: frozenset[int]) -> int:
    return sum(1 for y in g.tree_neighbors(x) if y in s)


# ---------------------------------------------------------------------------- traversals
@SETTINGS
@given(random_trees())
def test_traversals_visit_each_node_once(g: GHD) -> None:
    pre, post = g.preorder(), g.postorder()
    assert sorted(pre) == g.node_ids() == sorted(post)
    assert pre[0] == g.root and post[-1] == g.root
    pos_pre = {x: i for i, x in enumerate(pre)}
    pos_post = {x: i for i, x in enumerate(post)}
    for x in g.node_ids():
        if (p := g.parent(x)) is not None:
            assert pos_pre[p] < pos_pre[x] and pos_post[x] < pos_post[p]
        assert set(g.preorder(x)) == g.subtree_nodes(x) == set(g.postorder(x))
        assert all(x in g.subtree_nodes(a) for a in g.ancestors(x))
    assert len(id_edges(g)) == len(g) - 1


@SETTINGS
@given(random_trees(), st.data())
def test_components_partition_and_are_connected(g: GHD, data: st.DataObject) -> None:
    removed = data.draw(st.frozensets(st.sampled_from(g.node_ids())))
    comps = g.components_without(removed)
    union: set[int] = set()
    for c in comps:
        assert c and not (c & union) and not (c & removed)
        assert g.is_connected(c)
        union |= c
        # maximality: no tree edge leaves the component except into `removed`
        assert all(y in c or y in removed for x in c for y in g.tree_neighbors(x))
    assert union == set(g.node_ids()) - removed
    assert [min(c) for c in comps] == sorted(min(c) for c in comps)


@SETTINGS
@given(random_trees(), st.data())
def test_reroot_preserves_undirected_tree(g: GHD, data: st.DataObject) -> None:
    edges, spec_nodes = id_edges(g), {n.id: n for n in g}
    target = data.draw(st.sampled_from(g.node_ids()))
    old_children = {x: g.children(x) for x in g.node_ids()}
    g.reroot(target)
    assert g.root == target and g.parent(target) is None
    assert id_edges(g) == edges
    assert {n.id: n for n in g} == spec_nodes
    for x in g.node_ids():  # previous children keep their relative order, as a prefix
        kept = tuple(c for c in old_children[x] if g.parent(c) == x)
        assert g.children(x)[:len(kept)] == kept


@SETTINGS
@given(tree_and_connected_set())
def test_split_and_glue_reproduces_the_tree(arg: tuple[GHD, frozenset[int]]) -> None:
    """Cut out a connected T', then re-attach every tree of T \\ T' at its original neighbour."""
    g, core_set = arg
    core_root = min(core_set)
    for renumber in (False, True):
        core = g.extract(core_set, core_root)
        if renumber:  # fresh preorder ids force id collisions with the outer trees
            core = GHD.from_spec(core.to_spec())
        assert len(core) == len(core_set)
        for comp in g.components_without(core_set):
            links = [(x, y) for x in comp for y in g.tree_neighbors(x) if y in core_set]
            assert len(links) == 1
            x, y = links[0]
            piece = g.extract(comp, x)
            before = len(piece)
            mapping = core.attach(core.by_label(g.node(y).label), piece, x)  # type: ignore[arg-type]
            assert set(mapping) == comp and len(piece) == before
            assert len(set(core.node_ids())) == len(core)
            for old, new in mapping.items():
                assert (core.node(new).bag, core.node(new).cover, core.node(new).label) == \
                    (g.node(old).bag, g.node(old).cover, g.node(old).label)
        assert len(core) == len(g)
        assert label_edges(core) == label_edges(g)
        if not renumber:
            assert id_edges(core) == id_edges(g)  # no collisions: ids are kept


@SETTINGS
@given(random_trees(), st.data())
def test_copy_is_independent(g: GHD, data: st.DataObject) -> None:
    before = g.to_spec()
    c = g.copy()
    assert c.to_spec() == before
    x = data.draw(st.sampled_from(g.node_ids()))
    c.set_labels(x, bag={"zz"}, cover={"w99"})
    c.add_node({"q"}, set(), parent=x, label="extra")
    c.reroot(data.draw(st.sampled_from(c.node_ids())))
    assert g.to_spec() == before
    assert "zz" not in g.node(x).bag and len(g) == len(c) - 1


@SETTINGS
@given(tree_and_connected_set())
def test_leaves_of_connected_set(arg: tuple[GHD, frozenset[int]]) -> None:
    g, s = arg
    assert g.is_connected(s)
    expected = sorted(x for x in s if degree_in(g, x, s) <= 1)
    assert g.leaves_of(s) == expected
    if len(s) >= 2:
        assert len(expected) >= 2
    assert g.bag_union(s) == frozenset().union(*(g.node(x).bag for x in s))


@SETTINGS
@given(tree_and_connected_set(), st.data())
def test_extract_matches_induced_edges(arg: tuple[GHD, frozenset[int]], data: st.DataObject) -> None:
    g, s = arg
    r = data.draw(st.sampled_from(sorted(s)))
    t = g.extract(s, r)
    assert t.root == r and set(t.node_ids()) == s
    assert id_edges(t) == frozenset(e for e in id_edges(g) if e <= s)
    assert all(t.node(x) == g.node(x) for x in s)


@SETTINGS
@given(random_trees())
def test_spec_round_trip(g: GHD) -> None:
    spec = g.to_spec()
    back = GHD.from_spec(spec)
    assert back.to_spec() == spec
    assert label_edges(back) == label_edges(g)
    assert back.node(back.root).label == g.node(g.root).label
    assert back.preorder() == list(range(len(g)))

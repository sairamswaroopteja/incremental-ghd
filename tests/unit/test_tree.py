"""S3 unit tests: the GHD tree on the paper fixtures, and structural error cases."""

from __future__ import annotations

import copy as pycopy

import pytest

from ighd.common.errors import InvalidGHDError
from ighd.ghd.tree import GHD, Node
from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, JOIN_TREE_HP_SPEC, S_SPEC

ALL_SPECS = {"G_PRIME_SPEC": G_PRIME_SPEC, "G2_SPEC": G2_SPEC,
             "JOIN_TREE_HP_SPEC": JOIN_TREE_HP_SPEC, "S_SPEC": S_SPEC}


def undirected_label_edges(g: GHD) -> frozenset[frozenset[str]]:
    """The unrooted tree as a set of {label, label} pairs."""
    out = set()
    for nid in g.node_ids():
        p = g.parent(nid)
        if p is not None:
            out.add(frozenset({g.node(p).label, g.node(nid).label}))
    return frozenset(out)  # type: ignore[arg-type]


def undirected_id_edges(g: GHD) -> frozenset[frozenset[int]]:
    return frozenset(frozenset({p, c}) for c in g.node_ids() if (p := g.parent(c)) is not None)


@pytest.fixture
def g2() -> GHD:
    return GHD.from_spec(G2_SPEC)  # type: ignore[arg-type]


def ids(g: GHD, *labels: str) -> list[int]:
    return [g.by_label(lbl) for lbl in labels]


# ----------------------------------------------------------------------- empty tree / basics
def test_empty_tree() -> None:
    g = GHD()
    assert len(g) == 0
    assert list(g) == []
    assert g.node_ids() == []
    assert g.width() == 0
    assert g.preorder() == [] and g.postorder() == []
    assert g.is_connected([]) is True
    assert g.leaves_of([]) == []
    assert g.bag_union([]) == frozenset()
    assert g.components_without([]) == []
    with pytest.raises(InvalidGHDError):
        _ = g.root
    with pytest.raises(InvalidGHDError):
        g.to_spec()


def test_add_node_basics() -> None:
    g = GHD()
    r = g.add_node("ab", ["w1"], label="r")
    a = g.add_node(["b", "c"], ("w2", "w3"), parent=r, label="a")
    b = g.add_node("bd", ["w4"], parent=r)
    c = g.add_node("cx", ["w2"], parent=a, label="c")
    assert (r, a, b, c) == (0, 1, 2, 3)
    assert g.root == r
    assert g.node(a) == Node(1, frozenset("bc"), frozenset({"w2", "w3"}), "a")
    assert isinstance(g.node(a).bag, frozenset) and isinstance(g.node(a).cover, frozenset)
    assert g.node(b).label is None
    assert g.children(r) == (a, b)
    assert g.parent(r) is None and g.parent(c) == a
    assert g.tree_neighbors(a) == (r, c)
    assert g.tree_neighbors(r) == (a, b)
    assert [n.id for n in g] == [0, 1, 2, 3]
    assert len(g) == 4
    assert g.width() == 2
    assert g.by_label("c") == c


def test_single_node_tree() -> None:
    g = GHD()
    r = g.add_node("a", ["w1"])
    assert g.preorder() == [r] == g.postorder()
    assert g.leaves_of([r]) == [r]
    assert g.components_without([r]) == []
    assert g.components_without([]) == [frozenset({r})]
    assert g.ancestors(r) == []
    assert g.subtree_nodes(r) == frozenset({r})
    g.reroot(r)
    assert g.root == r
    assert g.to_spec() == {"root": "#0", "nodes": {"#0": (("a",), ("w1",))}, "children": {"#0": []}}


# ------------------------------------------------------------------------ G2 (Fig. 6(a))
def test_g2_preorder_ids(g2: GHD) -> None:
    assert ids(g2, "u1", "u2", "u4", "u3") == [0, 1, 2, 3]
    assert g2.root == 0
    assert g2.children(0) == (1, 3)
    assert g2.children(1) == (2,)
    assert g2.node(0).bag == frozenset("abceh")
    assert g2.node(1).cover == frozenset({"w3", "w7"})


def test_g2_queries(g2: GHD) -> None:
    u1, u2, u4, u3 = ids(g2, "u1", "u2", "u4", "u3")
    assert g2.components_without({u1, u2}) == [frozenset({u4}), frozenset({u3})]
    assert g2.leaves_of(g2.node_ids()) == sorted([u3, u4])
    assert g2.bag_union({u1, u2}) == frozenset("abcehik")
    assert g2.width() == 2
    assert g2.subtree_nodes(u2) == frozenset({u2, u4})
    assert g2.subtree_nodes(u1) == frozenset(g2.node_ids())
    assert g2.ancestors(u4) == [u2, u1]
    assert g2.is_connected({u3, u4}) is False
    assert g2.is_connected({u1, u2, u4}) is True
    assert g2.is_connected({u4}) is True
    assert g2.preorder() == [u1, u2, u4, u3]
    assert g2.postorder() == [u4, u2, u3, u1]
    assert g2.preorder(u2) == [u2, u4]
    assert g2.postorder(u2) == [u4, u2]


def test_alg2_working_tree_leaves(g2: GHD) -> None:
    """Example 4.3: Algorithm 2 shrinks the working tree; u1 becomes a leaf once u3 is gone."""
    u1, u2, u3, u4 = ids(g2, "u1", "u2", "u3", "u4")
    assert g2.leaves_of({u1, u2, u3, u4}) == sorted([u3, u4])
    assert g2.leaves_of({u1, u2, u4}) == sorted([u1, u4])
    assert g2.leaves_of({u1, u2}) == sorted([u1, u2])
    assert g2.leaves_of({u2}) == [u2]


def test_g2_tree_neighbors(g2: GHD) -> None:
    u1, u2, u3, u4 = ids(g2, "u1", "u2", "u3", "u4")
    assert g2.tree_neighbors(u1) == (u2, u3)
    assert g2.tree_neighbors(u2) == (u1, u4)
    assert g2.tree_neighbors(u3) == (u1,)


# ------------------------------------------------------------------------ spec round trip
@pytest.mark.parametrize("name", sorted(ALL_SPECS))
def test_spec_round_trip(name: str) -> None:
    spec = ALL_SPECS[name]
    g = GHD.from_spec(spec)  # type: ignore[arg-type]
    assert len(g) == len(spec["nodes"])
    for lbl, (bag, cover) in spec["nodes"].items():
        n = g.node(g.by_label(lbl))
        assert n.bag == frozenset(bag) and n.cover == frozenset(cover)
    out = g.to_spec()
    assert out["root"] == spec["root"]
    assert {k: list(v) for k, v in out["children"].items()} == \
        {lbl: list(spec["children"].get(lbl, [])) for lbl in spec["nodes"]}
    g_back = GHD.from_spec(out)
    assert g_back.to_spec() == out
    assert [(n.id, n.bag, n.cover, n.label) for n in g_back] == [(n.id, n.bag, n.cover, n.label) for n in g]
    assert [g_back.children(i) for i in g_back.node_ids()] == [g.children(i) for i in g.node_ids()]


def test_to_spec_unlabelled_nodes_and_round_trip() -> None:
    g = GHD()
    r = g.add_node("ab", ["w1"])
    g.add_node("b", ["w2"], parent=r, label="x")
    g.add_node("a", [], parent=r)
    spec = g.to_spec()
    assert spec == {"root": "#0", "nodes": {"#0": (("a", "b"), ("w1",)), "x": (("b",), ("w2",)), "#2": (("a",), ())},
                    "children": {"#0": ["x", "#2"], "x": [], "#2": []}}
    assert GHD.from_spec(spec).to_spec() == spec


def test_to_spec_generated_label_collision() -> None:
    g = GHD()
    r = g.add_node("a", [], label="#1")
    g.add_node("b", [], parent=r)  # id 1, generated label "#1"
    with pytest.raises(InvalidGHDError, match="#1"):
        g.to_spec()


def test_from_spec_leaf_children_entry_optional() -> None:
    g = GHD.from_spec({"root": "a", "nodes": {"a": ("x", ["e"]), "b": ("y", ["f"])},  # type: ignore[typeddict-item]
                       "children": {"a": ["b"]}})
    assert g.children(g.by_label("a")) == (g.by_label("b"),)


def test_from_spec_does_not_mutate_spec() -> None:
    spec = pycopy.deepcopy(G2_SPEC)
    GHD.from_spec(spec)  # type: ignore[arg-type]
    assert spec == G2_SPEC


# ------------------------------------------------------------------------ reroot
@pytest.mark.parametrize("name", sorted(ALL_SPECS))
def test_reroot_every_node(name: str) -> None:
    base = GHD.from_spec(ALL_SPECS[name])  # type: ignore[arg-type]
    edges = undirected_id_edges(base)
    for target in base.node_ids():
        g = base.copy()
        g.reroot(target)
        assert g.root == target and g.parent(target) is None
        assert undirected_id_edges(g) == edges
        assert sorted(g.preorder()) == g.node_ids()
        assert g.ancestors(target) == []


def test_reroot_to_root_is_noop(g2: GHD) -> None:
    before = g2.to_spec()
    g2.reroot(g2.root)
    assert g2.to_spec() == before


def test_reroot_children_order(g2: GHD) -> None:
    u1, u2, u3, u4 = ids(g2, "u1", "u2", "u3", "u4")
    g2.reroot(u4)
    assert g2.root == u4
    assert g2.children(u4) == (u2,)
    assert g2.children(u2) == (u1,)          # former parent appended at the end
    assert g2.children(u1) == (u3,)          # u2 removed, order of the rest kept
    assert g2.ancestors(u3) == [u1, u2, u4]
    g2.reroot(u1)
    assert g2.children(u1) == (u3, u2)
    assert g2.children(u2) == (u4,)


# ------------------------------------------------------------------------ copy / set_labels
def test_copy_independent(g2: GHD) -> None:
    c = g2.copy()
    u1 = g2.by_label("u1")
    c.set_labels(u1, bag="xyz", cover=["w9"])
    c.add_node("q", [], parent=u1, label="new")
    c.reroot(g2.by_label("u4"))
    assert g2.node(u1).bag == frozenset("abceh") and g2.node(u1).cover == frozenset({"w1", "w5"})
    assert c.node(u1).bag == frozenset("xyz") and c.node(u1).label == "u1"
    assert len(g2) == 4 and g2.root == u1
    with pytest.raises(InvalidGHDError):
        g2.by_label("new")


def test_set_labels_partial(g2: GHD) -> None:
    u2 = g2.by_label("u2")
    g2.set_labels(u2, bag=["c", "e"])
    assert g2.node(u2) == Node(u2, frozenset("ce"), frozenset({"w3", "w7"}), "u2")
    g2.set_labels(u2, cover=[])
    assert g2.node(u2).cover == frozenset()
    with pytest.raises(InvalidGHDError, match="99"):
        g2.set_labels(99, bag="a")


# ------------------------------------------------------------------------ extract / attach
def test_example_4_3_split_and_glue(g2: GHD) -> None:
    """Theorem 4.5 gluing on Example 4.3: T* = {u1, u2} is replaced by the new D* (n1 - n2),
    and the outer trees {u3}, {u4} are re-attached to the nodes that satisfy their bag constraints."""
    u1, u2, u3, u4 = ids(g2, "u1", "u2", "u3", "u4")
    outer = g2.components_without({u1, u2})
    assert outer == [frozenset({u4}), frozenset({u3})]
    t_u4 = g2.extract(outer[0], u4)
    t_u3 = g2.extract(outer[1], u3)
    assert len(t_u4) == 1 and t_u4.root == u4 and t_u4.node(u4) == g2.node(u4)

    d = GHD()
    n1 = d.add_node("abceh", ["w1", "w5"], label="n1")
    n2 = d.add_node("eik", ["w3"], parent=n1, label="n2")
    m3 = d.attach(n1, t_u3, u3)
    m4 = d.attach(n2, t_u4, u4)
    assert m3 == {u3: u3} and m4 == {u4: u4}  # ids 3 and 2 are free in d
    assert undirected_label_edges(d) == {frozenset({"n1", "n2"}), frozenset({"n2", "u4"}),
                                         frozenset({"n1", "u3"})}
    assert d.children(n1) == (n2, m3[u3]) and d.children(n2) == (m4[u4],)
    for lbl in ("u3", "u4"):
        assert d.node(d.by_label(lbl)) == g2.node(g2.by_label(lbl))
    # the inputs are untouched
    assert len(t_u3) == 1 and len(t_u4) == 1 and len(g2) == 4


def test_extract_connected_part(g2: GHD) -> None:
    u1, u2, u3, u4 = ids(g2, "u1", "u2", "u3", "u4")
    t = g2.extract({u1, u2, u4}, u4)
    assert t.node_ids() == sorted([u1, u2, u4])
    assert t.root == u4
    assert undirected_id_edges(t) == {frozenset({u1, u2}), frozenset({u2, u4})}
    assert all(t.node(i) == g2.node(i) for i in t.node_ids())
    assert t.by_label("u1") == u1
    with pytest.raises(InvalidGHDError):
        t.by_label("u3")
    # a fresh add_node in the extract does not clash with kept ids
    assert t.add_node("z", [], parent=u1) == max(t.node_ids())
    assert len(set(t.node_ids())) == 4


def test_extract_errors(g2: GHD) -> None:
    u1, u2, u3, u4 = ids(g2, "u1", "u2", "u3", "u4")
    with pytest.raises(InvalidGHDError, match="not connected"):
        g2.extract({u3, u4}, u3)
    with pytest.raises(InvalidGHDError, match="root"):
        g2.extract({u1, u2}, u3)
    with pytest.raises(InvalidGHDError):
        g2.extract({u1, 42}, u1)


def test_attach_reroots_and_reassigns_colliding_ids(g2: GHD) -> None:
    d = GHD()
    a = d.add_node("p", [], label="a")       # id 0 collides with u1
    b = d.add_node("q", [], parent=a, label="b")  # id 1 collides with u2
    m = d.attach(b, g2, g2.by_label("u4"))
    assert set(m) == set(g2.node_ids())
    # rerooted preorder of g2 is u4(2), u2(1), u1(0), u3(3); ids 0 and 1 are taken in d
    assert m[g2.by_label("u4")] == 2 and m[g2.by_label("u3")] == 3   # free ids kept
    assert m[g2.by_label("u2")] == 4 and m[g2.by_label("u1")] == 5   # fresh: max(all ids) + 1, ...
    assert len(set(m.values())) == 4 and not set(m.values()) & {a, b}
    assert d.children(b) == (m[g2.by_label("u4")],)
    assert undirected_label_edges(d) == undirected_label_edges(g2) | {frozenset({"a", "b"}), frozenset({"b", "u4"})}
    for lbl in ("u1", "u2", "u3", "u4"):
        old, new = g2.node(g2.by_label(lbl)), d.node(d.by_label(lbl))
        assert (old.bag, old.cover) == (new.bag, new.cover) and new.id == m[old.id]
    # g2 itself was neither rerooted nor modified
    assert g2.root == g2.by_label("u1") and g2.preorder() == [0, 1, 2, 3]
    # later add_node allocates past every id
    assert d.add_node("r", [], parent=a) == 6


def test_attach_label_collision_leaves_self_unchanged(g2: GHD) -> None:
    d = GHD()
    n1 = d.add_node("x", [], label="n1")
    d.add_node("y", [], parent=n1, label="u3")
    before = (d.to_spec(), d.node_ids())
    with pytest.raises(InvalidGHDError, match="u3"):
        d.attach(n1, g2, g2.by_label("u1"))
    assert (d.to_spec(), d.node_ids()) == before


def test_attach_unknown_nodes(g2: GHD) -> None:
    d = GHD()
    d.add_node("x", [])
    with pytest.raises(InvalidGHDError, match="7"):
        d.attach(7, g2, 0)
    with pytest.raises(InvalidGHDError, match="9"):
        d.attach(0, g2, 9)
    assert len(d) == 1


# ------------------------------------------------------------------------ error cases
def test_add_node_errors() -> None:
    g = GHD()
    r = g.add_node("a", [], label="r")
    with pytest.raises(InvalidGHDError, match="root"):
        g.add_node("b", [], label="second_root")
    with pytest.raises(InvalidGHDError, match="5"):
        g.add_node("b", [], parent=5, label="orphan")
    with pytest.raises(InvalidGHDError, match="'r'"):
        g.add_node("b", [], parent=r, label="r")
    assert len(g) == 1  # failed calls change nothing


def test_unknown_ids_and_labels(g2: GHD) -> None:
    for call in (lambda: g2.node(17), lambda: g2.parent(17), lambda: g2.children(17),
                 lambda: g2.tree_neighbors(17), lambda: g2.preorder(17), lambda: g2.postorder(17),
                 lambda: g2.subtree_nodes(17), lambda: g2.ancestors(17), lambda: g2.reroot(17),
                 lambda: g2.is_connected([0, 17]), lambda: g2.leaves_of([17]),
                 lambda: g2.bag_union([17]), lambda: g2.components_without([17])):
        with pytest.raises(InvalidGHDError, match="17"):
            call()
    with pytest.raises(InvalidGHDError, match="nope"):
        g2.by_label("nope")


def _spec(children: dict, root: str = "a", labels: str = "abcd") -> dict:
    return {"root": root, "nodes": {lbl: (lbl, ["w"]) for lbl in labels}, "children": children}


@pytest.mark.parametrize("spec,match", [
    (_spec({"a": ["b", "c", "d"]}, root="z"), "root"),
    (_spec({"a": ["b", "c"], "b": ["d"], "c": ["d"]}), "two parents"),
    (_spec({"a": ["b", "b", "c", "d"]}), "two parents"),
    (_spec({"a": ["b"], "b": ["c"], "c": ["a"], "d": []}), "cycle"),
    (_spec({"a": ["b"], "c": ["d"], "d": ["c"]}), "cycle"),
    (_spec({"a": ["b", "c"]}), "not reachable"),
    (_spec({"a": ["b", "c", "x"]}), "'x'"),
    (_spec({"a": ["b", "c", "d"], "q": []}), "'q'"),
    (_spec({"a": "bcd"}), "sequence"),
], ids=["unknown-root", "two-parents", "listed-twice", "cycle-through-root", "cycle-detached",
        "unreachable", "unknown-child", "unknown-parent-entry", "string-children"])
def test_from_spec_errors(spec: dict, match: str) -> None:
    with pytest.raises(InvalidGHDError, match=match):
        GHD.from_spec(spec)  # type: ignore[arg-type]


def test_from_spec_bad_node_entry() -> None:
    with pytest.raises(InvalidGHDError, match="'a'"):
        GHD.from_spec({"root": "a", "nodes": {"a": ("x",)}, "children": {}})  # type: ignore[typeddict-item]


def test_deep_path_no_recursion_limit() -> None:
    g = GHD()
    prev = g.add_node("v0", ["e"])
    for i in range(1, 5000):
        prev = g.add_node([f"v{i}"], ["e"], parent=prev)
    assert len(g.preorder()) == 5000 and len(g.postorder()) == 5000
    assert len(g.ancestors(prev)) == 4999
    g.reroot(prev)
    assert g.preorder()[-1] == 0
    assert len(g.extract(g.node_ids(), 2500)) == 5000
    assert GHD.from_spec(g.to_spec()).width() == 1

"""S11: paper Example 5.2 run through Algorithms 3 and 4 (scene creation).

Input: H_P2 (Fig. 5(a)) with the GHD G2 of Fig. 6(a); delta = DelConstr(w7) (giving H_P');
T* = {u1, u2} from Algorithm 2 (Example 4.3).

Pinned readings (FAITHFULNESS_LEDGER): L-A16 (Alg 3 line 3 applied), L-A17 (up-scene key =
coveredEdges), L-A20 (delta applied to bags and covers), L-A25 (kind by Alg 3 line 9).
"""

from __future__ import annotations

import pytest

from ighd.common.config import Semantics, UpSceneKey
from ighd.ghd import GHD, UnguardedVertices, validate
from ighd.hypergraph.core import Hypergraph
from ighd.modifications import DelConstr, ModificationResult
from ighd.mutable import minimal_mutable_subtree
from ighd.scenes import SceneKind, SceneMapping, scene_create
from ighd.static import connection
from tests.fixtures.expected import ALL_HPP_EDGES, EX52_SIGMA_AS_STATED, EX52_SIGMA_PSEUDOCODE
from tests.fixtures.paper import G2_SPEC, H_P2

fs = frozenset


def _setup() -> tuple[ModificationResult, GHD, frozenset[int]]:
    change = DelConstr("w7").apply(Hypergraph(H_P2))
    g = GHD.from_spec(G2_SPEC)
    t_star = minimal_mutable_subtree(change, g).t_star
    assert t_star == fs({g.by_label("u1"), g.by_label("u2")})
    return change, g, t_star


def _as_labels(g: GHD, sigma: SceneMapping) -> dict[frozenset[str], tuple[str, str]]:
    out: dict[frozenset[str], tuple[str, str]] = {}
    for key, entry in sigma.items():
        label = g.node(entry.node).label
        assert label is not None
        out[key] = (label, entry.kind.value)
    return out


def test_ex52_defaults_give_pseudocode_sigma() -> None:
    change, g, t_star = _setup()
    sigma, events = scene_create(change, g, t_star)
    assert _as_labels(g, sigma) == EX52_SIGMA_PSEUDOCODE
    assert sigma.overwritten == []
    origins = {key: e.origin for key, e in sigma.items()}
    assert origins == {ALL_HPP_EDGES: "down", fs({"w2", "w4"}): "down", fs({"w6"}): "up"}


def test_ex52_line3_fires_at_u2_naming_c() -> None:
    change, g, t_star = _setup()
    _, events = scene_create(change, g, t_star)
    u2, u4 = g.by_label("u2"), g.by_label("u4")
    l3 = [e for e in events if e.line == "A3:L3"]
    assert len(l3) == 1
    assert l3[0].node == u2 and l3[0].edges == fs({"w3", "w6"})
    assert "uncovered vertices {c}" in l3[0].detail
    # u2's bag {c,e,i,k} is now guarded only by its renamed cover {w3} = {e,i,k}
    assert change.new.covered_vertices(fs({"w3"})) == fs("eik")
    # the scene for u4 is recorded by Algorithm 4 (line 16), with key coveredEdges = {w6}
    up = [e for e in events if e.line == "A4:L16"]
    assert [(e.node, e.edges) for e in up] == [(u4, fs({"w6"}))]
    # the full decision trace, in order
    trace = [(e.line, g.node(e.node).label, e.edges) for e in events]
    assert trace == [
        ("A3:L10", "u1", ALL_HPP_EDGES),
        ("A3:L16", "u2", fs({"w3", "w6"})),
        ("A3:L3", "u2", fs({"w3", "w6"})),
        ("A4:L16", "u4", fs({"w6"})),
        ("A3:L16", "u3", fs({"w2", "w4"})),
        ("A3:L12", "u3", fs({"w2", "w4"})),
    ]


@pytest.mark.paper_discrepancy
def test_ex52_without_line3_reproduces_stated_sigma_which_is_unsafe() -> None:
    """A16: skipping Alg 3 line 3 gives exactly the mapping printed in Example 5.2, including
    C2 = {w3, w6} -> u2. Reusing u2 for C2 is unsafe: after deleting w7, u2's delta-bag
    {c,e,i,k} is not covered by its delta-cover {w3} (= {e,i,k}), so the GHD condition (3)
    fails."""
    change, g, t_star = _setup()
    sigma, events = scene_create(change, g, t_star, Semantics(scene_guard_check=False))
    assert _as_labels(g, sigma) == EX52_SIGMA_AS_STATED
    assert not [e for e in events if e.line == "A3:L3"]
    u2 = g.by_label("u2")
    entry = sigma.peek(fs({"w3", "w6"}))
    assert entry is not None and entry.node == u2 and entry.kind is SceneKind.IN

    # the consequence: delta(B_u2) is not inside B(delta(lambda_u2))
    d_bag = g.node(u2).bag & change.new.vertices
    d_cover = fs(t for e in g.node(u2).cover if (t := change.s_delta[e]) is not None)
    assert d_bag == fs("ceik") and d_cover == fs({"w3"})
    assert change.new.covered_vertices(d_cover) == fs("eik")
    assert not d_bag <= change.new.covered_vertices(d_cover)

    # reusing every node of the stated sigma with its delta-labels is rejected by the validator
    reused = GHD.from_spec({
        "root": "u1",
        "nodes": {lbl: (g.node(g.by_label(lbl)).bag & change.new.vertices,
                        tuple(t for e in g.node(g.by_label(lbl)).cover
                              if (t := change.s_delta[e]) is not None))
                  for lbl in ("u1", "u2", "u3", "u4")},
        "children": {"u1": ["u2", "u3"], "u2": ["u4"], "u3": [], "u4": []},
    })
    report = validate(change.new, reused)
    assert not report.ok
    assert [v for v in report.violations if isinstance(v, UnguardedVertices)] == [
        UnguardedVertices(reused.by_label("u2"), fs("c"))]


@pytest.mark.paper_discrepancy
@pytest.mark.parametrize("key_mode", [UpSceneKey.LITERAL_H_PRIME, UpSceneKey.INTERSECTING_EDGES])
def test_ex52_alternative_up_scene_keys(key_mode: UpSceneKey) -> None:
    """A17. Algorithm 4 is entered at u2 with H' = C2 = {w3, w6} (after line 3 fails).

    * COVERED_EDGES (default) keys u4's scene by the edges of H' contained in a bag of T_u4:
      only w6 = {j,k,l} lies inside B_u4 = {j,k,l}; w3 = {e,i,k} does not. Key {w6}.
    * LITERAL_H_PRIME uses H' itself: {w3, w6}.
    * INTERSECTING_EDGES uses the edges of H' meeting V(T_u4) = {j,k,l}: w6, and w3 via k.
    Both alternatives therefore map {w3, w6} -> u4 (OUT, origin 'up').
    """
    change, g, t_star = _setup()
    sigma, _ = scene_create(change, g, t_star, Semantics(up_scene_key=key_mode))
    u4 = g.by_label("u4")
    assert _as_labels(g, sigma) == {
        ALL_HPP_EDGES: ("u1", "in"),
        fs({"w2", "w4"}): ("u3", "out"),
        fs({"w3", "w6"}): ("u4", "out"),
    }
    entry = sigma.peek(fs({"w3", "w6"}))
    assert entry is not None and (entry.node, entry.kind, entry.origin) == (u4, SceneKind.OUT, "up")
    assert sigma.peek(fs({"w6"})) is None

    # Why the key {w3, w6} is harmful: DecompUpdate would look up the component C2 = {w3, w6}
    # of u1's bag and root it at u4, whose bag {j,k,l} misses the connection vertex e.
    parent_bag = g.node(g.by_label("u1")).bag & change.new.vertices
    assert parent_bag == fs("abceh")
    conn = connection(change.new, fs({"w3", "w6"}), parent_bag)
    assert conn == fs("e")
    assert not conn <= g.node(u4).bag

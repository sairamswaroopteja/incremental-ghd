"""Paper Example 2.3 (p. 5-6, Fig. 3/4), replayed compositionally with the S7 decomposer.

The paper builds the GHD of Fig. 3 top-down: the root separator {c,e,h,i,k} (cover {w5,w3})
splits H_P' into C1 = {w1,w2,w4} and C2 = {w6}; C1 is decomposed below the root with connection
{c,h} into {a,b,c,f,g,h}/{w1,w2} with child {a,d,f}/{w4}, and C2 with connection {k} into the
single node {j,k,l}/{w6}. We reproduce every intermediate step and the assembled tree.
"""

from __future__ import annotations

from typing import Any

from ighd.common import DecomposerMode, SearchStatus
from ighd.ghd.normal_form import check_normal_form
from ighd.ghd.tree import GHD
from ighd.ghd.validation import validate
from ighd.hypergraph.core import Hypergraph
from ighd.static.decomposer import DecompositionTask, TopDownDecomposer
from ighd.static.separation import components, connection
from tests.fixtures.paper import G_PRIME_SPEC, H_PP

fs = frozenset
HPP = Hypergraph(H_PP)
ROOT_BAG = fs("cehik")
C1 = fs({"w1", "w2", "w4"})
C2 = fs({"w6"})
EXACT = TopDownDecomposer(DecomposerMode.EXACT)


def shape(g: GHD, node: int | None = None) -> tuple[Any, ...]:
    """Label-free structure: (bag, cover, children shapes in order)."""
    n = g.root if node is None else node
    return (g.node(n).bag, g.node(n).cover, tuple(shape(g, c) for c in g.children(n)))


def test_a_root_separator_components() -> None:
    assert components(HPP, HPP.edge_names, ROOT_BAG) == [C1, C2]
    assert connection(HPP, C1, ROOT_BAG) == fs("ch")
    assert connection(HPP, C2, ROOT_BAG) == fs("k")


def fragment_c1() -> tuple[GHD, int]:
    r = EXACT.decompose(DecompositionTask(HPP, 2, edges=C1, conn=fs("ch")))
    assert r.status is SearchStatus.FOUND and r.ghd is not None and r.root is not None
    return r.ghd, r.root


def fragment_c2() -> tuple[GHD, int]:
    r = EXACT.decompose(DecompositionTask(HPP, 2, edges=C2, conn=fs("k")))
    assert r.status is SearchStatus.FOUND and r.ghd is not None and r.root is not None
    return r.ghd, r.root


def test_b_component_c1() -> None:
    g, root = fragment_c1()
    assert shape(g, root) == (fs("abcfgh"), fs({"w1", "w2"}), ((fs("adf"), fs({"w4"}), ()),))


def test_c_component_c2() -> None:
    g, root = fragment_c2()
    assert shape(g, root) == (fs("jkl"), fs({"w6"}), ())


def test_d_assembled_tree_is_fig3() -> None:
    g = GHD()
    root = g.add_node(ROOT_BAG, {"w5", "w3"})
    for frag, frag_root in (fragment_c1(), fragment_c2()):  # C1 then C2, as in Example 2.3
        g.attach(root, frag, frag_root)
    expected = GHD.from_spec(G_PRIME_SPEC)  # type: ignore[arg-type]
    assert shape(g) == shape(expected)
    report = validate(HPP, g)
    assert report.ok, report.violations
    assert report.width == 2
    assert check_normal_form(HPP, g).ok


def test_forcing_root_separator_via_scene_hint_reproduces_fig3() -> None:
    """IMPLEMENTATION_PLAN S7 unit test: forcing the root separator {w5,w3} gives Fig. 3 exactly."""

    class Forced(TopDownDecomposer):
        def _scene_candidates(self, c_key, conn, scenes):  # type: ignore[no-untyped-def]
            return [(ROOT_BAG, fs({"w5", "w3"}))] if c_key == HPP.edge_names else []

    r = Forced(DecomposerMode.EXACT).decompose(DecompositionTask(HPP, 2))
    assert r.status is SearchStatus.FOUND and r.ghd is not None
    assert shape(r.ghd) == shape(GHD.from_spec(G_PRIME_SPEC))  # type: ignore[arg-type]
    assert r.stats.scene_hits == 1

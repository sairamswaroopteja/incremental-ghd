"""S15: the frozen public entry point ``decomp_update`` (ARCHITECTURE: update.decomp_update) and the
debugging reprs were never executed by the suite (function-level execution scan in S15). The
pipeline calls ``run_decomp_update``; these tests pin that the public wrapper gives the same
answer and a valid GHD, and that a failure returns no GHD (never a partial one).
"""

from __future__ import annotations

from ighd.common import DecomposerMode, SearchStatus
from ighd.common.config import PAPER_DEFAULT
from ighd.ghd import GHD, check_normal_form, validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, DelConstr
from ighd.mutable.minimal import minimal_mutable_subtree
from ighd.oracle import exact_ghw
from ighd.scenes.scene_down import scene_create
from ighd.static import TopDownDecomposer
from ighd.update.decomp_update import decomp_update, fragment_to_ghd, run_decomp_update
from tests.fixtures.paper import G2_SPEC, H_P2


def _setup(h: Hypergraph, g: GHD, mod):
    change = mod.apply(h)
    t_star = minimal_mutable_subtree(change, g).t_star
    return change, t_star


def _sigma(change, g, t_star):
    return scene_create(change, g, t_star)[0]       # fresh: lookups consume in-scenes


def test_public_decomp_update_matches_pipeline_entry_on_example_52() -> None:
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    change, t_star = _setup(h, g, DelConstr("w7"))
    k = g.width()
    dec = TopDownDecomposer(DecomposerMode.EXACT)
    res = decomp_update(change, g, change.new.edge_names, frozenset(), k,
                        _sigma(change, g, t_star), dec)
    status, frag, _, _ = run_decomp_update(change, g, k, _sigma(change, g, t_star), dec, None,
                                           PAPER_DEFAULT)
    assert res.status is status is SearchStatus.FOUND
    assert res.root == res.ghd.root
    rep = validate(change.new, res.ghd)
    assert rep.ok and rep.width <= k, rep.violations
    assert check_normal_form(change.new, res.ghd).ok
    same, _, _ = fragment_to_ghd(frag)
    assert res.ghd.to_spec() == same.to_spec()       # identical assembly
    # u1 and u3 are reused with their old bags (paper Ex. 5.2; u2 rejected by Alg 3 L3, L-A16)
    for lab in ("u1", "u3"):
        assert res.ghd.node(res.ghd.by_label(lab)).bag == g.node(g.by_label(lab)).bag


def test_public_decomp_update_failure_returns_no_ghd() -> None:
    """L-A21 case: AddConstr {d,e,f} raises ghw from 1 to 2, so at k = 1 nothing exists."""
    h = Hypergraph({"w0": "ce", "w1": "df", "w2": "cf"})
    g = GHD.from_spec({"root": "n0", "nodes": {"n0": ("ce", ("w0",)), "n1": ("cf", ("w2",)),
                                               "n2": ("df", ("w1",))},
                       "children": {"n0": ["n1"], "n1": ["n2"]}})
    change, t_star = _setup(h, g, AddConstr("wnew", frozenset("def")))
    assert exact_ghw(change.new)[0] == 2
    res = decomp_update(change, g, change.new.edge_names, frozenset(), 1,
                        _sigma(change, g, t_star), TopDownDecomposer(DecomposerMode.EXACT))
    assert res.status is SearchStatus.PROVEN_NO      # EXACT decomposer, A18 fallback on the top state
    assert res.ghd is None and res.root is None


def test_reprs_are_informative() -> None:
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    assert "u1" in repr(g) and repr(GHD()) == "GHD(<empty>)"
    change, t_star = _setup(h, g, DelConstr("w7"))
    text = repr(_sigma(change, g, t_star))
    assert "->" in text and ("in" in text or "out" in text)

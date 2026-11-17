"""S9: paper Example 4.3 run through Algorithm 2 (minimal delta-mutable subtree).

Input: H_P2 (Fig. 5(a)), delta = DelConstr(w7) (giving H_P'), GHD G2 of Fig. 6(a).
Paper: T* = {u1, u2}. The step log follows node-id order (u1=0, u2=1, u4=2, u3=3; ids from
GHD.from_spec preorder), so u4 is removed before u3 (PROGRESS "Findings carried forward"; the
study guide's table removes u3 first and is not a valid expected log here).
"""

from __future__ import annotations

from ighd.common.config import PAPER_DEFAULT, InducedComparison, Semantics
from ighd.ghd.tree import GHD
from ighd.hypergraph.core import Hypergraph
from ighd.modifications import DelConstr, ModificationResult
from ighd.mutable import minimal_mutable_subtree, mutable_conditions
from tests.fixtures.paper import G2_SPEC, H_P2

fs = frozenset

EXPECTED_LOG = [
    # (round, leaf, sorted outside labels, outside vertices, induced_equal, accepted)
    (1, "u4", ["u4"], "jkl", True, True),
    (2, "u2", ["u2", "u4"], "ceijkl", False, False),
    (2, "u3", ["u3", "u4"], "adfghjkl", True, True),
    (3, "u1", ["u1", "u3", "u4"], "abcdefghjkl", False, False),
    (3, "u2", ["u2", "u3", "u4"], "acdefghijkl", False, False),
]


def _setup() -> tuple[ModificationResult, GHD]:
    return DelConstr("w7").apply(Hypergraph(H_P2)), GHD.from_spec(G2_SPEC)


def _label(g: GHD, u: int) -> str:
    lbl = g.node(u).label
    assert lbl is not None
    return lbl


def test_node_ids_are_preorder() -> None:
    _, g = _setup()
    assert [g.by_label(x) for x in ("u1", "u2", "u4", "u3")] == [0, 1, 2, 3]


def test_ex43_t_star() -> None:
    ch, g = _setup()
    res = minimal_mutable_subtree(ch, g)
    assert res.t_star == fs({g.by_label("u1"), g.by_label("u2")})


def test_ex43_exact_step_log() -> None:
    ch, g = _setup()
    res = minimal_mutable_subtree(ch, g)
    log = [
        (s.round, _label(g, s.leaf), sorted(_label(g, x) for x in s.outside),
         "".join(sorted(s.outside_vertices)), s.induced_equal, s.accepted)
        for s in res.steps
    ]
    assert log == EXPECTED_LOG
    # DelConstr creates no vertex, so condition (ii) never blocks a removal here.
    assert all(not s.adjacent_new for s in res.steps)


def test_ex43_round2_u2_diff_names_w7() -> None:
    """Rejecting u2 in round 2: with X = B({u2, u4}) = {c,e,i,j,k,l}, w7 restricted to X is
    {c, i} in H_P2 but w7 is deleted in delta(H) (EDGEWISE: counts as empty)."""
    ch, g = _setup()
    outside = {g.by_label("u2"), g.by_label("u4")}
    t_prime = fs(g.node_ids()) - outside
    check = mutable_conditions(ch, g, t_prime, PAPER_DEFAULT)
    assert not check.condition_i
    assert check.diff.changed == (("w7", fs("ci"), fs()),)


def test_ex43_set_semantics_same_result() -> None:
    """A2 (b): the paper example gives the same T* and log under SET semantics."""
    ch, g = _setup()
    edgewise = minimal_mutable_subtree(ch, g)
    set_mode = minimal_mutable_subtree(ch, g, Semantics(induced_comparison=InducedComparison.SET))
    assert set_mode.t_star == edgewise.t_star
    assert [(s.round, s.leaf, s.accepted) for s in set_mode.steps] == \
        [(s.round, s.leaf, s.accepted) for s in edgewise.steps]

"""Algorithm 2: the minimal delta-mutable subtree, with a step log (stage S9; Lemma 4.4).

Leaves are tried in increasing node-id order (the paper leaves the order open; under EDGEWISE
semantics the result is order-independent by Lemma 4.4). After each accepted removal the scan
restarts (Alg 2 line 12). A single remaining node is treated as a leaf, so T* may become empty
(A12) when delta is invisible from every bag.
"""

from __future__ import annotations

from dataclasses import dataclass

from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.types import NodeId, VertexSet
from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult
from ighd.mutable.conditions import mutable_conditions


@dataclass(frozen=True)
class Alg2Step:
    """One tested leaf (one evaluation of Alg 2 lines 6-10)."""

    round: int
    leaf: NodeId
    outside: frozenset[NodeId]
    """T \\ T'_{-u}."""
    outside_vertices: VertexSet
    """B(T \\ T'_{-u})."""
    induced_equal: bool
    adjacent_new: VertexSet
    accepted: bool


@dataclass(frozen=True)
class MutableResult:
    t_star: frozenset[NodeId]
    steps: tuple[Alg2Step, ...]


def minimal_mutable_subtree(change: ModificationResult, ghd: GHD,
                            semantics: Semantics = PAPER_DEFAULT) -> MutableResult:
    """Algorithm 2 on a GHD of change.old; returns T* and one Alg2Step per tested leaf.

    ("minus" is set difference; T minus T'_{-u} is the forest of nodes outside T'_{-u}, D17.)
    Line 2: T' := T.  Line 3: V_new := V(delta(H)) minus V(H) (``change.new_vertices``).
    Lines 4-13: repeat a round; in each round, for every leaf u of T' (``ghd.leaves_of``,
    increasing id order, line 5), let T'_{-u} := T' minus {u} (line 6) and test lines 7-10, i.e.
    A = H[T minus T'_{-u}] equals B = delta(H)[T minus T'_{-u}] and V_new & Adj = {}, where Adj
    is the set of vertices adjacent in delta(H) to B(T minus T'_{-u}) (line 9). The test is delegated to
    ``mutable_conditions(change, ghd, T'_{-u})``, so Def 4.1 and Alg 2 share one implementation
    (T'_{-u} is always connected, as u is a leaf of the connected T'). On success T' := T'_{-u}
    (line 11) and the scan restarts in a new round (line 12, break). The loop ends after a round
    with no accepted leaf (line 13); T' is returned (line 14).

    A single remaining node is a leaf, so T' can become empty (A12). By Lemma 4.4 (EDGEWISE)
    the result is the unique minimum delta-mutable subtree, independent of the leaf order.
    """
    working: frozenset[NodeId] = frozenset(ghd.node_ids())
    steps: list[Alg2Step] = []
    rnd = 0
    changed = True
    while changed:
        changed = False
        rnd += 1
        for u in ghd.leaves_of(working):
            candidate = working - {u}
            check = mutable_conditions(change, ghd, candidate, semantics)
            accepted = check.condition_i and check.condition_ii
            steps.append(Alg2Step(
                round=rnd, leaf=u, outside=frozenset(ghd.node_ids()) - candidate,
                outside_vertices=check.outside_vertices, induced_equal=check.condition_i,
                adjacent_new=check.adjacent_new, accepted=accepted,
            ))
            if accepted:
                # Invariant I7 (Lemma 4.4): the working tree stays delta-mutable at every step.
                # Conditions (i) and (ii) were just checked; the third part of Def 4.1, being a
                # connected subtree, holds because u is a leaf. Asserted, not assumed.
                if not check.is_subtree:
                    raise AssertionError(
                        f"I7 violated: removing leaf {u} leaves a disconnected working tree "
                        f"{sorted(candidate)}")
                working = candidate
                changed = True
                break
    return MutableResult(t_star=working, steps=tuple(steps))

"""The two conditions of Def 4.1, evaluated literally (stage S9).

For a GHD of H with tree T and a node set T* (a subtree, possibly empty, A12):
  (i)  H[T \\ T*] = delta(H)[T \\ T*]       (compared under Semantics.induced_comparison, A2)
  (ii) no v in V(delta(H)) \\ V(H) is adjacent in delta(H) to a vertex of B(T \\ T*).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from ighd.common.config import PAPER_DEFAULT, Semantics
from ighd.common.types import NodeId, VertexSet
from ighd.ghd.tree import GHD
from ighd.hypergraph.compare import InducedDiff, induced_diff
from ighd.modifications.base import ModificationResult


@dataclass(frozen=True)
class MutabilityCheck:
    is_subtree: bool
    condition_i: bool
    condition_ii: bool
    outside_vertices: VertexSet
    """B(T \\ T*)."""
    diff: InducedDiff
    adjacent_new: VertexSet
    """New vertices adjacent to B(T \\ T*) (empty iff condition (ii) holds)."""

    @property
    def mutable(self) -> bool:
        return self.is_subtree and self.condition_i and self.condition_ii


def mutable_conditions(change: ModificationResult, ghd: GHD, t_star: Iterable[NodeId],
                       semantics: Semantics = PAPER_DEFAULT) -> MutabilityCheck:
    """Evaluate Def 4.1 for ``t_star`` (ghd must be a GHD of change.old).

    * is_subtree: ``t_star`` induces a connected subtree of T (the empty set counts, A12).
    * X = B(T minus T*), the union of the bags of all nodes outside ``t_star`` (D17).
    * condition (i): H[X] = delta(H)[X], decided by ``induced_diff`` under
      ``semantics.induced_comparison`` (A2; default EDGEWISE via s_delta).
    * condition (ii): V_new & adj_{delta(H)}(X) is empty, where V_new = change.new_vertices
      (Alg 2 line 3) and adj is ``Hypergraph.adjacent_to`` on delta(H) (Alg 2 line 9). That set
      includes X itself; this is harmless because new vertices never lie in old bags (A10).

    Raises InvalidGHDError for node ids that are not in ``ghd``.
    """
    s = frozenset(t_star)
    is_subtree = ghd.is_connected(s)  # also rejects unknown ids (InvalidGHDError)
    outside = [u for u in ghd.node_ids() if u not in s]
    outside_vertices = ghd.bag_union(outside)
    diff = induced_diff(change.old, change.new, outside_vertices, change.s_delta,
                        semantics.induced_comparison)
    adjacent_new = frozenset(change.new_vertices) & change.new.adjacent_to(outside_vertices)
    return MutabilityCheck(
        is_subtree=is_subtree,
        condition_i=diff.equal,
        condition_ii=not adjacent_new,
        outside_vertices=outside_vertices,
        diff=diff,
        adjacent_new=adjacent_new,
    )

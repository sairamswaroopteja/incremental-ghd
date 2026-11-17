"""Modification protocol and the change record every modification must produce.

Paper Def 3.1: a modification is any function from hypergraphs to hypergraphs. The update
framework (Def 4.1, Lemma 4.2, Lemma 4.4, Thm 4.5) works for any modification; what it needs
besides delta(H) is the edge correspondence s_delta (paper §5.1) and the set of new vertices
V_new = V(delta(H)) \\ V(H) (Alg 2 line 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ighd.common.types import EdgeName, EdgeSet, VertexSet
from ighd.hypergraph.core import Hypergraph


@dataclass(frozen=True)
class ModificationResult:
    """Everything known about one application delta(H).

    Invariants (checked by tests in S2):
      * ``s_delta`` has exactly the keys E(old); values are names in E(new) or None (deleted);
      * ``new_edges`` = E(new) minus the image of s_delta;
      * ``new_vertices`` = V(new) - V(old); ``removed_vertices`` = V(old) - V(new).
    """

    kind: str
    old: Hypergraph
    new: Hypergraph
    s_delta: Mapping[EdgeName, EdgeName | None]
    new_edges: EdgeSet
    new_vertices: VertexSet
    removed_vertices: VertexSet
    description: str

    @property
    def removed_edges(self) -> EdgeSet:
        """Old edges with s_delta(e) = None (deleted by delta)."""
        return frozenset(e for e, t in self.s_delta.items() if t is None)


class Modification(Protocol):
    """Anything that can be applied to a hypergraph and report the change."""

    def apply(self, h: Hypergraph) -> ModificationResult:
        """Apply to ``h``. Raises InvalidModificationError if the parameters do not fit ``h``."""
        ...

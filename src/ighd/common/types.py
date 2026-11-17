"""Basic type aliases and result enums shared by every module.

Naming follows the paper: hypergraph *vertices* and *edges* (named, e.g. "w1")
versus decomposition *nodes* (integer ids). The two are never mixed.
"""

from __future__ import annotations

from enum import Enum
from typing import NoReturn, TypeAlias

Vertex: TypeAlias = str
"""A hypergraph vertex (a CSP variable)."""

EdgeName: TypeAlias = str
"""The name of a hyperedge (a constraint scope), e.g. "w1". Edges have identity (PAPER_ANALYSIS A2)."""

NodeId: TypeAlias = int
"""A decomposition-tree node id. Stable within one GHD object."""

VertexSet: TypeAlias = frozenset[Vertex]
EdgeSet: TypeAlias = frozenset[EdgeName]


class SearchStatus(Enum):
    """Outcome of a decomposition search (IMPLEMENTATION_PLAN §A.1.4).

    FOUND      a decomposition was found (and must pass the validator);
    PROVEN_NO  an exhaustive EXACT search established that none exists;
    NOT_FOUND  a heuristic or budget-limited search failed: proves nothing.
    """

    FOUND = "found"
    PROVEN_NO = "proven_no"
    NOT_FOUND = "not_found"


class UpdateStatus(Enum):
    """Outcome of SearchUpdateGHD (paper §3.2).

    UPDATED    a GHD of delta(H) with width <= k is returned;
    PROVEN_NO  ghw(delta(H)) > k, established by an EXACT search of all of delta(H);
    NOT_FOUND  no GHD found, but nonexistence is not established.
    """

    UPDATED = "updated"
    PROVEN_NO = "proven_no"
    NOT_FOUND = "not_found"


class Minimality(Enum):
    """Whether the input GHD is known to have minimal width (precondition of SearchUpdateGHD, A14)."""

    VERIFIED = "verified"   # width == ghw(H), checked by the exact oracle
    ASSUMED = "assumed"     # not checked (e.g. instance too large for the oracle)
    REFUTED = "refuted"     # width > ghw(H): the paper's precondition does not hold


class DecomposerMode(Enum):
    """Separator enumeration mode of the top-down decomposer (IMPLEMENTATION_PLAN S7).

    EXACT      all bags conn <= B <= B(lambda) & (W | conn): complete for ghw <= k;
    HEURISTIC  only B = B(lambda) & (W | conn) (det-k-decomp style): sound, incomplete for ghw.
    """

    EXACT = "exact"
    HEURISTIC = "heuristic"


def todo(stage: str) -> NoReturn:
    """Marker for interface stubs: fails loudly until the named stage implements it."""
    raise NotImplementedError(f"not implemented yet (stage {stage}, IMPLEMENTATION_PLAN §C)")

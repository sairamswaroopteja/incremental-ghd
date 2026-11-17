"""Sequences of modifications (stage S2).

By Def 3.1 a sequence delta_l o ... o delta_1 is itself a modification, so the update framework
applies to it directly (PAPER_ANALYSIS §1 D11, guide §6.9). Composition chains s_delta maps and
accumulates new/removed vertices relative to the *first* hypergraph.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ighd.common.errors import InvalidModificationError
from ighd.common.types import EdgeName
from ighd.hypergraph.core import Hypergraph
from ighd.modifications.base import Modification, ModificationResult
from ighd.modifications.ops import _finish


def compose(results: Sequence[ModificationResult]) -> ModificationResult:
    """Compose consecutive results (results[i].new must equal results[i+1].old).

    The composed s_delta is the chain s_l o ... o s_1 (None absorbs: an edge deleted at some
    step stays deleted). new_edges, new_vertices and removed_vertices are recomputed between
    results[0].old and results[-1].new, so a vertex added and later removed appears in neither.
    Raises ValueError on an empty sequence or a broken chain.
    """
    rs = list(results)
    if not rs:
        raise ValueError("compose: empty sequence of modification results")
    for i in range(len(rs) - 1):
        if rs[i].new != rs[i + 1].old:
            raise ValueError(f"compose: result {i} ({rs[i].kind}) does not end where result {i + 1} "
                             f"({rs[i + 1].kind}) starts")
    chained: dict[EdgeName, EdgeName | None] = {e: e for e in rs[0].old.edge_names}
    for i, r in enumerate(rs):
        for e, cur in chained.items():
            if cur is None:
                continue
            if cur not in r.s_delta:
                raise ValueError(f"compose: s_delta of result {i} ({r.kind}) has no entry for edge {cur!r}")
            chained[e] = r.s_delta[cur]
    return _finish("Sequence", rs[0].old, rs[-1].new, chained, "; ".join(r.description for r in rs))


@dataclass(frozen=True)
class ModificationSequence:
    """Apply several modifications in order, as one modification (Def 3.1)."""

    steps: tuple[Modification, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))

    def apply(self, h: Hypergraph) -> ModificationResult:
        """Apply every step to the result of the previous one and compose the results.

        Raises InvalidModificationError for an empty sequence, or (from the failing step) if a
        step's parameters do not fit the hypergraph it is applied to.
        """
        if not self.steps:
            raise InvalidModificationError("ModificationSequence: no steps")
        results: list[ModificationResult] = []
        cur = h
        for step in self.steps:
            r = step.apply(cur)
            results.append(r)
            cur = r.new
        return compose(results)

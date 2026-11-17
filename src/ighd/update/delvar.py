"""DelVar fast path (paper §3.2, footnote 1, §6.1): delete the vertex from every bag.

DelVar yields an induced subhypergraph, whose ghw never exceeds the old one. The GHD with
B'_u = B_u - {v} and lambda'_u = delta(lambda_u) (edges emptied by the deletion dropped, A6) is a
GHD of delta(H) of width <= k (proof: study guide §5.3; coverage, connectedness and guards are
each preserved). The tree is unchanged. The result may be non-optimal (ghw can drop).
"""

from __future__ import annotations

from ighd.ghd.tree import GHD
from ighd.modifications.base import ModificationResult


def delvar_update(change: ModificationResult, old: GHD) -> GHD:
    """Apply the DelVar rule to a copy of ``old`` (a GHD of change.old)."""
    if change.kind != "DelVar":
        raise ValueError(f"delvar_update needs a DelVar change, got {change.kind}")
    out = old.copy()
    removed = change.removed_vertices
    for node in list(out):
        cover = frozenset(t for e in node.cover if (t := change.s_delta.get(e)) is not None)
        out.set_labels(node.id, bag=node.bag - removed, cover=cover)
    return out

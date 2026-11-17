"""M7-M8: [U]-components and the top-down decomposer (paper §2.3, Algorithm 1)."""

from ighd.static.separation import components, connection, inside_edges
from ighd.static.decomposer import (
    DecompositionTask,
    DecompResult,
    DecompStats,
    Decomposer,
    TopDownDecomposer,
    ghw_by_search,
)

__all__ = [
    "DecompResult", "DecompStats", "DecompositionTask", "Decomposer", "TopDownDecomposer",
    "components", "connection", "ghw_by_search", "inside_edges",
]

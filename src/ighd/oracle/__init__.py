"""M6: exact reference procedures for small instances (stage S5).

INDEPENDENCE RULE: must not import ighd.static, ighd.update, ighd.scenes, ighd.constraints
or ighd.mutable. These are ground truth for those modules.
"""

from ighd.oracle.brute_mutable import MAX_BRUTE_NODES, all_mutable_subtrees
from ighd.oracle.edge_cover import edge_cover_number, minimum_edge_cover
from ighd.oracle.ghw_dp import MAX_ORACLE_VERTICES, exact_ghw

__all__ = [
    "MAX_BRUTE_NODES", "MAX_ORACLE_VERTICES", "all_mutable_subtrees", "edge_cover_number",
    "exact_ghw", "minimum_edge_cover",
]

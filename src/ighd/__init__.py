"""ighd: incremental updates of generalized hypertree decompositions.

Research implementation of Gottlob, Lanzinger, Longo, Okulmus,
"Incremental Updates of Generalized Hypertree Decompositions" (arXiv:2209.10375).

Package map (IMPLEMENTATION_PLAN §A.2):
    common         shared types, result enums, semantics switches, budgets
    hypergraph     M1  hypergraphs with named edges, induced subhypergraphs
    modifications  M2  the six elementary modifications (Defs 3.2-3.4)
    ghd            M3-M5  GHD tree, independent validator, normal-form checker
    oracle         M6  exact ghw and brute-force reference procedures
    static         M7-M8  [U]-components and the top-down decomposer (Alg 1)
    mutable        M9  delta-mutable subtrees (Def 4.1, Alg 2)
    constraints    M10 delta(H)*, bag constraints, Theorem 4.5 gluing
    scenes         M11 scene mappings (Def 5.1, Algs 3-4)
    update         M12 GHDUpdate (Alg 5) and update strategies
"""

__version__ = "0.0.1"

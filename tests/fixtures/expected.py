"""Expected intermediate results for later stages, each with its provenance.

"paper"  = stated in arXiv:2209.10375v1;
"guide"  = hand-verified trace in Incremental_GHD_Updates_Guide.pdf (constructed from the paper's
           definitions; to be re-checked by the stage that consumes it, never trusted blindly).
Where the paper's statement conflicts with its own pseudocode, both are recorded (A16).
"""

from __future__ import annotations

from tests.fixtures.paper import G2_SPEC, G_PRIME_SPEC, H_P, H_P2, H_P3, H_PP, JOIN_TREE_HP_SPEC, S_SPEC

fs = frozenset

# --- S1: hypergraph basics ------------------------------------------------------------------
HPP_RANK = 3
HPP_DEGREES = {"a": 2, "b": 1, "c": 2, "d": 1, "e": 2, "f": 2, "g": 1, "h": 2,
               "i": 1, "j": 1, "k": 2, "l": 1}
HPP_INDUCED_ADFGH = {"w4": fs("adf"), "w2": fs("fgh"), "w1": fs("a"), "w5": fs("h")}
"""guide Fig. 15 / paper Fig. 6(b): H_P'[{a,d,f,g,h}]."""

# --- S5: exact ghw ----------------------------------------------------------------------------
GHW = {"H_P": 1, "H_PP": 2, "H_P2": 2, "H_P3": 2}
"""paper Ex. 2.2 (H_P, H_PP); guide §2.5/§8.4/§8.6 (H_P2, H_P3)."""

# --- S6: components --------------------------------------------------------------------------
COMPONENT_CASES = [
    # (hypergraph, edge subset (None = all), separator, expected components, provenance)
    (H_PP, None, fs("cehik"), [fs({"w1", "w2", "w4"}), fs({"w6"})], "paper Ex. 2.3 / Fig. 4"),
    (H_PP, fs({"w1", "w2", "w4"}), fs("abcfgh"), [fs({"w4"})], "paper Ex. 2.3"),
    (H_PP, None, fs("abceh"), [fs({"w2", "w4"}), fs({"w3", "w6"})], "paper Ex. 5.2"),
    (H_PP, fs({"w3", "w6"}), fs("ceik"), [fs({"w6"})], "paper Ex. 5.2 (C4)"),
]

# --- S9: minimal delta-mutable subtrees (Algorithm 2) ------------------------------------------
# (case id, base hypergraph, base GHD spec, modification as (class name, kwargs), expected T* labels, provenance)
T_STAR_CASES = [
    ("ex43_delconstr", H_P2, G2_SPEC, ("DelConstr", {"name": "w7"}), fs({"u1", "u2"}), "paper Ex. 4.3 / Fig. 6(a)"),
    ("addconstr_w7", H_PP, G_PRIME_SPEC, ("AddConstr", {"name": "w7", "vertices": fs("ci")}), fs({"t1", "t2"}), "guide §8.4"),
    ("addvar_m", H_PP, G_PRIME_SPEC, ("AddVar", {"vertex": "m", "edges": fs({"w6"})}), fs({"t1", "t4"}), "guide §8.3"),
    ("addeq_bg", H_PP, G_PRIME_SPEC, ("AddEq", {"merge": fs("bg"), "into": "g"}), fs({"t2"}), "guide §8.6"),
    ("deleq_g", H_P3, S_SPEC, ("DelEq", {"vertex": "g", "parts": {"g": fs({"w2"}), "b": fs({"w1"})}}),
     fs({"s1", "s2", "s3"}), "guide §8.7"),
    ("addvar_h_jointree", H_P, JOIN_TREE_HP_SPEC, ("AddVar", {"vertex": "h", "edges": fs({"w2", "w5"})}),
     fs({"p1", "p2", "p3", "p4", "p5"}), "guide §8.2"),
    ("delvar_h", H_PP, G_PRIME_SPEC, ("DelVar", {"vertex": "h"}), fs({"t1", "t2"}), "guide §8.1"),
]

# --- S10: bag constraints of Example 4.3 --------------------------------------------------------
EX43_CONSTRAINTS = {"u3": fs("ah"), "u4": fs("k")}
"""(outer node label -> C_i), guide §6.6."""

EX43_REPAIRED_SPEC = {
    "root": "n1",
    "nodes": {"n1": ("abceh", ("w1", "w5")), "n2": ("eik", ("w3",)),
              "u3": ("adfgh", ("w2", "w4")), "u4": ("jkl", ("w6",))},
    "children": {"n1": ["n2", "u3"], "n2": ["u4"], "u3": [], "u4": []},
}
"""guide §6.8 / §9.9: the repaired GHD of H_P' (paper Ex. 4.3 prose: bag {c,e,i,k} -> {e,i,k}, w7 removed)."""

# --- S11: scene mapping of Example 5.2 -----------------------------------------------------------
ALL_HPP_EDGES = fs(H_PP)
EX52_SIGMA_PSEUDOCODE = {
    ALL_HPP_EDGES: ("u1", "in"),
    fs({"w2", "w4"}): ("u3", "out"),
    fs({"w6"}): ("u4", "out"),
}
"""Our literal run of Alg 3/4 (scene_guard_check=True, up_scene_key=COVERED_EDGES), guide §9.6."""

EX52_SIGMA_AS_STATED = {
    ALL_HPP_EDGES: ("u1", "in"),
    fs({"w3", "w6"}): ("u2", "in"),
    fs({"w2", "w4"}): ("u3", "out"),
    fs({"w6"}): ("u4", "out"),
}
"""Paper Ex. 5.2 as printed. The paper does not state kinds; ours follow Def 5.1 (in iff the node
lies in T* = {u1, u2}). Conflicts with Alg 3 line 3 at u2 (A16)."""

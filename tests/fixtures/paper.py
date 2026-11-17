"""The paper's running example as plain data (arXiv:2209.10375v1).

Everything here is transcribed from the paper unless its PROVENANCE entry says otherwise.
Plain dicts and frozensets only, so the fixtures do not depend on any implementation.

Naming notes (transcription decisions, recorded so they can be reviewed):
  * H_P's middle-column edge {c, e} is labelled w'_5 in Fig. 2(a). It is named "w5" here, so that
    the AddVar of Example 3.5 (which turns it into {c, e, h} = w5 of H_P') keeps the edge's
    identity (s_delta(w5) = w5).
  * H_P3's T-shaped edge {a, c, g} keeps the label w1 (Fig. 5(b) labels it w1).
  * The nodes of Fig. 3 are unnamed in the paper; they are named t1..t4 here (as in the study guide).
"""

from __future__ import annotations


def _e(**edges: str) -> dict[str, frozenset[str]]:
    return {name: frozenset(vs) for name, vs in edges.items()}


# --- hypergraphs (Fig. 2, Fig. 5) ---------------------------------------------------------
H_P = _e(w1="abc", w2="fg", w3="eik", w4="adf", w5="ce", w6="jkl")
"""Fig. 2(a): hypergraph of puzzle P (acyclic, ghw 1). "w5" is the paper's w'_5."""

H_PP = _e(w1="abc", w2="fgh", w3="eik", w4="adf", w5="ceh", w6="jkl")
"""Fig. 2(b): hypergraph of puzzle P' (cyclic, ghw 2)."""

H_P2 = {**H_PP, "w7": frozenset("ci")}
"""Fig. 5(a): H_P' plus the new edge w7 = {c, i} (AddConstr, Example 3.5)."""

H_P3 = {**H_PP, "w1": frozenset("acg")}
"""Fig. 5(b): H_P' with b merged into g (AddEq, Example 3.5); w1 becomes {a, c, g}."""

# --- CSP view of P' (Example 2.1) ---------------------------------------------------------
SCOPES_PP: dict[str, tuple[str, ...]] = {
    "w1": ("a", "b", "c"), "w2": ("f", "g", "h"), "w3": ("e", "i", "k"),
    "w4": ("a", "d", "f"), "w5": ("c", "e", "h"), "w6": ("j", "k", "l"),
}
"""Ordered scopes (reading direction of each word slot)."""

WORDS_EX21 = frozenset({"dog", "god", "odd"})
SOLUTION_EX21 = dict(zip("abcdefghijkl", "godoodogdodd"))
"""Example 2.1: <a,...,l> = <g,o,d,o,o,d,o,g,d,o,d,d>."""

# --- GHDs (GhdSpec-shaped plain data) -------------------------------------------------------
G_PRIME_SPEC = {
    "root": "t1",
    "nodes": {
        "t1": ("cehik", ("w5", "w3")),
        "t2": ("abcfgh", ("w1", "w2")),
        "t3": ("adf", ("w4",)),
        "t4": ("jkl", ("w6",)),
    },
    "children": {"t1": ["t2", "t4"], "t2": ["t3"], "t3": [], "t4": []},
}
"""Fig. 3: a width-2 GHD of H_P' (Example 2.2). Child order follows Example 2.3 (C1 then C2)."""

G2_SPEC = {
    "root": "u1",
    "nodes": {
        "u1": ("abceh", ("w1", "w5")),
        "u2": ("ceik", ("w3", "w7")),
        "u3": ("adfgh", ("w2", "w4")),
        "u4": ("jkl", ("w6",)),
    },
    "children": {"u1": ["u2", "u3"], "u2": ["u4"], "u3": [], "u4": []},
}
"""Fig. 6(a): a width-2 GHD of H_P2, input of Examples 4.3 and 5.2."""

JOIN_TREE_HP_SPEC = {
    "root": "p1",
    "nodes": {
        "p1": ("fg", ("w2",)), "p2": ("adf", ("w4",)), "p3": ("abc", ("w1",)),
        "p4": ("ce", ("w5",)), "p5": ("eik", ("w3",)), "p6": ("jkl", ("w6",)),
    },
    "children": {"p1": ["p2"], "p2": ["p3"], "p3": ["p4"], "p4": ["p5"], "p5": ["p6"], "p6": []},
}
"""Width-1 GHD of H_P from the join tree w2-w4-w1-w5-w3-w6 (study guide §2.5/§8.2; NOT in the paper)."""

S_SPEC = {
    "root": "s1",
    "nodes": {
        "s1": ("cehik", ("w5", "w3")),
        "s2": ("acfgh", ("w1", "w2")),
        "s3": ("adf", ("w4",)),
        "s4": ("jkl", ("w6",)),
    },
    "children": {"s1": ["s2", "s4"], "s2": ["s3"], "s3": [], "s4": []},
}
"""Width-2 GHD of H_P3 (study guide §8.6 result, relabelled; NOT in the paper)."""

PROVENANCE = {
    "H_P": "paper Fig. 2(a) (edge w'_5 named w5)",
    "H_PP": "paper Fig. 2(b)",
    "H_P2": "paper Fig. 5(a), Example 3.5",
    "H_P3": "paper Fig. 5(b), Example 3.5",
    "SCOPES_PP": "paper Fig. 1(b), Example 2.1",
    "SOLUTION_EX21": "paper Example 2.1",
    "G_PRIME_SPEC": "paper Fig. 3 (node names ours)",
    "G2_SPEC": "paper Fig. 6(a)",
    "JOIN_TREE_HP_SPEC": "study guide §8.2 (constructed)",
    "S_SPEC": "study guide §8.6 (constructed)",
}

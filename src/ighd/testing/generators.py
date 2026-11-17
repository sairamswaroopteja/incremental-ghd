"""Seeded random hypergraphs and VALID random elementary modifications (Defs 3.2-3.4).

All randomness comes from the caller's ``random.Random`` instance, so every test is reproducible
from its seed. Generated modifications always satisfy the parameter rules of ighd.modifications
(they may still be rejected by ``apply`` in rare corner cases, which callers skip).
"""

from __future__ import annotations

import random

from ighd.hypergraph.core import Hypergraph
from ighd.modifications.base import Modification
from ighd.modifications.ops import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar

KINDS: tuple[str, ...] = ("AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq")


def random_hypergraph(rng: random.Random, *, min_vertices: int = 4, max_vertices: int = 7,
                      min_edges: int = 3, max_edges: int = 6, max_rank: int = 3) -> Hypergraph:
    """Edges w0..w{m-1}, each of 2..max_rank distinct vertices drawn from a..g (or more)."""
    alphabet = [chr(ord("a") + i) for i in range(max(max_vertices, 2))]
    vs = alphabet[: rng.randint(min_vertices, max_vertices)]
    edges = {f"w{i}": rng.sample(vs, rng.randint(2, min(max_rank, len(vs))))
             for i in range(rng.randint(min_edges, max_edges))}
    return Hypergraph(edges)


def random_modification(rng: random.Random, h: Hypergraph, kind: str) -> Modification | None:
    """A random valid modification of class ``kind`` for ``h`` (None if none exists, e.g. DelEq
    without a vertex of degree >= 2). New vertices are named z, y, v2; new edges wnew."""
    names, verts = sorted(h.edge_names), sorted(h.vertices)
    if not names:
        return None
    if kind == "AddVar":
        return AddVar("z", frozenset(rng.sample(names, rng.randint(1, len(names)))))
    if kind == "DelVar":
        return DelVar(rng.choice(verts))
    if kind == "AddConstr":
        pick = rng.sample(verts, rng.randint(1, min(3, len(verts))))
        if rng.random() < 0.15:                    # occasionally touch a fresh vertex (A12 path)
            pick = pick[:1] + ["y"]
        return AddConstr("wnew", frozenset(pick))
    if kind == "DelConstr":
        return DelConstr(rng.choice(names))
    if kind == "AddEq":
        if len(verts) < 2:
            return None
        a, b = rng.sample(verts, 2)
        return AddEq(frozenset({a, b}), a)
    if kind == "DelEq":
        deg2 = [v for v in verts if len(h.incident(v)) >= 2]
        if not deg2:
            return None
        v = rng.choice(deg2)
        inc = sorted(h.incident(v))
        keep = frozenset(rng.sample(inc, rng.randint(1, len(inc) - 1)))
        return DelEq(v, {v: keep, "v2": frozenset(inc) - keep})
    raise ValueError(f"unknown modification kind {kind!r}")

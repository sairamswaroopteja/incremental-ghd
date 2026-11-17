"""The paper's §6.1 modification generator (seeded).

Five modifications per class per hypergraph (``per_class``), drawn as in §6.1:

  AddVar     a fresh vertex added to ⌈avg degree⌉ distinct random edges (capped at |E|);
  AddEq      two distinct random vertices x1, x2 merged into x1;
  DelEq      a random vertex x of degree >= 2 split into two fresh vertices y1, y2; x's incident
             edges are shuffled and y1 receives the first ⌊d/2⌋, y2 the remaining ⌈d/2⌉;
  AddConstr  a new edge on ⌈avg rank⌉ distinct random EXISTING vertices (capped at |V|);
  DelConstr  a random edge deleted.
  DelVar     (not in the paper's protocol; only with --with-delvar) a random vertex deleted.

avg degree = sum|e| / |V| and avg rank = sum|e| / |E| (``loader.InstanceInfo``).

Invalid draws are redrawn with the SAME rng and counted, never dropped silently. A draw is
invalid if the modification class rejects it (``InvalidModificationError``, e.g. DelEq of a
degree-1 vertex cannot give each part an edge) or if an AddConstr scope equals an existing edge's
vertex set (that would only duplicate a constraint scope). Merges that make two existing edges
equal (A9) are valid: both names are kept by ``ighd`` and the record says so
(``creates_duplicate_edges``). If a class is not applicable at all, or ``MAX_REDRAWS`` redraws
fail, the slot is recorded with ``failure`` set and no modification.

Every (seed, instance, class) has its own ``random.Random`` seeded with a string, which Python
hashes with SHA-512, so draws do not depend on PYTHONHASHSEED, on other classes or on --limit.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field

from ighd.common.errors import InvalidModificationError
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar, Modification

from benchmarks.loader import InstanceInfo, ceil_avg_degree, ceil_avg_rank

PAPER_CLASSES: tuple[str, ...] = ("AddVar", "AddEq", "DelEq", "AddConstr", "DelConstr")
ALL_CLASSES: tuple[str, ...] = PAPER_CLASSES + ("DelVar",)
MAX_REDRAWS = 1000


@dataclass
class ModRecord:
    """One generated modification slot (``spec`` is None iff ``failure`` is set)."""

    instance: str
    mod_class: str
    index: int
    spec: dict | None
    description: str = ""
    redraws: int = 0
    redraw_reasons: dict = field(default_factory=dict)
    creates_duplicate_edges: bool = False
    failure: str | None = None

    def to_dict(self) -> dict:
        return {"instance": self.instance, "mod_class": self.mod_class, "index": self.index,
                "spec": self.spec, "description": self.description, "redraws": self.redraws,
                "redraw_reasons": dict(self.redraw_reasons),
                "creates_duplicate_edges": self.creates_duplicate_edges, "failure": self.failure}


# ------------------------------------------------------------------ (de)serialisation
def to_spec(mod: Modification) -> dict:
    if isinstance(mod, AddVar):
        return {"kind": "AddVar", "vertex": mod.vertex, "edges": sorted(mod.edges)}
    if isinstance(mod, AddEq):
        return {"kind": "AddEq", "merge": sorted(mod.merge), "into": mod.into}
    if isinstance(mod, DelEq):
        return {"kind": "DelEq", "vertex": mod.vertex,
                "parts": {p: sorted(es) for p, es in sorted(mod.parts.items())}}
    if isinstance(mod, AddConstr):
        return {"kind": "AddConstr", "name": mod.name, "vertices": sorted(mod.vertices)}
    if isinstance(mod, DelConstr):
        return {"kind": "DelConstr", "name": mod.name}
    if isinstance(mod, DelVar):
        return {"kind": "DelVar", "vertex": mod.vertex}
    raise TypeError(f"not an elementary modification: {mod!r}")


def from_spec(spec: dict) -> Modification:
    kind = spec["kind"]
    if kind == "AddVar":
        return AddVar(spec["vertex"], frozenset(spec["edges"]))
    if kind == "AddEq":
        return AddEq(frozenset(spec["merge"]), spec["into"])
    if kind == "DelEq":
        return DelEq(spec["vertex"], {p: frozenset(es) for p, es in spec["parts"].items()})
    if kind == "AddConstr":
        return AddConstr(spec["name"], frozenset(spec["vertices"]))
    if kind == "DelConstr":
        return DelConstr(spec["name"])
    if kind == "DelVar":
        return DelVar(spec["vertex"])
    raise ValueError(f"unknown modification kind {kind!r}")


# ------------------------------------------------------------------ drawing
def _fresh(prefix: str, taken: frozenset[str] | set[str]) -> str:
    i = 0
    while f"{prefix}{i}" in taken:
        i += 1
    return f"{prefix}{i}"


def _applicable(h: Hypergraph, cls: str) -> str | None:
    """None if the class can be drawn on ``h``, else the reason it cannot."""
    nv, ne = len(h.vertices), len(h.edge_names)
    if cls in ("AddVar", "DelConstr") and ne == 0:
        return "hypergraph has no edges"
    if cls in ("AddConstr", "DelVar") and nv == 0:
        return "hypergraph has no vertices"
    if cls == "AddEq" and nv < 2:
        return "AddEq needs two vertices"
    if cls == "DelEq" and not any(h.degree(v) >= 2 for v in h.vertices):
        return "DelEq needs a vertex of degree >= 2 (each half receives an edge)"
    return None


def draw(cls: str, h: Hypergraph, info: InstanceInfo, rng: random.Random) -> Modification:
    """One raw §6.1 draw of class ``cls`` (possibly invalid; see :func:`invalid_reason`)."""
    vertices = sorted(h.vertices)
    edges = sorted(h.edge_names)
    if cls == "AddVar":
        m = min(ceil_avg_degree(info), len(edges))
        return AddVar(_fresh("bench_v", h.vertices), frozenset(rng.sample(edges, m)))
    if cls == "AddEq":
        x1, x2 = rng.sample(vertices, 2)
        return AddEq(frozenset({x1, x2}), x1)
    if cls == "DelEq":
        x = rng.choice(vertices)
        inc = sorted(h.incident(x))
        rng.shuffle(inc)
        half = len(inc) // 2
        y1 = _fresh("bench_y", h.vertices)
        y2 = _fresh("bench_y", h.vertices | {y1})
        return DelEq(x, {y1: frozenset(inc[:half]), y2: frozenset(inc[half:])})
    if cls == "AddConstr":
        m = min(ceil_avg_rank(info), len(vertices))
        return AddConstr(_fresh("bench_e", h.edge_names), frozenset(rng.sample(vertices, m)))
    if cls == "DelConstr":
        return DelConstr(rng.choice(edges))
    if cls == "DelVar":
        return DelVar(rng.choice(vertices))
    raise ValueError(f"unknown modification class {cls!r}")


def invalid_reason(h: Hypergraph, mod: Modification) -> str | None:
    """Why a raw draw must be redrawn (None if it is valid)."""
    try:
        mod.apply(h)
    except InvalidModificationError as exc:
        if isinstance(mod, DelEq) and h.degree(mod.vertex) < 2:
            return "DelEq: drawn vertex has degree < 2 (a half would receive no edge)"
        # the class's message without the concrete names, so reasons aggregate
        return f"{type(mod).__name__} rejected: " + re.sub(r"'[^']*'|\[[^\]]*\]|\{[^}]*\}", "_", str(exc))
    if isinstance(mod, AddConstr) and mod.vertices in set(h.edges.values()):
        return "AddConstr scope equals an existing edge"
    return None


def _duplicate_pairs(h: Hypergraph) -> int:
    c = Counter(h.edges.values())
    return sum(n * (n - 1) // 2 for n in c.values())


def generate(h: Hypergraph, info: InstanceInfo, seed: int, per_class: int,
             classes: tuple[str, ...] = PAPER_CLASSES) -> list[ModRecord]:
    """``per_class`` §6.1 modifications of every class in ``classes`` (see module docstring)."""
    out: list[ModRecord] = []
    base_dups = _duplicate_pairs(h)
    for cls in classes:
        rng = random.Random(f"ighd-bench|{seed}|{info.name}|{cls}")
        reason = _applicable(h, cls)
        for i in range(per_class):
            if reason is not None:
                out.append(ModRecord(info.name, cls, i, None, failure=f"not applicable: {reason}"))
                continue
            reasons: Counter = Counter()
            mod = None
            while True:
                cand = draw(cls, h, info, rng)
                why = invalid_reason(h, cand)
                if why is None:
                    mod = cand
                    break
                reasons[why] += 1
                if sum(reasons.values()) >= MAX_REDRAWS:
                    break
            n = sum(reasons.values())
            if mod is None:
                out.append(ModRecord(info.name, cls, i, None, redraws=n, redraw_reasons=dict(reasons),
                                     failure=f"no valid draw after {n} redraws"))
                continue
            change = mod.apply(h)
            out.append(ModRecord(info.name, cls, i, to_spec(mod), change.description, n, dict(reasons),
                                 _duplicate_pairs(change.new) > base_dups))
    return out

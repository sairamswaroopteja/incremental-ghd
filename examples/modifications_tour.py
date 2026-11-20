"""A tour of hypergraph modifications: one hypergraph, a chain of edits, and what happens to its
generalized hypertree width (ghw) and to the decomposition after every edit.

For every step it prints
  * the modification and the edges it changed (+ added, - deleted, ~ changed),
  * ghw before -> after, computed independently by the exact oracle,
  * the answer of the incremental update (PAPER strategy = the paper's Algorithm 5) for the
    current width k, which old decomposition nodes were reused, and the new decomposition.
When ghw rises above k the update answers PROVEN_NO (no GHD of width k exists); the tour then
computes a fresh minimum-width GHD and continues with the new k. When ghw drops, the update may
keep the old width: the paper only promises width <= k, not minimality.

Run from the project root:   python examples/modifications_tour.py [--png out.png]
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from ighd.common import DecomposerMode, UpdateStatus  # noqa: E402
from ighd.ghd import GHD, validate  # noqa: E402
from ighd.hypergraph import Hypergraph  # noqa: E402
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar  # noqa: E402
from ighd.oracle import exact_ghw  # noqa: E402
from ighd.static import ghw_by_search  # noqa: E402
from ighd.update import Strategy, ghd_update  # noqa: E402

fs = frozenset

START = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd", "e4": "de", "e5": "ef"})
STEPS = [
    ("close a cycle a-b-c-d-e-f-a", AddConstr("e6", fs("fa"))),
    ("put a new vertex x into two opposite edges", AddVar("x", fs({"e1", "e4"}))),
    ("add a chord a-d", AddConstr("e7", fs("ad"))),
    ("add a chord b-e: three overlapping cycles", AddConstr("e8", fs("be"))),
    ("add a chord c-f: now every opposite pair is joined", AddConstr("e9", fs("cf"))),
    ("merge c into b (an equality constraint)", AddEq(fs("bc"), "b")),
    ("delete the chord a-d", DelConstr("e7")),
    ("split b again into b and c", DelEq("b", {"b": fs({"e1", "e2", "e8"}),
                                              "c": fs({"e2", "e3", "e9"})})),
    ("delete vertex x", DelVar("x")),
    ("delete the cycle-closing edge f-a", DelConstr("e6")),
    ("delete the chord b-e", DelConstr("e8")),
    ("delete the chord c-f: back to a tree-like hypergraph", DelConstr("e9")),
]


def s(xs) -> str:
    return "{" + ",".join(sorted(xs)) + "}"


def edge_diff(old: Hypergraph, new: Hypergraph, s_delta) -> list[str]:
    out = []
    for e, vs in sorted(old.edges.items()):
        t = s_delta.get(e)
        if t is None:
            out.append(f"- {e}{s(vs)}")
        elif new.edge(t) != vs:
            out.append(f"~ {e}{s(vs)}->{s(new.edge(t))}")
    image = {t for t in s_delta.values() if t is not None}
    out += [f"+ {e}{s(vs)}" for e, vs in sorted(new.edges.items()) if e not in image]
    return out


def show_tree(g: GHD, reused_bags: set) -> None:
    def rec(u, depth):
        n = g.node(u)
        tag = "reused" if (n.bag, n.cover) in reused_bags else "new"
        print(f"      {'    ' * depth}[{tag:6s}] bag={s(n.bag):12s} cover={s(n.cover)}")
        for c in g.children(u):
            rec(c, depth + 1)
    rec(g.root, 0)


def tour(png: str | None = None) -> list[dict]:
    h = START
    k, g, _ = ghw_by_search(h, DecomposerMode.EXACT)
    print("START  H0:", "  ".join(f"{e}{s(v)}" for e, v in sorted(h.edges.items())))
    print(f"       ghw(H0) = {exact_ghw(h)[0]} (oracle), decomposition of width {k}:")
    show_tree(g, set())
    frames = [dict(title="H0", why="a path a-b-c-d-e-f", h=h, g=g, ghw=k, k=k, status="start",
                   reused=set(), changed=set())]
    log = []

    for i, (why, mod) in enumerate(STEPS, 1):
        change = mod.apply(h)
        before, after = exact_ghw(h)[0], exact_ghw(change.new)[0]
        t0 = time.perf_counter()
        r = ghd_update(h, g, mod, strategy=Strategy.PAPER, delvar_fast_path=False)
        ms = (time.perf_counter() - t0) * 1000
        arrow = "rises" if after > before else "drops" if after < before else "stays"
        print("\n" + "-" * 78)
        print(f"STEP {i}: {why}")
        print(f"   modification : {change.description}")
        print(f"   edges        : {'   '.join(edge_diff(h, change.new, change.s_delta))}")
        print(f"   ghw          : {before} -> {after}  ({arrow}; exact oracle)")
        old_bags = {(g.node(u).bag & change.new.vertices,
                     fs(t for e in g.node(u).cover if (t := change.s_delta.get(e)) is not None))
                    for u in r.trace.reused_nodes}
        if r.status is UpdateStatus.UPDATED:
            assert validate(change.new, r.ghd).ok
            print(f"   update (k={k}): UPDATED in {ms:.1f} ms -> width {r.width}; reused "
                  f"{len(r.trace.reused_nodes)} of {len(g)} old nodes, "
                  f"{len(r.trace.decomposer_calls)} decomposer call(s)")
            show_tree(r.ghd, old_bags)
            new_g, new_k = r.ghd, k
            if r.width > after:
                print(f"   note         : width {r.width} > ghw {after}. Allowed (the update promises "
                      f"width <= k, not minimality), but the")
                print("                  paper's update needs a MINIMUM-width input, so before the "
                      "next step a fresh one is computed:")
                new_k, new_g, _ = ghw_by_search(change.new, DecomposerMode.EXACT)
                show_tree(new_g, set())
        else:
            print(f"   update (k={k}): {r.status.value.upper()} in {ms:.1f} ms -> no GHD of width {k} "
                  f"exists (exact search; oracle agrees: ghw = {after})")
            new_k, new_g, _ = ghw_by_search(change.new, DecomposerMode.EXACT)
            print(f"                  fresh minimum-width decomposition computed, new k = {new_k}:")
            show_tree(new_g, set())
        assert (r.status is UpdateStatus.UPDATED) == (after <= k)
        changed = {t for e, t in change.s_delta.items() if t is None or change.new.edge(t) != h.edge(e)}
        changed |= set(change.new.edge_names) - {t for t in change.s_delta.values() if t}
        frames.append(dict(title=f"step {i}: {type(mod).__name__}", why=why, h=change.new, g=new_g,
                           before=before, ghw=after, k=k, status=r.status.value,
                           reused=old_bags if new_g is r.ghd else set(),
                           recomputed=new_g is not r.ghd, changed=changed - {None}))
        log.append(dict(step=i, kind=type(mod).__name__, before=before, after=after,
                        status=r.status.value, width=r.width, k=k))
        h, g, k = change.new, new_g, new_k

    print("\n" + "=" * 78 + "\nSUMMARY   step  modification   ghw before->after   update answer (k)")
    for row in log:
        ans = f"{row['status']} (width {row['width']})" if row["width"] else row["status"]
        print(f"          {row['step']:4d}  {row['kind']:12s}   {row['before']} -> {row['after']}"
              f"              {ans}  (k={row['k']})")
    if png:
        from examples.tour_plot import draw
        draw(frames, png)
        print(f"\npicture of every step written to {png}")
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", help="also draw every step into this PNG file")
    tour(ap.parse_args().png)

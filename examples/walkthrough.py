"""Guided walkthrough: the paper's Examples 4.3 / 5.2 step by step, then each update strategy on
every modification class, a correct "no", and the A21 issue found in the paper's Algorithm 5.

Run from the project root:   python examples/walkthrough.py
Output is plain ASCII so it renders in any console.
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from ighd.common import DecomposerMode, UpdateStatus  # noqa: E402
from ighd.common.config import Semantics  # noqa: E402
from ighd.common.errors import InvalidGHDError  # noqa: E402
from ighd.ghd import GHD, check_normal_form, validate  # noqa: E402
from ighd.hypergraph import Hypergraph  # noqa: E402
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar  # noqa: E402
from ighd.mutable import minimal_mutable_subtree  # noqa: E402
from ighd.oracle import exact_ghw  # noqa: E402
from ighd.scenes.scene_down import scene_create  # noqa: E402
from ighd.static import ghw_by_search  # noqa: E402
from ighd.update import Strategy, ghd_update  # noqa: E402
from tests.fixtures.paper import G2_SPEC, H_P2  # noqa: E402


def banner(title: str) -> None:
    print("\n" + "=" * 78 + f"\n {title}\n" + "=" * 78)


def s(xs) -> str:
    return "{" + ",".join(sorted(xs)) + "}"


def name(g: GHD, u) -> str:
    return g.node(u).label or f"#{u}"


def show_tree(g: GHD, marks: dict | None = None) -> None:
    marks = marks or {}

    def rec(u, depth):
        n = g.node(u)
        tag = f"   <- {marks[u]}" if u in marks else ""
        print(f"   {'    ' * depth}{name(g, u):4s} bag={s(n.bag):14s} cover={s(n.cover)}{tag}")
        for c in g.children(u):
            rec(c, depth + 1)
    rec(g.root, 0)


def show_h(h: Hypergraph) -> None:
    print("   " + "  ".join(f"{e}={s(vs)}" for e, vs in sorted(h.edges.items())))


# ---------------------------------------------------------------------------------------- part 1
def part1() -> None:
    banner("PART 1  Paper Examples 4.3 / 5.2: delete constraint w7 from H_P2 (Fig. 6a)")
    h, g = Hypergraph(H_P2), GHD.from_spec(G2_SPEC)
    print(" Hypergraph H (named edges):")
    show_h(h)
    print(f" Old GHD of width {g.width()} (Fig. 6a); the exact oracle says ghw(H) = {exact_ghw(h)[0]}:")
    show_tree(g)

    mod = DelConstr("w7")
    change = mod.apply(h)
    print(f"\n Modification delta = {change.description}")
    print(" delta(H):")
    show_h(change.new)

    print("\n Step 1  Algorithm 2: peel leaves while the outside part is untouched by delta")
    res = minimal_mutable_subtree(change, g)
    for st in res.steps:
        verdict = "removed" if st.accepted else "kept   "
        why = "outside part unchanged" if st.induced_equal else "outside part would change"
        print(f"   round {st.round}: leaf {name(g, st.leaf):3s} {verdict} ({why}; "
              f"outside vertices {s(st.outside_vertices)})")
    t_star = res.t_star
    print(f"   => minimal delta-mutable subtree T* = {s(name(g, u) for u in t_star)}"
          "   (paper: {u1,u2})")

    print("\n Step 2  Algorithms 3-4: scenes = old nodes that may be reused for a sub-problem")
    sigma, events = scene_create(change, g, t_star)
    for key, entry in sigma.items():
        print(f"   scene {s(key):22s} -> {name(g, entry.node)} ({entry.kind.value}-scene)")
    for e in events:
        if e.line == "A3:L3":
            print(f"   rejected {name(g, e.node)} at Alg 3 line 3: {e.detail}")

    print("\n Step 3  Algorithm 5 (DecompUpdate) through the full pipeline, PAPER strategy")
    t0 = time.perf_counter()
    r = ghd_update(h, g, mod, strategy=Strategy.PAPER, verify_minimality=True)
    dt = time.perf_counter() - t0
    reused = {g.node(u).label for u in r.trace.reused_nodes}
    marks = {u: "reused" for u in r.ghd.node_ids() if r.ghd.node(u).label in reused}
    print(f"   status={r.status.value}  width={r.width}  k={r.k}  input minimality={r.minimality.value}"
          f"  decomposer calls={len(r.trace.decomposer_calls)}  time={dt * 1000:.1f} ms")
    show_tree(r.ghd, marks)
    rep = validate(change.new, r.ghd)
    print(f"   independent validator: ok={rep.ok}, width={rep.width};"
          f" normal form: {check_normal_form(change.new, r.ghd).ok}")


# ---------------------------------------------------------------------------------------- part 2
def part2() -> None:
    banner("PART 2  Every modification class x every strategy, checked against the exact oracle")
    h = Hypergraph({"e1": "abc", "e2": "cde", "e3": "efa", "e4": "bdf", "e5": "fg", "e6": "gh"})
    k, g, _ = ghw_by_search(h, DecomposerMode.EXACT)
    print(f" H (ghw {k}):")
    show_h(h)
    mods = [AddVar("x", frozenset({"e1", "e5"})), DelVar("g"), AddConstr("f1", frozenset("ah")),
            DelConstr("e4"), AddEq(frozenset("bd"), "b"),
            DelEq("f", {"f": frozenset({"e3", "e4"}), "f2": frozenset({"e5"})})]
    print(f"\n {'modification':44s} {'oracle':>6s} | {'PAPER':^17s} | {'THEOREM45':^17s} | {'RECOMPUTE':^17s}")
    for mod in mods:
        new = mod.apply(h).new
        truth = exact_ghw(new)[0]
        cells = []
        for strategy in Strategy:
            t0 = time.perf_counter()
            r = ghd_update(h, g, mod, strategy=strategy, delvar_fast_path=False)
            ms = (time.perf_counter() - t0) * 1000
            agree = (r.status is UpdateStatus.UPDATED) == (truth <= k)
            if r.status is UpdateStatus.UPDATED:
                assert validate(new, r.ghd).ok
            cells.append(f"{r.status.value[:7]:7s} {ms:5.1f}ms {'ok' if agree else 'BAD'}")
        desc = mod.apply(h).description[:44]
        print(f" {desc:44s} {'ghw ' + str(truth):>6s} | " + " | ".join(cells))
    print(f"\n 'updated' = a validated GHD of width <= k={k}; 'proven_' = PROVEN_NO (ghw rose above k).")


# ---------------------------------------------------------------------------------------- part 3
def part3() -> None:
    banner("PART 3  A correct NO, and the A21 issue in the paper's Algorithm 5")
    h = Hypergraph({"w0": "ce", "w1": "df", "w2": "cf"})
    g = GHD.from_spec({"root": "n0", "nodes": {"n0": ("ce", ("w0",)), "n1": ("cf", ("w2",)),
                                               "n2": ("df", ("w1",))},
                       "children": {"n0": ["n1"], "n1": ["n2"]}})
    mod = AddConstr("wnew", frozenset("def"))
    print(" H is the path c-e / c-f / d-f with a width-1 GHD:")
    show_tree(g)
    print(f" delta = AddConstr {{d,e,f}} closes a cycle: oracle ghw(delta(H)) = {exact_ghw(mod.apply(h).new)[0]}")
    r = ghd_update(h, g, mod)
    print(f" With the interface check (our default):  status = {r.status.value}  (correct: no GHD of width 1)")
    try:
        ghd_update(h, g, mod, semantics=Semantics(scene_interface_check=False))
        print(" Literal Algorithm 5: returned a result (unexpected)")
    except InvalidGHDError as exc:
        print(" Literal Algorithm 5 (no interface check): it built a width-1 'GHD' and the")
        print(f" independent validator refused it -> {str(exc)[:70]}...")
        print(" Without the validator this would have been a wrong YES. Ledger entry L-A21.")


if __name__ == "__main__":
    part1()
    part2()
    part3()
    print("\nDone.")

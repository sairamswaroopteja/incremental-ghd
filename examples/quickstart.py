"""Quickstart: decompose a hypergraph exactly, then update the GHD through a chain of modifications.

Run from the project root:   python examples/quickstart.py
(pyproject puts src/ on the test path only; this script adds it itself.)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from ighd.common import DecomposerMode, UpdateStatus  # noqa: E402
from ighd.ghd import validate  # noqa: E402
from ighd.hypergraph import Hypergraph  # noqa: E402
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq  # noqa: E402
from ighd.oracle import exact_ghw  # noqa: E402
from ighd.static import ghw_by_search  # noqa: E402
from ighd.update import Strategy, ghd_update  # noqa: E402


def main() -> list[tuple[str, str, int | None]]:
    # A 4-cycle a-b-c-d-a plus a pendant edge: ghw 2.
    h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd", "e4": "da", "e5": "dx"})
    k, ghd, _ = ghw_by_search(h, DecomposerMode.EXACT)      # EXACT: k is ghw(H) (Theorem E)
    print(f"start: ghw = {k}, GHD = {ghd!r}")

    steps = [
        AddVar("y", frozenset({"e1", "e3"})),     # new vertex y in e1 and e3
        AddConstr("f", frozenset("bd")),          # chord b-d
        DelConstr("e5"),                          # drop the pendant edge
        AddEq(frozenset("ac"), "a"),              # merge c into a
        DelEq("a", {"a": frozenset({"e1"}), "a2": frozenset({"e2", "e3", "e4"})}),  # split a again
    ]
    log = []
    for mod in steps:
        r = ghd_update(h, ghd, mod, strategy=Strategy.PAPER, delvar_fast_path=False,
                       verify_minimality=True)
        new = mod.apply(h).new
        truth = exact_ghw(new)[0]
        reused = len(r.trace.reused_nodes)
        print(f"{type(mod).__name__:10s} -> {r.status.value:9s} width={r.width} k={r.k} "
              f"oracle ghw={truth} reused old nodes={reused} minimality={r.minimality.value}")
        log.append((type(mod).__name__, r.status.value, r.width))
        if r.status is UpdateStatus.UPDATED:
            assert validate(new, r.ghd).ok
            h, ghd = new, r.ghd
        else:                                     # PROVEN_NO: ghw rose above k; start afresh
            h = new
            k, ghd, _ = ghw_by_search(h, DecomposerMode.EXACT)
            print(f"           restart from a fresh minimal GHD, ghw = {k}")
    return log


if __name__ == "__main__":
    main()

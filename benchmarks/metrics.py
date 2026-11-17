"""Table 1-style metrics (paper §6) from per-run records.

A *pair* is one (instance, modification, decomposer mode) with one Update record and one Classic
record. Definitions (per modification class and overall; EXACT and HEURISTIC never mixed):

  answer         "yes" for UPDATED, "no" for PROVEN_NO, none otherwise (NOT_FOUND, TIMEOUT,
                 MEMOUT, ERROR). Only a definite answer counts.
  Positive %     per system: yes / (yes + no) over its definite answers. "agreed": the answer of
                 whichever system answered (both, if both did and agree), yes / pairs with an
                 agreed answer. A pair where one says yes and the other PROVEN_NO is a
                 DISAGREEMENT (a correctness bug) and is counted and listed, never averaged away.
  finished       status in {UPDATED, PROVEN_NO, NOT_FOUND}: the run ended within the time limit.
  Better %       over pairs where BOTH finished: % with Update wall time < Classic wall time.
  GM times       geometric means of each system's wall time over pairs where both finished.
  GM speed-up    geometric mean of Classic/Update over the same pairs (> 1: Update faster).
  Timeouts (A24) exclusive: pairs where only that system timed out; total: all its timeouts.
  Filter         the paper's "Classic takes more than 15 ms" subset: pairs whose Classic wall time
                 (whatever its status) exceeds ``filter_ms``.

Times are floored at 1 µs before taking logarithms.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable

FINISHED = frozenset({"UPDATED", "PROVEN_NO", "NOT_FOUND"})
ANSWER = {"UPDATED": "yes", "PROVEN_NO": "no"}
EPS = 1e-6


def geomean(xs: Iterable[float]) -> float | None:
    xs = [max(float(x), EPS) for x in xs]
    if not xs:
        return None
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def pair_runs(records: Iterable[dict]) -> list[dict]:
    """Group run records into pairs {key fields, "update": rec, "classic": rec}.

    Records must carry instance, mod_class, mod_index, mode, system. A pair with a missing side is
    kept with that side None (it is reported as incomplete, not dropped)."""
    groups: dict[tuple, dict] = {}
    for r in records:
        key = (r["instance"], r["mod_class"], r["mod_index"], r["mode"])
        g = groups.setdefault(key, {"instance": r["instance"], "mod_class": r["mod_class"],
                                    "mod_index": r["mod_index"], "mode": r["mode"],
                                    "update": None, "classic": None})
        if g[r["system"]] is not None:
            raise ValueError(f"duplicate {r['system']} record for {key}")
        g[r["system"]] = r
        for f in ("k", "n_vertices", "n_edges", "family"):
            if f in r:
                g.setdefault(f, r[f])
    return list(groups.values())


def summarize(pairs: list[dict]) -> dict:
    """The metric row of one group of pairs (see module docstring)."""
    row: dict = {"pairs": len(pairs)}
    complete = [p for p in pairs if p["update"] is not None and p["classic"] is not None]
    row["incomplete"] = len(pairs) - len(complete)
    for side, tag in (("update", "U"), ("classic", "C")):
        st = [p[side]["status"] for p in complete]
        yes, no = st.count("UPDATED"), st.count("PROVEN_NO")
        row[f"yes_{tag}"], row[f"no_{tag}"] = yes, no
        row[f"pos_{tag}"] = 100.0 * yes / (yes + no) if yes + no else None
        row[f"notfound_{tag}"] = st.count("NOT_FOUND")
        row[f"to_total_{tag}"] = st.count("TIMEOUT")
        row[f"memout_{tag}"] = st.count("MEMOUT")
        row[f"error_{tag}"] = st.count("ERROR")
    agreed_yes = agreed = 0
    disagreements = []
    for p in complete:
        a, b = ANSWER.get(p["update"]["status"]), ANSWER.get(p["classic"]["status"])
        if a and b and a != b:
            disagreements.append(p)
            continue
        ans = a or b
        if ans:
            agreed += 1
            agreed_yes += ans == "yes"
    row["agreed"] = agreed
    row["pos_agreed"] = 100.0 * agreed_yes / agreed if agreed else None
    row["unresolved"] = sum(1 for p in complete if not ANSWER.get(p["update"]["status"])
                            and not ANSWER.get(p["classic"]["status"]))
    row["disagreements"] = len(disagreements)
    row["disagreement_keys"] = [(p["instance"], p["mod_class"], p["mod_index"], p["mode"],
                                 p["update"]["status"], p["classic"]["status"]) for p in disagreements]
    both = [p for p in complete if p["update"]["status"] in FINISHED and p["classic"]["status"] in FINISHED]
    row["both_finished"] = len(both)
    tu = [p["update"]["wall_s"] for p in both]
    tc = [p["classic"]["wall_s"] for p in both]
    row["better_pct"] = (100.0 * sum(1 for u, c in zip(tu, tc) if u < c) / len(both)) if both else None
    row["gm_U"] = geomean(tu)
    row["gm_C"] = geomean(tc)
    row["gm_speedup"] = geomean(max(c, EPS) / max(u, EPS) for u, c in zip(tu, tc)) if both else None
    row["to_excl_U"] = sum(1 for p in complete if p["update"]["status"] == "TIMEOUT"
                           and p["classic"]["status"] != "TIMEOUT")
    row["to_excl_C"] = sum(1 for p in complete if p["classic"]["status"] == "TIMEOUT"
                           and p["update"]["status"] != "TIMEOUT")
    nf = [p["update"]["out_nf"] for p in complete if p["update"]["status"] == "UPDATED"]
    row["update_out_nf"] = sum(1 for x in nf if x)
    row["update_out_not_nf"] = sum(1 for x in nf if x is False)
    reused = [p["update"].get("reused_nodes") or 0 for p in complete if p["update"]["status"] == "UPDATED"]
    row["mean_reused_U"] = sum(reused) / len(reused) if reused else None
    calls = [p["update"].get("decomposer_calls") or 0 for p in complete
             if p["update"]["status"] in FINISHED]
    row["mean_calls_U"] = sum(calls) / len(calls) if calls else None
    return row


def classic_slower_than(pairs: list[dict], filter_ms: float) -> list[dict]:
    """The paper's filter: pairs whose Classic run took more than ``filter_ms`` (any status)."""
    lim = filter_ms / 1000.0
    return [p for p in pairs if p["classic"] is not None and p["classic"]["wall_s"] is not None
            and p["classic"]["wall_s"] > lim]


def table(pairs: list[dict], classes: Iterable[str]) -> dict[str, dict[str, dict]]:
    """{mode: {class or "ALL": row}}; modes are kept apart."""
    out: dict[str, dict[str, dict]] = {}
    by_mode: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_mode[p["mode"]].append(p)
    for mode, ps in sorted(by_mode.items()):
        rows = {}
        for cls in classes:
            sub = [p for p in ps if p["mod_class"] == cls]
            if sub:
                rows[cls] = summarize(sub)
        rows["ALL"] = summarize(ps)
        out[mode] = rows
    return out

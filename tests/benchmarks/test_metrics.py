"""S14: Table 1 metrics on a hand-made record set."""

from __future__ import annotations

import math

import pytest

from benchmarks.metrics import classic_slower_than, geomean, pair_runs, summarize, table


def rec(i: int, system: str, status: str, t: float, cls: str = "AddVar", mode: str = "exact") -> dict:
    return {"instance": f"h{i}", "mod_class": cls, "mod_index": 0, "mode": mode, "system": system,
            "status": status, "wall_s": t, "out_nf": True if status == "UPDATED" else None,
            "reused_nodes": 2, "decomposer_calls": 1, "k": 1, "n_vertices": 5, "n_edges": 4}


def pairs_of(rows):
    out = []
    for i, (su, tu, sc, tc) in enumerate(rows):
        out += [rec(i, "update", su, tu), rec(i, "classic", sc, tc)]
    return pair_runs(out)


ROWS = [
    ("UPDATED", 0.010, "UPDATED", 0.040),     # 0: both yes, Update 4x faster
    ("UPDATED", 0.020, "UPDATED", 0.010),     # 1: both yes, Classic 2x faster
    ("PROVEN_NO", 0.005, "PROVEN_NO", 0.020), # 2: both no, Update 4x faster
    ("TIMEOUT", 10.0, "UPDATED", 0.500),      # 3: only Update timed out -> agreed yes
    ("UPDATED", 0.100, "TIMEOUT", 10.0),      # 4: only Classic timed out -> agreed yes
    ("TIMEOUT", 10.0, "TIMEOUT", 10.0),       # 5: both timed out -> unresolved
    ("ERROR", 0.001, "UPDATED", 0.012),       # 6: Update error
]


def test_geomean() -> None:
    assert geomean([1.0, 100.0]) == pytest.approx(10.0)
    assert geomean([]) is None
    assert geomean([0.0]) == pytest.approx(1e-6)      # floored, never log(0)


def test_summary_row() -> None:
    row = summarize(pairs_of(ROWS))
    assert row["pairs"] == 7 and row["incomplete"] == 0
    # both finished: pairs 0, 1, 2
    assert row["both_finished"] == 3
    assert row["better_pct"] == pytest.approx(100 * 2 / 3)
    assert row["gm_U"] == pytest.approx((0.010 * 0.020 * 0.005) ** (1 / 3))
    assert row["gm_C"] == pytest.approx((0.040 * 0.010 * 0.020) ** (1 / 3))
    assert row["gm_speedup"] == pytest.approx((4 * 0.5 * 4) ** (1 / 3))
    # timeouts both ways (A24)
    assert (row["to_excl_U"], row["to_excl_C"]) == (1, 1)
    assert (row["to_total_U"], row["to_total_C"]) == (2, 2)
    assert (row["error_U"], row["error_C"]) == (1, 0)
    # Positive %: per system over definite answers, and the agreed answer
    assert (row["yes_U"], row["no_U"]) == (3, 1) and row["pos_U"] == pytest.approx(75.0)
    assert (row["yes_C"], row["no_C"]) == (4, 1) and row["pos_C"] == pytest.approx(80.0)
    assert row["agreed"] == 6 and row["pos_agreed"] == pytest.approx(100 * 5 / 6)
    assert row["unresolved"] == 1 and row["disagreements"] == 0


def test_disagreement_is_counted_not_averaged() -> None:
    row = summarize(pairs_of([("UPDATED", 0.01, "PROVEN_NO", 0.01), ("UPDATED", 0.01, "UPDATED", 0.02)]))
    assert row["disagreements"] == 1
    assert row["disagreement_keys"][0][4:] == ("UPDATED", "PROVEN_NO")
    assert row["agreed"] == 1                         # the disagreeing pair has no agreed answer


def test_classic_15ms_filter() -> None:
    ps = pairs_of(ROWS)
    kept = classic_slower_than(ps, 15.0)
    # Classic times: 40, 10, 20, 500, 10000, 10000, 12 ms -> keep 0, 2, 3, 4, 5
    assert sorted(p["instance"] for p in kept) == ["h0", "h2", "h3", "h4", "h5"]
    row = summarize(kept)
    assert row["both_finished"] == 2 and row["better_pct"] == pytest.approx(100.0)


def test_modes_never_mixed_and_classes_split() -> None:
    recs = [rec(0, "update", "UPDATED", 0.01), rec(0, "classic", "UPDATED", 0.02),
            rec(1, "update", "UPDATED", 0.01, cls="DelEq"), rec(1, "classic", "UPDATED", 0.02, cls="DelEq"),
            rec(0, "update", "NOT_FOUND", 0.01, mode="heuristic"),
            rec(0, "classic", "UPDATED", 0.02, mode="heuristic")]
    t = table(pair_runs(recs), ["AddVar", "DelEq"])
    assert set(t) == {"exact", "heuristic"}
    assert t["exact"]["ALL"]["pairs"] == 2 and t["heuristic"]["ALL"]["pairs"] == 1
    assert set(t["exact"]) == {"AddVar", "DelEq", "ALL"}
    assert t["heuristic"]["ALL"]["notfound_U"] == 1
    # a heuristic NOT_FOUND is "finished" but not an answer
    assert t["heuristic"]["ALL"]["both_finished"] == 1 and t["heuristic"]["ALL"]["yes_U"] == 0


def test_duplicate_record_rejected_and_incomplete_pair_kept() -> None:
    with pytest.raises(ValueError):
        pair_runs([rec(0, "update", "UPDATED", 0.1), rec(0, "update", "UPDATED", 0.1)])
    row = summarize(pair_runs([rec(0, "update", "UPDATED", 0.1)]))
    assert row["pairs"] == 1 and row["incomplete"] == 1 and row["both_finished"] == 0
    assert math.isclose(row["pos_agreed"] or 0.0, 0.0)

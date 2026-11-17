"""S14: the runner end to end on tiny instances, the pool's hard limits, and the rule that a
timeout is never reported as PROVEN_NO."""

from __future__ import annotations

import json

import pytest

from ighd.common import DecomposerMode
from ighd.hypergraph import Hypergraph, to_hyperbench
from ighd.static import ghw_by_search

from benchmarks.generator import to_spec
from benchmarks.pool import HardPool, Task
from benchmarks.runner import Config, _killed_record, run
from benchmarks.worker import run_task
from ighd.modifications import AddConstr

TINY = {
    "path3.hg": Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd"}),                 # ghw 1
    "cycle4.hg": Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd", "e4": "da"}),    # ghw 2
    "star.hg": Hypergraph({"r1": "xab", "r2": "xc", "r3": "xd"}),                 # ghw 1
}


@pytest.fixture()
def data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    for name, h in TINY.items():
        (d / name).write_text(to_hyperbench(h), encoding="utf-8")
    return d


def test_runner_end_to_end(tmp_path, data_dir) -> None:
    cfg = Config(run_id="t", seed=1, per_class=1, timeout=2.0, prep_timeout=5.0, jobs=2,
                 data_dir=str(data_dir), results_dir=str(tmp_path / "res"), quiet=True)
    out = run(cfg)
    preps = [json.loads(x) for x in (out / "instances.jsonl").read_text().splitlines()]
    assert {p["instance"]: (p["k"], p["cert"]) for p in preps} == {
        "path3.hg": (1, "oracle"), "cycle4.hg": (2, "oracle"), "star.hg": (1, "oracle")}
    recs = [json.loads(x) for x in (out / "runs.jsonl").read_text().splitlines()]
    mods = [json.loads(x) for x in (out / "mods.jsonl").read_text().splitlines()]
    generated = [m for m in mods if m["spec"] is not None]
    assert len(recs) == 2 * len(generated) and len(mods) == 3 * 5
    assert {r["status"] for r in recs} <= {"UPDATED", "PROVEN_NO"}
    assert all(r["harness_valid"] for r in recs if r["status"] == "UPDATED")
    assert all(r["mode"] == "exact" and r["minimality"] == "verified" for r in recs)
    # Update and Classic agree on every pair
    ans = {}
    for r in recs:
        ans.setdefault((r["instance"], r["mod_class"], r["mod_index"]), set()).add(r["status"])
    assert all(len(s) == 1 for s in ans.values())
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "disagreements: 0**" in summary and "Classic > 15 ms" in summary
    assert (out / "plots" / "fig7_exact.png").stat().st_size > 0
    manifest = json.loads((out / "manifest.json").read_text())
    assert len(manifest["code_sha256"]) == 64 and manifest["config"]["seed"] == 1
    assert (out / "runs.csv").read_text().count("\n") == len(recs) + 1


def _proven_no_case():
    h = TINY["path3.hg"]
    k, ghd, _ = ghw_by_search(h, DecomposerMode.EXACT)
    assert k == 1
    mod = AddConstr("new", frozenset({"a", "d"}))      # closes a 4-cycle: ghw 2 > k
    return {"path": None, "instance": "path3", "ghd": ghd, "k": 1, "mod": to_spec(mod), "mode": "exact"}


@pytest.mark.parametrize("system", ["update", "classic"])
def test_timeout_is_never_reported_as_proven_no(tmp_path, monkeypatch, system) -> None:
    import benchmarks.worker as w
    p = _proven_no_case()
    monkeypatch.setitem(w._CACHE, "path3", TINY["path3.hg"])
    p["path"] = "path3"
    # with enough time the answer is PROVEN_NO ...
    assert run_task(dict(p, system=system, timeout=30.0))["status"] == "PROVEN_NO"
    # ... with an (absurdly) small limit the budget cuts the search: TIMEOUT, never PROVEN_NO
    r = run_task(dict(p, system=system, timeout=1e-9))
    assert r["status"] == "TIMEOUT" and r["raw_status"] == "NOT_FOUND"
    assert r["timeout_reason"] == "budget"


def test_killed_records_are_timeouts_or_memouts() -> None:
    assert _killed_record({"_killed": "TIMEOUT"}, 3.0)["status"] == "TIMEOUT"
    assert _killed_record({"_killed": "MEMOUT"}, 3.0)["status"] == "MEMOUT"
    assert _killed_record({"_died": 3}, 3.0)["status"] == "ERROR"


def test_pool_hard_deadline_and_memory_watchdog() -> None:
    results = {}
    pool = HardPool(jobs=2, mem_cap_mb=150, poll_s=0.02)
    pool.run([Task("ok", "sleep_task", {"s": 0.05}, 20.0),
              Task("hang", "sleep_task", {"s": 60}, 1.0),
              Task("big", "alloc_task", {"mb": 400, "s": 30}, 25.0),
              Task("after", "sleep_task", {"s": 0.01}, 20.0)],
             lambda t, res, el, rss: results.__setitem__(t.tid, (res, el)))
    assert results["ok"][0] == {"slept": 0.05}
    assert results["hang"][0] == {"_killed": "TIMEOUT"} and results["hang"][1] < 10
    assert results["big"][0] == {"_killed": "MEMOUT"}
    assert results["after"][0] == {"slept": 0.01}             # the pool recovers after kills
    assert pool.kills["TIMEOUT"] == 1 and pool.kills["MEMOUT"] == 1

"""Task functions executed inside worker processes (also callable in-process, e.g. by tests).

``prep_task``  establishes the width bound k and a minimum-width, normal-form input GHD for one
               instance and generates its §6.1 modifications.
``run_task``   runs ONE system (Update = Strategy.PAPER, Classic = Strategy.RECOMPUTE) on one
               (instance, modification) pair and classifies the outcome.

Status vocabulary of a run record (the harness's, a superset of ``UpdateStatus``):
  UPDATED    a GHD of delta(H) of width <= k, validated by the pipeline AND re-validated here;
  PROVEN_NO  ghw(delta(H)) > k established by an exhaustive EXACT search (pipeline invariant I10);
  NOT_FOUND  the search ended without an answer within the time limit (HEURISTIC failure);
  TIMEOUT    no answer within the time limit: the Budget ran out (raw NOT_FOUND), the answer
             arrived after the limit (``raw_status`` keeps it), or the pool killed the worker;
  MEMOUT     the pool's RSS watchdog killed the worker, or MemoryError;
  ERROR      an exception (``error`` has the message), or a harness re-validation failure.
A TIMEOUT is never turned into PROVEN_NO: any run whose wall time exceeds the limit is TIMEOUT.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path

from ighd.common import Budget, DecomposerMode, UpdateStatus
from ighd.common.errors import InvalidGHDError
from ighd.ghd import GHD, check_normal_form, validate
from ighd.oracle import MAX_ORACLE_VERTICES, exact_ghw
from ighd.static import DecompositionTask, TopDownDecomposer, ghw_by_search
from ighd.common.types import SearchStatus
from ighd.update import Strategy, ghd_update

from benchmarks.generator import PAPER_CLASSES, from_spec, generate
from benchmarks.loader import instance_info, load

SYSTEMS = {"update": Strategy.PAPER, "classic": Strategy.RECOMPUTE}
_CACHE: dict[str, object] = {}


def _hypergraph(path: str):
    """Parse once per worker process (the pool reuses workers across tasks)."""
    h = _CACHE.get(path)
    if h is None:
        if len(_CACHE) > 64:
            _CACHE.clear()
        h = _CACHE[path] = load(path)
    return h


# ---------------------------------------------------------------------------- preparation
def prep_task(p: dict) -> dict:
    """Payload: path, prep_timeout, seed, per_class, classes, oracle_max_vertices.

    Certification of k (never claim optimality without one):
      oracle        |V| <= oracle_max_vertices and exact_ghw(H) == k (the same check as
                    ghd_update(verify_minimality=True)); if the EXACT search was cut by the budget
                    the input GHD comes from an EXACT search at k = exact_ghw(H) alone;
      exact-search  ghw_by_search(EXACT) found k and refuted every k' < k without hitting the budget;
      unknown       neither: the instance is excluded from the main table.
    A mismatch between oracle and search is reported as cert ``ERROR`` (a finding).
    """
    path = p["path"]
    h = _hypergraph(path)
    info = instance_info(Path(path), h)
    out: dict = {"instance": info.name, **info.to_dict(), "k": None, "cert": "unknown",
                 "minimality": "assumed", "search_k": None, "search_s": None, "oracle_ghw": None,
                 "oracle_s": None, "input_nodes": None, "input_nf": None, "ghd": None,
                 "ghd_spec": None, "mods": [], "note": ""}
    t = time.perf_counter()
    k, ghd, _ = ghw_by_search(h, DecomposerMode.EXACT, Budget(time_limit_s=p["prep_timeout"]).start())
    out["search_s"] = time.perf_counter() - t
    out["search_k"] = k
    if len(h.vertices) <= min(p.get("oracle_max_vertices", MAX_ORACLE_VERTICES), MAX_ORACLE_VERTICES):
        t = time.perf_counter()
        ghw, _ = exact_ghw(h)
        out["oracle_s"] = time.perf_counter() - t
        out["oracle_ghw"] = ghw
        if k is not None and k != ghw:
            out["cert"] = "ERROR"
            out["note"] = f"FINDING: EXACT search ghw {k} != oracle ghw {ghw}"
            return out
        if k is None:
            res = TopDownDecomposer(DecomposerMode.EXACT).decompose(
                DecompositionTask(h, ghw), budget=Budget(time_limit_s=p["prep_timeout"]).start())
            if res.status is SearchStatus.FOUND:
                k, ghd = ghw, res.ghd
                out["note"] = "EXACT search for ghw cut by budget; oracle ghw used, GHD from search at k"
            else:
                out["note"] = (f"oracle ghw {ghw}, but no normal-form GHD of that width found "
                               f"within the budget ({res.status.value})")
                return out
        out["cert"] = "oracle"
        out["minimality"] = "verified"
    elif k is not None:
        out["cert"] = "exact-search"
    else:
        out["note"] = "EXACT search for ghw cut by the prep budget"
        return out
    assert ghd is not None and k is not None
    rep = validate(h, ghd)
    if not rep.ok or rep.width != k:
        out["cert"] = "ERROR"
        out["note"] = f"FINDING: input GHD invalid or of width {rep.width} != {k}"
        return out
    out["k"] = k
    out["ghd"] = ghd
    out["ghd_spec"] = ghd.to_spec() if len(ghd) else None
    out["input_nodes"] = len(ghd)
    out["input_nf"] = check_normal_form(h, ghd).ok
    classes = tuple(p.get("classes", PAPER_CLASSES))
    out["mods"] = [m.to_dict() for m in generate(h, info, p["seed"], p["per_class"], classes)]
    return out


# ---------------------------------------------------------------------------- pool self-tests
def sleep_task(p: dict) -> dict:
    """Test helper for the pool's hard deadline: sleeps ``p["s"]`` seconds."""
    time.sleep(float(p["s"]))
    return {"slept": p["s"]}


def alloc_task(p: dict) -> dict:
    """Test helper for the RSS watchdog: holds ``p["mb"]`` MB (touched) for ``p["s"]`` seconds."""
    block = bytearray(int(p["mb"]) * 2**20)
    for i in range(0, len(block), 4096):
        block[i] = 1
    time.sleep(float(p.get("s", 5)))
    return {"held_mb": p["mb"], "n": len(block)}


# ---------------------------------------------------------------------------- one run
def run_task(p: dict) -> dict:
    """Payload: path, instance, ghd (GHD), k, mod (spec), system, mode, timeout."""
    path, k, timeout = p["path"], p["k"], float(p["timeout"])
    system, mode = p["system"], DecomposerMode(p["mode"])
    h = _hypergraph(path)
    mod = from_spec(p["mod"])
    ghd: GHD = p["ghd"]
    expected_new = mod.apply(h).new           # independent of the pipeline, outside the timing
    rec = {"status": None, "raw_status": None, "timeout_reason": None, "wall_s": None,
           "budget_s": None, "decomposer_calls": None, "expansions": None, "reused_nodes": None,
           "new_nodes": None, "out_width": None, "out_nf": None, "harness_valid": None,
           "minimality": None, "error": None}
    budget = Budget(time_limit_s=timeout)
    decomposer = TopDownDecomposer(mode)
    budget.start()
    t0 = time.perf_counter()
    try:
        r = ghd_update(h, ghd, mod, k=k, strategy=SYSTEMS[system], decomposer=decomposer,
                       budget=budget)
    except MemoryError:
        rec.update(status="MEMOUT", wall_s=time.perf_counter() - t0, error="MemoryError")
        return rec
    except InvalidGHDError as exc:
        rec.update(status="ERROR", wall_s=time.perf_counter() - t0, harness_valid=False,
                   error=f"FINDING: pipeline InvalidGHDError: {exc}")
        return rec
    except Exception as exc:  # noqa: BLE001 - every failure becomes a recorded ERROR
        rec.update(status="ERROR", wall_s=time.perf_counter() - t0,
                   error=f"{type(exc).__name__}: {exc} | {traceback.format_exc(limit=3)[-600:]}")
        return rec
    wall = time.perf_counter() - t0
    calls = r.trace.decomposer_calls
    rec.update(raw_status=r.status.name, wall_s=wall, budget_s=budget.elapsed_s,
               decomposer_calls=len(calls),
               expansions=sum(int(c.get("expansions", 0) or 0) for c in calls),
               reused_nodes=len(r.trace.reused_nodes), new_nodes=len(r.trace.new_nodes),
               minimality=r.minimality.value)
    for note in r.trace.notes:
        if note.startswith("output in normal form:"):
            rec["out_nf"] = note.endswith("yes")
    if r.status is UpdateStatus.UPDATED:
        assert r.ghd is not None
        rep = validate(expected_new, r.ghd)
        rec["out_width"] = rep.width
        rec["harness_valid"] = rep.ok and rep.width <= k
        if not rec["harness_valid"]:
            rec.update(status="ERROR", error="FINDING: harness re-validation failed: "
                       f"width {rep.width}, k {k}, {[v.describe() for v in rep.violations][:5]}")
            return rec
    if wall > timeout:
        rec["status"] = "TIMEOUT"
        rec["timeout_reason"] = ("budget" if r.status is UpdateStatus.NOT_FOUND
                                 else "answer after the time limit")
    else:
        rec["status"] = r.status.name
    return rec

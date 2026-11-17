"""Orchestration of one benchmark run: select -> prepare (k + input GHD + modifications) -> run
Update and Classic on every (instance, modification, mode) -> records, metrics, report, plots.

Everything that executes solver code runs in ``pool.HardPool`` workers (hard deadline + sampled
RSS watchdog). Outputs go to ``<results>/<run-id>/`` (see README).
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import random
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import psutil

from benchmarks import DATA_DIR, PROJECT_ROOT, RESULTS_DIR
from benchmarks.generator import PAPER_CLASSES
from benchmarks.loader import InstanceInfo, enumerate_instances
from benchmarks.pool import HardPool, Task

RUN_FIELDS = [
    "instance", "family", "n_vertices", "n_edges", "rank", "avg_degree", "avg_rank", "k", "cert",
    "minimality", "mod_class", "mod_index", "mod_desc", "mod_spec", "redraws",
    "creates_duplicate_edges", "system", "strategy", "mode", "timeout_s", "status", "raw_status",
    "timeout_reason", "wall_s", "budget_s", "decomposer_calls", "expansions", "reused_nodes",
    "new_nodes", "input_nodes", "out_width", "out_nf", "harness_valid", "rss_peak_mb", "error",
]
STRATEGY_NAME = {"update": "paper", "classic": "recompute"}


@dataclass
class Config:
    run_id: str
    seed: int = 0
    per_class: int = 5
    timeout: float = 10.0            # per run (Update or Classic), Budget + hard kill
    prep_timeout: float = 20.0       # EXACT ghw search per instance
    jobs: int = 4
    mem_cap_mb: float | None = 1024.0
    modes: tuple[str, ...] = ("exact",)
    classes: tuple[str, ...] = PAPER_CLASSES
    families: tuple[str, ...] | None = None
    names: tuple[str, ...] | None = None
    min_vertices: int = 0
    max_vertices: int | None = None
    max_edges: int | None = None
    limit: int | None = None
    filter_ms: float = 15.0
    oracle_max_vertices: int = 16
    preset: str | None = None
    data_dir: str = str(DATA_DIR)
    results_dir: str = str(RESULTS_DIR)
    quiet: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def run_dir(self) -> Path:
        return Path(self.results_dir) / self.run_id

    def run_hard_deadline(self) -> float:
        return 2 * self.timeout + 10

    def prep_hard_deadline(self) -> float:
        return 3 * self.prep_timeout + 60


# ---------------------------------------------------------------------------- selection
def select(cfg: Config) -> list[InstanceInfo]:
    """Filtered instances; with ``limit``, a seeded family-stratified sample (round-robin over
    families, each family shuffled with the seed), so small presets cover many families."""
    cache = Path(cfg.results_dir) / "_cache" / "instance_index.json"
    xs = enumerate_instances(cfg.data_dir, families=list(cfg.families) if cfg.families else None,
                             min_vertices=cfg.min_vertices, max_vertices=cfg.max_vertices,
                             max_edges=cfg.max_edges, names=list(cfg.names) if cfg.names else None,
                             cache_file=cache)
    if cfg.limit is None or cfg.limit >= len(xs):
        return xs
    rng = random.Random(f"ighd-bench-select|{cfg.seed}")
    fams: dict[str, list[InstanceInfo]] = {}
    for x in xs:
        fams.setdefault(x.family, []).append(x)
    queues = []
    for f in sorted(fams):
        q = list(fams[f])
        rng.shuffle(q)
        queues.append(q)
    out: list[InstanceInfo] = []
    while len(out) < cfg.limit:
        for q in queues:
            if q and len(out) < cfg.limit:
                out.append(q.pop())
    return sorted(out, key=lambda x: x.name)


# ---------------------------------------------------------------------------- manifest
def code_hash() -> tuple[str, int]:
    """sha256 over src/ighd/**/*.py and benchmarks/*.py (relative path + bytes), no git needed."""
    h = hashlib.sha256()
    files = sorted(list((PROJECT_ROOT / "src" / "ighd").rglob("*.py"))
                   + list((PROJECT_ROOT / "benchmarks").glob("*.py")))
    for f in files:
        h.update(f.relative_to(PROJECT_ROOT).as_posix().encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest(), len(files)


def machine_info() -> dict:
    vers = {}
    for mod in ("matplotlib", "numpy", "pandas", "psutil"):
        try:
            vers[mod] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            vers[mod] = None
    return {"platform": platform.platform(), "processor": platform.processor(),
            "machine": platform.machine(), "cpu_physical": psutil.cpu_count(logical=False),
            "cpu_logical": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 2**30, 2),
            "python": sys.version, "executable": sys.executable, "packages": vers}


# ---------------------------------------------------------------------------- main
def _log(cfg: Config, msg: str) -> None:
    if not cfg.quiet:
        print(msg, flush=True)


def _killed_record(res: dict, elapsed: float) -> dict:
    if "_killed" in res:
        st = res["_killed"]
        return {"status": st, "wall_s": elapsed,
                "timeout_reason": "hard kill by the pool" if st == "TIMEOUT" else None,
                "error": f"worker killed by the pool ({st})"}
    if res.get("_memout"):
        return {"status": "MEMOUT", "wall_s": elapsed, "error": res.get("_error")}
    if "_died" in res:
        return {"status": "ERROR", "wall_s": elapsed, "error": f"worker process died (exit code {res['_died']})"}
    return {"status": "ERROR", "wall_s": elapsed, "error": res.get("_error", "unknown worker failure")}


def run(cfg: Config, *, overwrite: bool = False) -> Path:
    out = cfg.run_dir
    if out.exists() and any(out.iterdir()) and not overwrite:
        raise FileExistsError(f"{out} exists; pass --overwrite or another --run-id")
    out.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    instances = select(cfg)
    chash, nfiles = code_hash()
    manifest = {"run_id": cfg.run_id, "config": asdict(cfg), "code_sha256": chash,
                "code_files_hashed": nfiles, "machine": machine_info(),
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "start_method": "spawn", "instances_selected": [i.name for i in instances],
                "data_source": "HyperBench, http://hyperbench.dbai.tuwien.ac.at ('Download All')"}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _log(cfg, f"[{cfg.run_id}] {len(instances)} instances selected; preparing (EXACT ghw search, "
              f"{cfg.prep_timeout}s budget each, {cfg.jobs} workers)")

    pool = HardPool(cfg.jobs, cfg.mem_cap_mb)
    preps: dict[str, dict] = {}

    def on_prep(task: Task, res: dict, elapsed: float, rss: int) -> None:
        info: InstanceInfo = task.payload["_info"]
        if any(k in res for k in ("_killed", "_died", "_error", "_memout")):
            r = {"instance": info.name, **info.to_dict(), "k": None,
                 "cert": "killed" if "_killed" in res else "error",
                 "note": _killed_record(res, elapsed)["error"], "mods": []}
        else:
            r = res
        r["prep_wall_s"] = elapsed
        preps[info.name] = r
        if r.get("cert") == "ERROR":
            _log(cfg, f"  !!! FINDING during prep of {info.name}: {r.get('note')}")

    prep_tasks = [Task(i.name, "prep_task",
                       {"path": i.path, "prep_timeout": cfg.prep_timeout, "seed": cfg.seed,
                        "per_class": cfg.per_class, "classes": list(cfg.classes),
                        "oracle_max_vertices": cfg.oracle_max_vertices, "_info": i},
                       cfg.prep_hard_deadline()) for i in instances]
    pool.run(prep_tasks, on_prep)

    with (out / "instances.jsonl").open("w", encoding="utf-8") as f:
        for name in sorted(preps):
            r = {k: v for k, v in preps[name].items() if k not in ("ghd", "mods")}
            f.write(json.dumps(r, default=str) + "\n")
    with (out / "mods.jsonl").open("w", encoding="utf-8") as f:
        for name in sorted(preps):
            for m in preps[name].get("mods", []):
                f.write(json.dumps(m) + "\n")
    certs = Counter(p.get("cert") for p in preps.values())
    _log(cfg, f"[{cfg.run_id}] prep done: {dict(certs)}")

    # ---- runs
    tasks: list[Task] = []
    for name in sorted(preps):
        p = preps[name]
        if p.get("cert") not in ("oracle", "exact-search"):
            continue
        for m in p["mods"]:
            if m["spec"] is None:
                continue
            for mode in cfg.modes:
                order = ("update", "classic") if m["index"] % 2 == 0 else ("classic", "update")
                for system in order:
                    payload = {"path": p["path"], "instance": name, "ghd": p["ghd"], "k": p["k"],
                               "mod": m["spec"], "system": system, "mode": mode,
                               "timeout": cfg.timeout,
                               "_meta": {f: p.get(f) for f in ("instance", "family", "n_vertices", "n_edges",
                                                               "rank", "avg_degree", "avg_rank", "k",
                                                               "cert", "minimality", "input_nodes")}
                               | {"mod_class": m["mod_class"], "mod_index": m["index"],
                                  "mod_desc": m["description"], "mod_spec": json.dumps(m["spec"]),
                                  "redraws": m["redraws"],
                                  "creates_duplicate_edges": m["creates_duplicate_edges"],
                                  "system": system, "strategy": STRATEGY_NAME[system], "mode": mode,
                                  "timeout_s": cfg.timeout}}
                    tasks.append(Task((name, m["mod_class"], m["index"], mode, system), "run_task",
                                      payload, cfg.run_hard_deadline()))
    _log(cfg, f"[{cfg.run_id}] {len(tasks)} runs ({len(tasks) // 2} Update/Classic pairs), "
              f"timeout {cfg.timeout}s each")
    records: list[dict] = []
    t_runs = time.time()
    fh = (out / "runs.jsonl").open("w", encoding="utf-8")

    def on_run(task: Task, res: dict, elapsed: float, rss: int) -> None:
        rec = dict(task.payload["_meta"])
        if any(k in res for k in ("_killed", "_died", "_error", "_memout")):
            rec.update(_killed_record(res, elapsed))
        else:
            res = dict(res)
            res.pop("minimality", None)       # the prep step certifies minimality, not the timed call
            rec.update(res)
        rec["rss_peak_mb"] = round(rss / 2**20, 1)
        for f_ in RUN_FIELDS:
            rec.setdefault(f_, None)
        records.append(rec)
        fh.write(json.dumps(rec, default=str) + "\n")
        fh.flush()
        if rec["status"] == "ERROR":
            _log(cfg, f"  !!! ERROR {task.tid}: {str(rec.get('error'))[:300]}")
        n = len(records)
        if n % max(1, len(tasks) // 20) == 0 or n == len(tasks):
            el = time.time() - t_runs
            _log(cfg, f"  {n}/{len(tasks)} runs, {el:.0f}s elapsed, "
                      f"{dict(Counter(r['status'] for r in records))}")

    try:
        pool.run(tasks, on_run)
    finally:
        fh.close()
    with (out / "runs.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUN_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)

    from benchmarks.report import write_report   # noqa: PLC0415 (matplotlib only when reporting)
    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["duration_s"] = round(time.time() - t_start, 1)
    manifest["pool_kills"] = pool.kills
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary = write_report(out, cfg, list(preps.values()), records)
    _log(cfg, f"[{cfg.run_id}] done in {manifest['duration_s']}s -> {out}")
    if not cfg.quiet:
        print(summary)
    return out


def default_jobs() -> int:
    return psutil.cpu_count(logical=False) or os.cpu_count() or 1

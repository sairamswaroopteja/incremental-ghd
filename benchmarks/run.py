"""CLI: ``python -m benchmarks.run --preset smoke`` / ``--preset small --seed 0``.

Explicit options override the preset's values. See benchmarks/README.md.
"""

from __future__ import annotations

import argparse
import sys

from benchmarks.generator import ALL_CLASSES, PAPER_CLASSES
from benchmarks.runner import Config, default_jobs, run

PRESETS: dict[str, dict] = {
    # ~1 minute: a handful of tiny instances, 2 modifications per class, 2 s limit
    "smoke": dict(max_vertices=12, limit=6, per_class=2, timeout=2.0, prep_timeout=5.0),
    # the reproducible subset (README): <= 30 vertices, family-stratified sample of 200 instances
    "small": dict(max_vertices=30, limit=200, per_class=5, timeout=10.0, prep_timeout=20.0),
    # everything that passes the filters you give (no sampling); expect hours
    "full": dict(per_class=5, timeout=60.0, prep_timeout=120.0),
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m benchmarks.run", description=__doc__)
    ap.add_argument("--preset", choices=sorted(PRESETS), default="smoke")
    ap.add_argument("--subset", dest="preset_alias", choices=sorted(PRESETS), default=None,
                    help="alias of --preset")
    ap.add_argument("--run-id", default=None, help="results sub-folder (default <preset>-seed<seed>)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--per-class", type=int, default=None)
    ap.add_argument("--timeout", type=float, default=None, help="seconds per Update/Classic run")
    ap.add_argument("--prep-timeout", type=float, default=None, help="seconds for the EXACT ghw search")
    ap.add_argument("--jobs", type=int, default=None, help="parallel workers (default: physical cores)")
    ap.add_argument("--mem-cap-mb", type=float, default=1024.0, help="sampled RSS cap per worker; 0 = off")
    ap.add_argument("--modes", default="exact", help="comma list of exact,heuristic")
    ap.add_argument("--with-delvar", action="store_true", help="also generate DelVar (not in the paper's protocol)")
    ap.add_argument("--families", default=None, help="comma list of families (see loader.family_of)")
    ap.add_argument("--names", default=None, help="comma list of exact instance file names")
    ap.add_argument("--min-vertices", type=int, default=None)
    ap.add_argument("--max-vertices", type=int, default=None)
    ap.add_argument("--max-edges", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="family-stratified seeded sample size")
    ap.add_argument("--no-limit", action="store_true", help="drop the preset's sample limit")
    ap.add_argument("--filter-ms", type=float, default=15.0, help="the paper's 'Classic > 15 ms' filter")
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    return ap.parse_args(argv)


def build_config(a: argparse.Namespace) -> Config:
    preset = a.preset_alias or a.preset
    p = dict(PRESETS[preset])
    for key in ("per_class", "timeout", "prep_timeout", "min_vertices", "max_vertices", "max_edges", "limit"):
        v = getattr(a, key)
        if v is not None:
            p[key] = v
    if a.no_limit:
        p["limit"] = None
    modes = tuple(m.strip().lower() for m in a.modes.split(",") if m.strip())
    bad = [m for m in modes if m not in ("exact", "heuristic")]
    if bad:
        raise SystemExit(f"unknown mode(s) {bad}")
    kw = dict(run_id=a.run_id or f"{preset}-seed{a.seed}", seed=a.seed, preset=preset,
              jobs=a.jobs or default_jobs(), mem_cap_mb=a.mem_cap_mb or None, modes=modes,
              classes=ALL_CLASSES if a.with_delvar else PAPER_CLASSES,
              families=tuple(a.families.split(",")) if a.families else None,
              names=tuple(a.names.split(",")) if a.names else None,
              filter_ms=a.filter_ms, quiet=a.quiet, **p)
    if a.data_dir:
        kw["data_dir"] = a.data_dir
    if a.results_dir:
        kw["results_dir"] = a.results_dir
    return Config(**kw)


def main(argv: list[str] | None = None) -> int:
    cfg = build_config(parse_args(argv))
    run(cfg, overwrite=parse_args(argv).overwrite)
    return 0


if __name__ == "__main__":
    sys.exit(main())

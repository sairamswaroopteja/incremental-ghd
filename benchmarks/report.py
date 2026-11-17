"""Markdown summary (summary.md), metrics.json and the plots of one run directory."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from benchmarks.metrics import classic_slower_than, pair_runs, table

COLS = [
    ("pairs", "pairs"), ("pos_U", "Pos% U"), ("pos_C", "Pos% C"), ("pos_agreed", "Pos% agreed"),
    ("agreed", "n agreed"), ("disagreements", "DISAGREE"), ("both_finished", "both fin."),
    ("better_pct", "Better%"), ("gm_U", "GM U [ms]"), ("gm_C", "GM C [ms]"),
    ("gm_speedup", "GM speed-up C/U"), ("to_excl", "TO excl U/C"), ("to_total", "TO total U/C"),
    ("memout", "MEMOUT U/C"), ("error", "ERR U/C"), ("notfound", "NOT_FOUND U/C"),
]


def _fmt(key: str, row: dict) -> str:
    if key in ("to_excl", "to_total", "memout", "error", "notfound"):
        return f"{row[f'{key}_U']}/{row[f'{key}_C']}"
    v = row.get(key)
    if v is None:
        return "–"
    if key in ("gm_U", "gm_C"):
        return f"{1000 * v:.2f}"
    if key == "gm_speedup":
        return f"{v:.2f}"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def md_table(rows: dict[str, dict]) -> str:
    head = "| class | " + " | ".join(lbl for _, lbl in COLS) + " |"
    sep = "|---" * (len(COLS) + 1) + "|"
    lines = [head, sep]
    for cls, row in rows.items():
        name = f"**{cls}**" if cls == "ALL" else cls
        lines.append(f"| {name} | " + " | ".join(_fmt(k, row) for k, _ in COLS) + " |")
    return "\n".join(lines)


def write_report(out: Path, cfg, preps: list[dict], records: list[dict]) -> str:
    pairs = pair_runs(records)
    classes = list(cfg.classes)
    full = table(pairs, classes)
    filt = table(classic_slower_than(pairs, cfg.filter_ms), classes)
    certs = Counter(p.get("cert") for p in preps)
    mods = [m for p in preps if p.get("cert") in ("oracle", "exact-search") for m in p.get("mods", [])]
    mod_ok = [m for m in mods if m["spec"] is not None]
    mod_fail = Counter(m["failure"] for m in mods if m["spec"] is None)
    redraw_reasons: Counter = Counter()
    for m in mods:
        redraw_reasons.update(m.get("redraw_reasons") or {})
    status = {s: Counter(r["status"] for r in records if r["system"] == s) for s in ("update", "classic")}
    errors = [r for r in records if r["status"] == "ERROR"]
    findings = [r for r in errors if "FINDING" in str(r.get("error"))]
    exact_nf = [r for r in records if r["mode"] == "exact" and r["status"] == "NOT_FOUND"]
    disagreements = [d for rows in full.values() for d in rows["ALL"]["disagreement_keys"]]
    ks = Counter(p["k"] for p in preps if p.get("cert") in ("oracle", "exact-search"))

    L: list[str] = []
    L.append(f"# Benchmark run `{cfg.run_id}`\n")
    L.append("Paper §6 comparison protocol (Update = `Strategy.PAPER`, Classic = `Strategy.RECOMPUTE`, "
             "same `TopDownDecomposer` type and mode, same k, same time limit). **Absolute numbers are "
             "not comparable with the paper** (our decomposer is a pure-Python top-down search, not "
             "BalancedGo / log-k-decomp; different machine; much smaller limits). See benchmarks/README.md.\n")
    L.append(f"- seed {cfg.seed}; preset `{cfg.preset}`; {cfg.per_class} modifications per class; classes "
             f"{', '.join(classes)}; modes {', '.join(m.upper() for m in cfg.modes)}")
    L.append(f"- per-run time limit {cfg.timeout}s (Budget inside + hard kill at {cfg.run_hard_deadline():.0f}s); "
             f"ghw search budget {cfg.prep_timeout}s per instance; sampled RSS cap "
             f"{cfg.mem_cap_mb} MB per worker; {cfg.jobs} parallel workers")
    L.append(f"- filters: families={list(cfg.families) if cfg.families else 'all'}, "
             f"vertices in [{cfg.min_vertices}, {cfg.max_vertices}], max edges {cfg.max_edges}, "
             f"limit {cfg.limit}\n")

    L.append("## Instance funnel\n")
    L.append(f"- selected: {len(preps)}")
    L.append(f"- k certified minimal by the exact oracle (|V| <= {cfg.oracle_max_vertices}): {certs.get('oracle', 0)}")
    L.append(f"- k certified minimal by EXACT search (k-1 refuted, not budget-cut): {certs.get('exact-search', 0)}")
    L.append(f"- **skipped: ghw not established** (budget hit, no certificate): {certs.get('unknown', 0)}")
    L.append(f"- prep killed by the pool (hard deadline / memory): {certs.get('killed', 0)}; "
             f"prep errors: {certs.get('error', 0)}; certification mismatches (FINDING): {certs.get('ERROR', 0)}")
    L.append(f"- ghw of the instances in the main table: {dict(sorted(ks.items()))}")
    fam = Counter(p["family"] for p in preps if p.get("cert") in ("oracle", "exact-search"))
    L.append(f"- families in the main table: {dict(sorted(fam.items()))}")
    L.append(f"- modification slots: {len(mods)}; generated {len(mod_ok)}; not generated "
             f"{sum(mod_fail.values())} {dict(mod_fail) if mod_fail else ''}")
    L.append(f"- redraws: {sum(redraw_reasons.values())} {dict(redraw_reasons) if redraw_reasons else ''}; "
             f"draws that made two edges equal (A9, kept): "
             f"{sum(1 for m in mod_ok if m['creates_duplicate_edges'])}")
    L.append(f"- runs: {len(records)}; Update statuses {dict(status['update'])}; "
             f"Classic statuses {dict(status['classic'])}\n")

    L.append("## Correctness checks\n")
    L.append(f"- Update/Classic yes/no **disagreements: {len(disagreements)}**"
             + ("" if not disagreements else " — CORRECTNESS BUG, reproducers below"))
    for d in disagreements:
        L.append(f"  - {d}")
    L.append(f"- harness re-validation failures / pipeline InvalidGHDError (FINDING): {len(findings)}")
    for r in findings[:20]:
        L.append(f"  - {r['instance']} {r['mod_class']}#{r['mod_index']} {r['system']}: {str(r['error'])[:300]}")
    L.append(f"- other ERROR records: {len(errors) - len(findings)}")
    for r in [e for e in errors if e not in findings][:20]:
        L.append(f"  - {r['instance']} {r['mod_class']}#{r['mod_index']} {r['system']} {r['mode']}: "
                 f"{str(r['error'])[:300]}")
    L.append(f"- EXACT runs with NOT_FOUND inside the time limit (unexpected): {len(exact_nf)}")
    L.append(f"- Update outputs not in normal form: "
             f"{sum(1 for r in records if r['system'] == 'update' and r['status'] == 'UPDATED' and r.get('out_nf') is False)}\n")

    legend = ("Pos% = yes/(yes+no) over the system's definite answers; agreed = answer of whichever "
              "system answered; Better% = Update faster, over pairs where both finished; GM = "
              "geometric mean wall time over the same pairs; speed-up = GM of Classic/Update; TO excl = "
              "only this system timed out; TO total = all its timeouts (A24).")
    for mode in full:
        L.append(f"## {mode.upper()} decomposer — all pairs\n")
        L.append(md_table(full[mode]) + "\n")
        L.append(f"## {mode.upper()} decomposer — paper filter: Classic > {cfg.filter_ms:g} ms\n")
        if mode in filt:
            L.append(md_table(filt[mode]) + "\n")
        else:
            L.append("_no pair passes the filter_\n")
        L.append(legend + "\n")

    plot_paths = []
    try:
        from benchmarks.plots import fig7   # noqa: PLC0415
        for mode in full:
            plot_paths += fig7(pairs, out / "plots", mode)
    except Exception as exc:  # noqa: BLE001 - a plotting failure must not lose the tables
        L.append(f"\nPlotting failed: {exc!r}\n")
    if plot_paths:
        L.append("## Plots\n")
        for p in plot_paths:
            L.append(f"- `{p.relative_to(out).as_posix()}`")
        L.append("\nOnly pairs where both systems finished are plotted (a timeout has no runtime).\n")
    text = "\n".join(L)
    (out / "summary.md").write_text(text, encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps({"all": full, "filtered": filt,
                                                  "filter_ms": cfg.filter_ms}, indent=2, default=str),
                                      encoding="utf-8")
    return text

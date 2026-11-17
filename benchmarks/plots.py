"""Fig. 7-style plots (matplotlib, Agg backend, PNG).

Per decomposer mode: wall time of Update vs Classic grouped by ghw (= k of the input GHD), by
number of edges (binned) and by number of vertices (binned). Only pairs where BOTH systems
finished within the time limit are plotted (timeouts have no runtime); the group size n is
printed under each group. A log-log scatter of Classic vs Update time is added per mode.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from benchmarks.metrics import EPS, FINISHED  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
COLORS = {"update": "#2a78d6", "classic": "#eb6834"}   # categorical slots 1 and 2
LABELS = {"update": "Update (PAPER strategy)", "classic": "Classic (RECOMPUTE)"}

EDGE_BINS = [(1, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, 10**9)]
VERTEX_BINS = [(1, 8), (9, 16), (17, 30), (31, 50), (51, 100), (101, 10**9)]


def _bin_label(lo: int, hi: int) -> str:
    return f">{lo - 1}" if hi >= 10**9 else f"{lo}-{hi}"


def _group(pairs: list[dict], key) -> list[tuple[str, list[dict]]]:
    groups: dict = {}
    for p in pairs:
        g = key(p)
        if g is not None:
            groups.setdefault(g, []).append(p)
    return [(lbl, ps) for (_, lbl), ps in sorted(groups.items())]


def _binned(field: str, bins):
    def key(p):
        v = p.get(field)
        for i, (lo, hi) in enumerate(bins):
            if v is not None and lo <= v <= hi:
                return (i, _bin_label(lo, hi))
        return None
    return key


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_yscale("log")
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)


def _panel(ax, groups, title: str, xlabel: str) -> None:
    _style(ax)
    pos, ticks, labels = 0.0, [], []
    for lbl, ps in groups:
        for j, side in enumerate(("update", "classic")):
            data = [max(p[side]["wall_s"], EPS) for p in ps]
            bp = ax.boxplot([data], positions=[pos + j * 0.42], widths=0.36, patch_artist=True,
                            showfliers=True, manage_ticks=False)
            for box in bp["boxes"]:
                box.set(facecolor=COLORS[side], edgecolor=COLORS[side], alpha=0.85)
            for part in ("whiskers", "caps"):
                for line in bp[part]:
                    line.set(color=COLORS[side], linewidth=1.2)
            for med in bp["medians"]:
                med.set(color=SURFACE, linewidth=2)
            for fl in bp["fliers"]:
                fl.set(marker="o", markersize=3, markerfacecolor=COLORS[side],
                       markeredgecolor=SURFACE, alpha=0.6)
        ticks.append(pos + 0.21)
        labels.append(f"{lbl}\nn={len(ps)}")
        pos += 1.2
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.set_ylabel("wall time [s] (log)", color=INK2, fontsize=9)
    if not groups:
        ax.text(0.5, 0.5, "no pair where both finished", transform=ax.transAxes, ha="center",
                color=INK2)


def fig7(pairs: list[dict], out_dir: Path, mode: str, subset_label: str = "") -> list[Path]:
    """Write fig7_<mode>.png and scatter_<mode>.png; returns the paths."""
    both = [p for p in pairs if p["mode"] == mode and p["update"] and p["classic"]
            and p["update"]["status"] in FINISHED and p["classic"]["status"] in FINISHED]
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), facecolor=SURFACE)
    _panel(axes[0], _group(both, lambda p: (p["k"], str(p["k"]))), "by ghw (k of the input GHD)", "ghw")
    _panel(axes[1], _group(both, _binned("n_edges", EDGE_BINS)), "by number of edges", "|E(H)|")
    _panel(axes[2], _group(both, _binned("n_vertices", VERTEX_BINS)), "by number of vertices", "|V(H)|")
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[s]) for s in ("update", "classic")]
    fig.legend(handles, [LABELS["update"], LABELS["classic"]], loc="upper right", frameon=False,
               fontsize=9, labelcolor=INK)
    fig.suptitle(f"Runtime, Update vs Classic: {mode.upper()} decomposer{subset_label} "
                 f"(pairs where both finished: {len(both)})", color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    p = out_dir / f"fig7_{mode}.png"
    fig.savefig(p, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    paths.append(p)

    fig, ax = plt.subplots(figsize=(5.2, 5), facecolor=SURFACE)
    _style(ax)
    ax.set_xscale("log")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    xs = [max(p["classic"]["wall_s"], EPS) for p in both]
    ys = [max(p["update"]["wall_s"], EPS) for p in both]
    if xs:
        lo, hi = min(xs + ys) / 1.5, max(xs + ys) * 1.5
        ax.plot([lo, hi], [lo, hi], color=INK2, linewidth=1, linestyle="--")
        ax.text(hi, hi, " equal time", color=INK2, fontsize=8, va="bottom", ha="right")
        ax.scatter(xs, ys, s=16, color=COLORS["update"], edgecolors=SURFACE, linewidths=0.5, alpha=0.8)
    ax.set_xlabel("Classic wall time [s]", color=INK2, fontsize=9)
    ax.set_ylabel("Update wall time [s]", color=INK2, fontsize=9)
    ax.set_title(f"{mode.upper()}: below the diagonal = Update faster (n={len(both)})",
                 color=INK, fontsize=10, loc="left")
    fig.tight_layout()
    p = out_dir / f"scatter_{mode}.png"
    fig.savefig(p, dpi=130, facecolor=SURFACE)
    plt.close(fig)
    paths.append(p)
    return paths

"""Draw the frames of examples/modifications_tour.py: for every step, the hypergraph (top; edges
changed by the step in orange) and the decomposition used next (bottom; reused nodes blue, new
nodes orange). Colors are the reference categorical slots 1-2; every colored element also carries
a text tag, so color is never the only cue."""

from __future__ import annotations

import math
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon  # noqa: E402

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#c9c8c3"
BLUE, ORANGE, NEUTRAL = "#2a78d6", "#eb6834", "#8a8986"

HEX = {v: (math.cos(math.pi / 2 - i * math.pi / 3), math.sin(math.pi / 2 - i * math.pi / 3))
       for i, v in enumerate("abcdef")}
HEX["x"] = (0.0, 0.0)


def _pos(v: str, extra: dict) -> tuple[float, float]:
    if v not in HEX and v not in extra:
        extra[v] = (0.35 * math.cos(len(extra)), -0.35 * math.sin(len(extra)) - 0.2)
    return HEX.get(v) or extra[v]


def _s(xs) -> str:
    return "{" + ",".join(sorted(xs)) + "}"


def draw_hypergraph(ax, h, changed: set) -> None:
    extra: dict = {}
    for name, vs in sorted(h.edges.items(), key=lambda kv: kv[0] in changed):
        pts = [_pos(v, extra) for v in sorted(vs)]
        col = ORANGE if name in changed else NEUTRAL
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        if len(pts) == 1:
            ax.add_patch(plt.Circle(pts[0], 0.16, fill=False, ec=col, lw=2))
        elif len(pts) == 2:
            ax.plot(*zip(*pts), color=col, lw=2.5 if name in changed else 2, solid_capstyle="round",
                    zorder=1)
        else:
            pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
            ax.add_patch(Polygon(pts, closed=True, fc=col, ec=col, alpha=0.18, lw=2, zorder=1))
        tag = name + (" *" if name in changed else "")
        ax.text(cx, cy, tag, fontsize=7.5, color=INK2, ha="center", va="center", zorder=3,
                bbox=dict(boxstyle="round,pad=0.12", fc=SURFACE, ec="none", alpha=0.85))
    for v in sorted(h.vertices):
        x, y = _pos(v, extra)
        ax.scatter([x], [y], s=150, color=SURFACE, edgecolors=INK, linewidths=1.2, zorder=4)
        ax.text(x, y, v, fontsize=8, ha="center", va="center", color=INK, zorder=5)
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.3, 1.3)
    ax.set_aspect("equal")
    ax.axis("off")


def draw_tree(ax, g, reused: set) -> None:
    depth, order, kids = {}, [], {}

    def walk(u, d):
        depth[u] = d
        kids[u] = list(g.children(u))
        if not kids[u]:
            order.append(u)
        for c in kids[u]:
            walk(c, d + 1)
    walk(g.root, 0)
    xs: dict = {}

    def place(u):
        if not kids[u]:
            xs[u] = order.index(u)
        else:
            for c in kids[u]:
                place(c)
            xs[u] = sum(xs[c] for c in kids[u]) / len(kids[u])
    place(g.root)
    width = max(len(order), 1)
    maxd = max(depth.values())
    pos = {u: ((xs[u] + 0.5) / width, 1 - (depth[u] + 0.5) / (maxd + 1)) for u in xs}
    for u, cs in kids.items():
        for c in cs:
            ax.plot([pos[u][0], pos[c][0]], [pos[u][1], pos[c][1]], color=GRID, lw=1.5, zorder=1)
    for u, (x, y) in pos.items():
        n = g.node(u)
        is_reused = (n.bag, n.cover) in reused
        col = BLUE if is_reused else ORANGE
        label = f"{'reused' if is_reused else 'new'}\nB={_s(n.bag)}\nλ={_s(n.cover)}"
        ax.text(x, y, label, fontsize=7, ha="center", va="center", color=INK, zorder=3,
                bbox=dict(boxstyle="round,pad=0.35", fc=SURFACE, ec=col, lw=2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")


def draw(frames: list[dict], out: str, cols: int = 5) -> None:
    rows = math.ceil(len(frames) / cols)
    fig = plt.figure(figsize=(4.2 * cols, 7.4 * rows), facecolor=SURFACE)
    sub = fig.add_gridspec(rows * 2, cols, height_ratios=[1, 1.05] * rows, hspace=0.22, wspace=0.08,
                           top=0.945, bottom=0.01, left=0.01, right=0.99)
    for i, f in enumerate(frames):
        r, c = divmod(i, cols)
        top = fig.add_subplot(sub[2 * r, c])
        bot = fig.add_subplot(sub[2 * r + 1, c])
        for ax in (top, bot):
            ax.set_facecolor(SURFACE)
        draw_hypergraph(top, f["h"], f["changed"])
        draw_tree(bot, f["g"], f["reused"])
        if f["status"] == "start":
            head, sub_t = "start", f"ghw = {f['ghw']}"
        else:
            arrow = f"ghw {f['before']} → {f['ghw']}"
            ans = "NO GHD of width k" if f["status"] == "proven_no" else "updated"
            head, sub_t = f["title"], f"{arrow}   ·   k={f['k']}: {ans}"
        why = textwrap.fill(f.get("why", ""), 34)
        top.set_title(f"{head}\n{why}", fontsize=10, color=INK, loc="left", pad=4)
        top.text(0, -0.02, sub_t, transform=top.transAxes, fontsize=9.5, color=INK, va="top",
                 fontweight="bold")
        bot.text(0, 1.0, "decomposition carried forward" + (" (recomputed)" if f.get("recomputed") else ""),
                 transform=bot.transAxes, fontsize=8, color=INK2, va="bottom")
    fig.suptitle("Hypergraph modifications and generalized hypertree width (ghw)     "
                 "orange * = edge changed by the step   ·   blue = reused decomposition node   ·   "
                 "orange box = new node", fontsize=12, color=INK, x=0.01, ha="left", y=0.99)
    fig.savefig(out, dpi=110, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)

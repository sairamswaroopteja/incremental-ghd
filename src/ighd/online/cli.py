"""Interactive, query-based front end for OnlineSession.

    python online.py                      (from the project root; no install needed)
    python online.py --load graph.hg      start from a HyperBench file
    python online.py --script cmds.txt    run commands from a file, then stay interactive
    echo "..." | python online.py         commands from a pipe (no prompt)

Type 'help' for the command list. Everything typed is parsed here; the mathematics lives in
OnlineSession and the update pipeline.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ighd.common.errors import IGHDError
from ighd.ghd import GHD, check_normal_form, validate
from ighd.hypergraph import Hypergraph, parse_hyperbench, to_hyperbench
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar
from ighd.online.session import OnlineSession, StepReport
from ighd.update import Strategy

HELP = """\
Initial hypergraph (typed before the first modification):
  edge NAME v1 v2 ...            add an edge, e.g.  edge e1 a b c
  NAME(v1,v2,...), ...           HyperBench syntax, e.g.  e1(a,b,c), e2(c,d).
  load PATH                      read a HyperBench .hg file
  start                          compute the initial minimum-width decomposition
                                 (also happens automatically at the first modification/query)
  reset                          forget everything and start a new hypergraph

Modifications (online: each is applied to the current decomposition when you type it):
  addvar V E1 E2 ...             new vertex V added to existing edges E1, E2, ...
  delvar V                       delete vertex V from every edge
  addconstr NAME v1 v2 ...       new edge NAME on the given vertices
  delconstr NAME                 delete edge NAME
  addeq v1 v2 ... -> W           merge the vertices into W (W may be one of them, or new)
  deleq V : P1 = E1 E2 ; P2 = E3 split V; part P1 takes edges E1,E2, part P2 takes E3
                                 (every edge of V must be listed; a part may be named V)

Queries:
  ghw                            current width k and whether k = ghw is proven
  ghd | tree                     current decomposition (bags B, covers lambda)
  show | hypergraph              current hypergraph
  check                          re-validate the decomposition independently
  history                        every step so far with its timing
  save PATH                      write the current hypergraph in HyperBench format

Settings:
  strategy paper|theorem45|recompute   update method (paper = Algorithm 5; default)
  tighten on|off                 after a step that may lower ghw, search for a smaller width
  oracle on|off                  also check ghw with the exact oracle (<= 16 vertices)
  timeout SECONDS|off            time limit per search (default off: every answer exact)
  undo                           undo the last step
  help, quit
"""

TOKEN = re.compile(r"->|[:;=]|(?:(?!->)[^\s,(){}:;=])+")
"""Words are split at whitespace, commas, brackets and ':;='; '->' is its own token even unspaced."""


def _s(xs) -> str:
    return "{" + ",".join(sorted(xs)) + "}"


def format_tree(g: GHD) -> str:
    lines: list[str] = []

    def rec(u, depth):
        n = g.node(u)
        lines.append(f"  {'    ' * depth}node {u}: B={_s(n.bag)}  lambda={_s(n.cover)}")
        for c in g.children(u):
            rec(c, depth + 1)
    if len(g):
        rec(g.root, 0)
    return "\n".join(lines)


def format_h(h: Hypergraph) -> str:
    return "\n".join(f"  {e}{_s(vs)}" for e, vs in sorted(h.edges.items()))


def format_step(r: StepReport) -> str:
    out = [f"  {r.description}"]
    if r.edge_changes:
        out.append("  edges   : " + "   ".join(r.edge_changes))
    if r.status == "built":
        out.append(f"  result  : decomposition built in {r.seconds * 1000:.1f} ms (strategy: exact search)")
    elif r.status == "updated":
        out.append(f"  result  : UPDATED in {r.seconds * 1000:.1f} ms with strategy {r.strategy}: "
                   f"reused {r.reused_nodes} of {r.old_nodes} old nodes, "
                   f"{r.decomposer_calls} decomposer call(s)")
    elif r.status == "proven_no":
        out.append(f"  result  : NO GHD of width {r.k_before} exists (found in {r.seconds * 1000:.1f} ms); "
                   "recomputed at a higher width")
    else:
        out.append(f"  result  : {r.status.upper()} after {r.seconds * 1000:.1f} ms")
    out.append(f"  ghw     : {r.ghw_note}")
    if r.oracle_ghw is not None:
        out.append(f"  oracle  : exact_ghw = {r.oracle_ghw}"
                   + (" (agrees)" if r.exact and r.oracle_ghw == r.width_after else ""))
    out += [f"  note    : {n}" for n in r.notes]
    return "\n".join(out)


def _path(rest: str) -> Path:
    """The rest of the line as a path: Windows backslashes and spaces are kept as typed;
    one pair of surrounding quotes is removed."""
    s = rest.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        s = s[1:-1]
    return Path(s)


def _edges(tokens: list[str]) -> frozenset[str]:
    if not tokens:
        raise ValueError("expected at least one name")
    return frozenset(tokens)


def parse_modification(cmd: str, toks: list[str]):
    """Turn a command and its tokens into a modification object (ValueError on bad syntax)."""
    if cmd == "addvar":
        if len(toks) < 2:
            raise ValueError("usage: addvar V E1 E2 ...")
        return AddVar(toks[0], _edges(toks[1:]))
    if cmd == "delvar":
        if len(toks) != 1:
            raise ValueError("usage: delvar V")
        return DelVar(toks[0])
    if cmd == "addconstr":
        if len(toks) < 2:
            raise ValueError("usage: addconstr NAME v1 v2 ...")
        return AddConstr(toks[0], _edges(toks[1:]))
    if cmd == "delconstr":
        if len(toks) != 1:
            raise ValueError("usage: delconstr NAME")
        return DelConstr(toks[0])
    if cmd == "addeq":
        if "->" not in toks or toks.count("->") != 1 or toks.index("->") != len(toks) - 2:
            raise ValueError("usage: addeq v1 v2 ... -> W")
        return AddEq(_edges(toks[:-2]), toks[-1])
    if cmd == "deleq":
        if len(toks) < 3 or toks[1] != ":":
            raise ValueError("usage: deleq V : P1 = E1 E2 ; P2 = E3")
        parts: dict[str, frozenset[str]] = {}
        for chunk in " ".join(toks[2:]).split(";"):
            words = chunk.split()
            if len(words) < 3 or words[1] != "=":
                raise ValueError(f"bad part {chunk.strip()!r}: expected  P = E1 E2 ...")
            if words[0] in parts:
                raise ValueError(f"part {words[0]!r} given twice")
            parts[words[0]] = _edges(words[2:])
        return DelEq(toks[0], parts)
    raise ValueError(f"unknown modification {cmd!r}")


MODS = {"addvar", "delvar", "addconstr", "delconstr", "addeq", "deleq"}
STRATEGIES = {"paper": Strategy.PAPER, "theorem45": Strategy.THEOREM45, "recompute": Strategy.RECOMPUTE}


class Shell:
    """Line-oriented command interpreter; ``execute`` returns the text to print."""

    def __init__(self, session: OnlineSession | None = None) -> None:
        self.session = session or OnlineSession()
        self.pending: dict[str, frozenset[str]] = {}

    # -------------------------------------------------------------------------- building
    def _add_edges(self, edges: dict[str, frozenset[str]]) -> str:
        if self.session.h is not None:
            return ("error: the initial hypergraph is fixed once decomposed; use 'addconstr' to "
                    "add an edge online, or 'reset' to start over")
        clash = sorted(set(edges) & set(self.pending))
        if clash:
            return f"error: edge name(s) already used: {', '.join(clash)}"
        self.pending.update(edges)
        return f"  {len(self.pending)} edge(s) so far; type 'start' when the hypergraph is complete"

    def _ensure_built(self) -> str:
        if self.session.h is not None:
            return ""
        if not self.pending:
            raise IGHDError("no hypergraph yet: type edges first (see 'help')")
        h = Hypergraph(self.pending)
        rep = self.session.build(h)
        self.pending = {}
        return ("initial hypergraph:\n" + format_h(h) + "\n" + format_step(rep) + "\n"
                + "decomposition:\n" + format_tree(self.session.ghd) + "\n")

    # -------------------------------------------------------------------------- dispatch
    def execute(self, line: str) -> str:
        line = line.strip()
        if not line or line.startswith("#"):
            return ""
        try:
            return self._execute(line)
        except (IGHDError, ValueError) as exc:
            return f"error: {exc}"

    def _execute(self, line: str) -> str:
        head, _, rest = line.partition(" ")
        cmd = head.lower()
        if "(" in head and cmd not in MODS:          # HyperBench term(s): e1(a,b), e2(b,c).
            return self._add_edges(dict(parse_hyperbench(line).edges))
        toks = TOKEN.findall(rest)
        s = self.session
        if cmd in ("help", "?"):
            return HELP
        if cmd == "edge":
            if len(toks) < 2:
                return "error: usage: edge NAME v1 v2 ..."
            return self._add_edges({toks[0]: frozenset(toks[1:])})
        if cmd == "load":
            path = _path(rest)
            if not path.is_file():
                return f"error: no such file: {path}"
            return self._add_edges(dict(parse_hyperbench(path.read_text(encoding="utf-8")).edges))
        if cmd in ("start", "build"):
            if s.h is not None:
                return "error: already started (use 'reset' to start a new hypergraph)"
            return self._ensure_built()
        if cmd == "reset":
            self.session = OnlineSession(strategy=s.strategy, tighten=s.tighten,
                                         oracle_check=s.oracle_check, time_limit_s=s.time_limit_s)
            self.pending = {}
            return "  cleared; type the new initial hypergraph"
        if cmd == "rebuild":
            if s.h is None:
                return "error: nothing to rebuild"
            rep = s.build(s.h)
            return format_step(rep) + "\ndecomposition:\n" + (format_tree(s.ghd) if s.ghd else "  none")
        if cmd in MODS:
            pre = self._ensure_built()
            try:
                rep = s.apply(parse_modification(cmd, toks))
            except (IGHDError, ValueError) as exc:     # state unchanged; keep the build output
                return pre + f"error: {exc}"
            tree = format_tree(s.ghd) if s.ghd is not None else "  (none)"
            return pre + format_step(rep) + "\ndecomposition now:\n" + tree
        if cmd in ("ghw", "width"):
            pre = self._ensure_built()
            if s.k is None:
                return pre + "  unknown (the last search hit the time limit)"
            proof = "proven by exact search" if s.exact else "upper bound only (not proven minimal)"
            return pre + f"  ghw = {s.k}  ({proof})" if s.exact else pre + f"  ghw <= {s.k}  ({proof})"
        if cmd in ("ghd", "tree"):
            pre = self._ensure_built()
            if s.ghd is None:
                return pre + "  no current decomposition"
            return pre + f"  width {s.k}, {len(s.ghd)} node(s):\n" + format_tree(s.ghd)
        if cmd in ("show", "hypergraph", "h"):
            if s.h is None:
                return "pending (not yet decomposed):\n" + format_h(Hypergraph(self.pending)) \
                    if self.pending else "  empty"
            return f"  {len(s.h.edge_names)} edges, {len(s.h.vertices)} vertices:\n" + format_h(s.h)
        if cmd in ("check", "validate"):
            pre = self._ensure_built()
            if s.ghd is None:
                return pre + "  no current decomposition"
            rep = validate(s.h, s.ghd)
            nf = check_normal_form(s.h, s.ghd).ok
            return pre + (f"  valid GHD: {rep.ok}, width {rep.width}, normal form: {nf}"
                          + ("" if rep.ok else f"\n  violations: {rep.violations}"))
        if cmd == "history":
            if not s.history:
                return "  no steps yet"
            rows = [f"  {i:3d}. {r.description:52.52s} {r.status:10s} {r.seconds * 1000:8.1f} ms  "
                    f"width {r.width_after}{'' if r.exact else ' (bound)'}"
                    for i, r in enumerate(s.history, 1)]
            return "\n".join(rows)
        if cmd == "save":
            if s.h is None:
                return "error: nothing to save yet"
            path = _path(rest) if rest.strip() else None
            if path is None:
                return "error: usage: save PATH"
            path.write_text(to_hyperbench(s.h) + "\n", encoding="utf-8")
            return f"  wrote {path}"
        if cmd == "undo":
            return "  undone" if s.undo() else "  nothing to undo"
        if cmd == "strategy":
            if not toks or toks[0].lower() not in STRATEGIES:
                return "error: usage: strategy paper|theorem45|recompute"
            s.strategy = STRATEGIES[toks[0].lower()]
            return f"  strategy = {s.strategy.value}"
        if cmd in ("tighten", "oracle"):
            if not toks or toks[0].lower() not in ("on", "off"):
                return f"error: usage: {cmd} on|off"
            setattr(s, "tighten" if cmd == "tighten" else "oracle_check", toks[0].lower() == "on")
            return f"  {cmd} {toks[0].lower()}"
        if cmd == "timeout":
            if not toks:
                return "error: usage: timeout SECONDS|off"
            s.time_limit_s = None if toks[0].lower() == "off" else float(toks[0])
            return f"  timeout = {s.time_limit_s or 'off'}"
        return f"error: unknown command {head!r} (type 'help')"


BANNER = """\
Online GHD maintenance (Gottlob et al., arXiv:2209.10375).
Type the initial hypergraph (e.g. 'edge e1 a b' or 'e1(a,b), e2(b,c).'), then 'start'.
Then send modifications one at a time, and ask queries in between. 'help' lists everything."""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Online, query-based GHD maintenance")
    ap.add_argument("--load", help="initial hypergraph in HyperBench format")
    ap.add_argument("--script", help="run the commands in this file first")
    ap.add_argument("--strategy", choices=sorted(STRATEGIES), default="paper")
    ap.add_argument("--timeout", type=float, help="time limit per search in seconds (default none)")
    ap.add_argument("--oracle", action="store_true", help="cross-check ghw with the exact oracle")
    ap.add_argument("--no-interactive", action="store_true", help="exit after --script / --load")
    a = ap.parse_args(argv)
    shell = Shell(OnlineSession(strategy=STRATEGIES[a.strategy], oracle_check=a.oracle,
                                time_limit_s=a.timeout))
    interactive = sys.stdin.isatty() and not a.no_interactive
    if interactive:
        print(BANNER)
    if a.load:
        print(shell.execute(f'load "{a.load}"'))
    if a.script:
        for line in Path(a.script).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.strip().startswith("#"):
                print(f"ghd> {line.strip()}")
            out = shell.execute(line)
            if out:
                print(out)
    if a.no_interactive:
        return 0
    while True:
        try:
            line = input("ghd> " if interactive else "")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.strip().lower() in ("quit", "exit", "q"):
            return 0
        if not interactive and line.strip():
            print(f"ghd> {line.strip()}")
        out = shell.execute(line)
        if out:
            print(out)


if __name__ == "__main__":
    raise SystemExit(main())

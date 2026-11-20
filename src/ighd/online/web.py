"""Local web interface for the online system: a JSON API around OnlineSession plus one page.

    python web.py                 (project root) -> http://127.0.0.1:8765 opens in the browser
    python web.py --port 9000 --no-browser

Single user, local only: the server binds to 127.0.0.1 and holds one session in memory.
Uses only the Python standard library.

API (JSON in, JSON out; every response carries the full current state):
    GET  /api/state
    GET  /api/examples                       built-in example hypergraphs
    GET  /api/hyperbench                     small HyperBench instances, if the data is present
    POST /api/hyperbench   {name}            text of one of those instances
    POST /api/start        {text}            initial hypergraph (one edge per line, or HyperBench)
    POST /api/modify       {kind, ...}       one of the six modifications
    POST /api/undo | /api/reset
    POST /api/settings     {strategy, tighten, oracle, timeout}
Errors: HTTP 400 with {"error": message}; the session is left unchanged.
"""

from __future__ import annotations

import argparse
import functools
import dataclasses
import json
import os
import re
import secrets
import threading
import time
import webbrowser
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ighd.common.errors import IGHDError
from ighd.ghd import validate
from ighd.hypergraph import Hypergraph, parse_hyperbench
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar
from ighd.online.session import OnlineSession
from ighd.update import Strategy

STATIC = Path(__file__).with_name("static")
STATIC_FILES = {"style.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
"""The only files served from static/ (an allow-list: no path from the URL reaches the disk)."""
HYPERBENCH_DIR = Path(__file__).resolve().parents[3] / "benchmarks" / "data" / "hyperbench" / "all"
MAX_EDGES, MAX_VERTICES, MAX_BODY = 200, 200, 1_000_000
STRATEGIES = {"paper": Strategy.PAPER, "theorem45": Strategy.THEOREM45, "recompute": Strategy.RECOMPUTE}

EXAMPLES = [
    {"name": "Path a-b-c-d-e (ghw 1)", "text": "e1: a b\ne2: b c\ne3: c d\ne4: d e"},
    {"name": "Cycle of 6 (ghw 2)", "text": "e1: a b\ne2: b c\ne3: c d\ne4: d e\ne5: e f\ne6: f a"},
    {"name": "Paper H_P2, Fig. 5(a) (ghw 2)",
     "text": "w1: a b c\nw2: f g h\nw3: e i k\nw4: a d f\nw5: c e h\nw6: j k l\nw7: c i"},
    {"name": "Paper H_P', Example 2.1 (ghw 2)",
     "text": "w1: a b c\nw2: f g h\nw3: e i k\nw4: a d f\nw5: c e h\nw6: j k l"},
    {"name": "Triangle of triangles (ghw 2)",
     "text": "t1: a b c\nt2: c d e\nt3: e f a\nm: a c e"},
]


class InputError(ValueError):
    """Bad user input (reported with HTTP 400)."""


def parse_edge_text(text: str) -> Hypergraph:
    """One edge per line ('e1: a b c', 'e1 a, b, c') or HyperBench terms ('e1(a,b,c), ...')."""
    lines = [ln.split("%")[0].split("#")[0].strip() for ln in text.splitlines()]
    body = "\n".join(ln for ln in lines if ln)
    if not body:
        raise InputError("the hypergraph is empty: give at least one edge")
    if "(" in body:
        h = parse_hyperbench(body)
    else:
        edges: dict[str, list[str]] = {}
        for ln in body.splitlines():
            words = [w for w in re.split(r"[\s,;:{}]+", ln) if w]
            if len(words) < 2:
                raise InputError(f"line {ln!r}: expected an edge name followed by its vertices")
            if words[0] in edges:
                raise InputError(f"edge name {words[0]!r} is used twice")
            edges[words[0]] = words[1:]
        h = Hypergraph(edges)
    if len(h.edge_names) > MAX_EDGES or len(h.vertices) > MAX_VERTICES:
        raise InputError(f"too large for this interface (limit {MAX_EDGES} edges, {MAX_VERTICES} vertices)")
    return h


def _names(value, what: str) -> frozenset[str]:
    if isinstance(value, str):
        value = [w for w in re.split(r"[\s,;]+", value) if w]
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise InputError(f"{what}: expected a list of names")
    return frozenset(v.strip() for v in value)


def _name(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip() or re.search(r"[\s,;(){}]", value.strip()):
        raise InputError(f"{what}: expected a single name without spaces or punctuation")
    return value.strip()


def build_modification(req: dict):
    kind = req.get("kind")
    if kind == "AddVar":
        return AddVar(_name(req.get("vertex"), "new vertex"), _names(req.get("edges"), "edges"))
    if kind == "DelVar":
        return DelVar(_name(req.get("vertex"), "vertex"))
    if kind == "AddConstr":
        return AddConstr(_name(req.get("name"), "edge name"), _names(req.get("vertices"), "vertices"))
    if kind == "DelConstr":
        return DelConstr(_name(req.get("name"), "edge"))
    if kind == "AddEq":
        return AddEq(_names(req.get("merge"), "vertices to merge"), _name(req.get("into"), "merged vertex"))
    if kind == "DelEq":
        parts = req.get("parts")
        if not isinstance(parts, dict) or not parts:
            raise InputError("parts: expected {part name: [edges]}")
        return DelEq(_name(req.get("vertex"), "vertex"),
                     {_name(p, "part name"): _names(es, f"edges of part {p}") for p, es in parts.items()})
    raise InputError(f"unknown modification kind {kind!r}")


@dataclasses.dataclass(frozen=True)
class Limits:
    """Input and search limits. ``public()`` is used when the site is hosted for anyone to use."""

    max_edges: int = MAX_EDGES
    max_vertices: int = MAX_VERTICES
    default_timeout_s: float | None = 30.0
    max_timeout_s: float | None = None        # None: the user may remove the time limit
    public: bool = False

    @classmethod
    def public_defaults(cls) -> "Limits":
        return cls(max_edges=60, max_vertices=60, default_timeout_s=10.0, max_timeout_s=20.0, public=True)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


class Workspace:
    """One visitor's hypergraph, decomposition and history, with its JSON views."""

    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.lock = threading.Lock()
        self.last_used = time.monotonic()
        self.session = OnlineSession(oracle_check=True, time_limit_s=limits.default_timeout_s)

    def _fresh(self) -> OnlineSession:
        s = self.session
        return OnlineSession(strategy=s.strategy, tighten=s.tighten, oracle_check=s.oracle_check,
                             time_limit_s=s.time_limit_s)

    def state(self) -> dict:
        s = self.session
        h, g = s.h, s.ghd
        ghd = None
        if g is not None and len(g):
            ghd = {"root": g.root, "nodes": [
                {"id": n.id, "bag": sorted(n.bag), "cover": sorted(n.cover),
                 "children": list(g.children(n.id))} for n in g]}
        last = dataclasses.asdict(s.history[-1]) if s.history else None
        return {
            "started": h is not None,
            "hypergraph": None if h is None else {
                "edges": {e: sorted(vs) for e, vs in sorted(h.edges.items())},
                "vertices": sorted(h.vertices)},
            "ghd": ghd, "k": s.k, "exact": s.exact,
            "valid": (validate(h, g).ok if h is not None and g is not None else None),
            "last": last,
            "history": [dataclasses.asdict(r) for r in s.history],
            "can_undo": bool(s._undo),
            "settings": {"strategy": s.strategy.value, "tighten": s.tighten,
                         "oracle": s.oracle_check, "timeout": s.time_limit_s},
            "limits": self.limits.as_dict(),
        }

    def _check_size(self, h: Hypergraph) -> None:
        lim = self.limits
        if len(h.edge_names) > lim.max_edges or len(h.vertices) > lim.max_vertices:
            raise InputError(f"too large for this site: at most {lim.max_edges} edges and "
                             f"{lim.max_vertices} vertices (the exact search is exponential)")

    def handle(self, path: str, req: dict) -> dict:
        s = self.session
        if path == "/api/start":
            h = parse_edge_text(str(req.get("text", "")))
            self._check_size(h)
            fresh = self._fresh()
            fresh.build(h)
            self.session = fresh
        elif path == "/api/modify":
            mod = build_modification(req)
            if s.h is not None:
                self._check_size(mod.apply(s.h).new)      # raises on an invalid modification too
            s.apply(mod)
        elif path == "/api/undo":
            if not s.undo():
                raise InputError("nothing to undo")
        elif path == "/api/reset":
            self.session = self._fresh()
        elif path == "/api/rebuild":
            if s.h is None:
                raise InputError("nothing to rebuild")
            s.build(s.h)
        elif path == "/api/settings":
            self._settings(s, req)
        else:
            raise InputError(f"unknown endpoint {path}")
        return self.state()

    def _settings(self, s: OnlineSession, req: dict) -> None:
        if "strategy" in req:
            if req["strategy"] not in STRATEGIES:
                raise InputError("strategy must be paper, theorem45 or recompute")
            s.strategy = STRATEGIES[req["strategy"]]
        if "tighten" in req:
            s.tighten = bool(req["tighten"])
        if "oracle" in req:
            s.oracle_check = bool(req["oracle"])
        if "timeout" in req:
            t, cap = req["timeout"], self.limits.max_timeout_s
            if t in (None, "", 0, "0", "off"):
                if cap is not None:
                    raise InputError(f"this site always uses a time limit (at most {cap:g} s)")
                s.time_limit_s = None
                return
            try:
                value = float(t)
            except (TypeError, ValueError):
                raise InputError("timeout must be a number of seconds, or empty for none") from None
            if value <= 0:
                raise InputError("timeout must be positive")
            if cap is not None and value > cap:
                raise InputError(f"the time limit on this site is at most {cap:g} s")
            s.time_limit_s = value


class App:
    """All workspaces. Locally (``limits.public`` False) every request shares one workspace, as
    before. Publicly each visitor gets their own, identified by a random cookie; workspaces idle
    for ``idle_s`` are dropped, and at most ``max_sessions`` are kept (least recently used out)."""

    COOKIE = "ghd_sid"

    def __init__(self, timeout_s: float | None = 30.0, *, limits: Limits | None = None,
                 max_sessions: int = 200, idle_s: float = 3600.0, secure_cookie: bool = False) -> None:
        self.limits = limits or dataclasses.replace(Limits(), default_timeout_s=timeout_s)
        self.max_sessions, self.idle_s, self.secure_cookie = max_sessions, idle_s, secure_cookie
        self._lock = threading.Lock()
        self._spaces: "OrderedDict[str, Workspace]" = OrderedDict()
        self._local = None if self.limits.public else Workspace(self.limits)

    def workspace(self, sid: str | None) -> tuple[Workspace, str | None]:
        """The visitor's workspace and, if a new cookie must be set, its value."""
        if self._local is not None:
            return self._local, None
        now = time.monotonic()
        with self._lock:
            for key in [k for k, w in self._spaces.items() if now - w.last_used > self.idle_s]:
                del self._spaces[key]
            if sid and sid in self._spaces:
                ws = self._spaces[sid]
                self._spaces.move_to_end(sid)
                ws.last_used = now
                return ws, None
            while len(self._spaces) >= self.max_sessions:
                self._spaces.popitem(last=False)
            sid = secrets.token_hex(16)
            ws = Workspace(self.limits)
            self._spaces[sid] = ws
            return ws, sid

    def cookie_header(self, sid: str) -> str:
        flags = "; Path=/; HttpOnly; SameSite=Lax" + ("; Secure" if self.secure_cookie else "")
        return f"{self.COOKIE}={sid}{flags}"

    @property
    def sessions(self) -> int:
        return len(self._spaces) if self._local is None else 1


@functools.lru_cache(maxsize=1)
def hyperbench_list(max_vertices: int = 16) -> list[dict]:
    """Small HyperBench instances (parsed once, on first use)."""
    if not HYPERBENCH_DIR.is_dir():
        return []
    out = []
    for p in sorted(HYPERBENCH_DIR.glob("*.hg")):
        try:
            h = parse_hyperbench(p.read_text(encoding="utf-8"))
        except (IGHDError, UnicodeDecodeError):
            continue
        if len(h.vertices) <= max_vertices:
            out.append({"name": p.name, "edges": len(h.edge_names), "vertices": len(h.vertices)})
    return out


def make_handler(app: App):

    class Handler(BaseHTTPRequestHandler):
        server_version = "ighd-web"

        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        new_cookie: str | None = None

        def _workspace(self) -> Workspace:
            sid = None
            for part in (self.headers.get("Cookie") or "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == App.COOKIE and re.fullmatch(r"[0-9a-f]{32}", value):
                    sid = value
            ws, new = app.workspace(sid)
            self.new_cookie = new
            return ws

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if self.new_cookie:
                self.send_header("Set-Cookie", app.cookie_header(self.new_cookie))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path.startswith("/static/") and path[len("/static/"):] in STATIC_FILES:
                name = path[len("/static/"):]
                self._send(200, (STATIC / name).read_bytes(), STATIC_FILES[name])
            elif path == "/healthz":
                self._json(200, {"ok": True})
            elif path == "/api/state":
                ws = self._workspace()
                with ws.lock:
                    self._json(200, ws.state())
            elif path == "/api/examples":
                self._json(200, EXAMPLES)
            elif path == "/api/hyperbench":
                self._json(200, hyperbench_list())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?")[0]
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._json(413, {"error": "request too large"})
            try:
                req = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(req, dict):
                    raise InputError("expected a JSON object")
            except (json.JSONDecodeError, UnicodeDecodeError, InputError) as exc:
                return self._json(400, {"error": f"bad request: {exc}"})
            if path == "/api/hyperbench":
                name = req.get("name")
                if name not in {b["name"] for b in hyperbench_list()}:
                    return self._json(400, {"error": "unknown HyperBench instance"})
                text = (HYPERBENCH_DIR / name).read_text(encoding="utf-8")
                h = parse_hyperbench(text)
                lines = "\n".join(f"{e}: {' '.join(sorted(vs))}" for e, vs in sorted(h.edges.items()))
                return self._json(200, {"text": lines})
            ws = self._workspace()
            with ws.lock:
                try:
                    state = ws.handle(path, req)
                except (IGHDError, ValueError) as exc:
                    return self._json(400, {"error": str(exc), "state": ws.state()})
                self._json(200, state)

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Web interface for online GHD maintenance")
    ap.add_argument("--public", action="store_true",
                    help="host for anyone: a private session per visitor, size and time limits, "
                         "listen on all interfaces (also enabled by the environment variable GHD_PUBLIC=1)")
    ap.add_argument("--host", default=None, help="interface to listen on (default 127.0.0.1; 0.0.0.0 with --public)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)),
                    help="port (default: $PORT if set, else 8765)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--timeout", type=float, default=30.0,
                    help="time limit per search in seconds (0 = none); default 30 (ignored with --public)")
    a = ap.parse_args(argv)
    public = a.public or os.environ.get("GHD_PUBLIC") == "1"
    if public:
        app = App(limits=Limits.public_defaults(), secure_cookie=True)
        host = a.host or "0.0.0.0"
    else:
        app = App(timeout_s=a.timeout or None)
        host = a.host or "127.0.0.1"
    server = ThreadingHTTPServer((host, a.port), make_handler(app))
    url = f"http://127.0.0.1:{a.port}/"
    mode = "public mode (per-visitor sessions, limits on)" if public else "local mode"
    print(f"Online GHD web interface running at {url} on {host}, {mode}  (Ctrl+C to stop)", flush=True)
    if not a.no_browser and not public:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

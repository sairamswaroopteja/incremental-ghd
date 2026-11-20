"""The web interface's JSON API (ighd.online.web), exercised over real HTTP on a free local port."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ighd.ghd import GHD, validate
from ighd.hypergraph import Hypergraph
from ighd.online.web import App, InputError, make_handler, parse_edge_text
from ighd.oracle import exact_ghw


@pytest.fixture()
def server():
    app = App(timeout_s=None)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def call(base: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if "json" in r.headers["Content-Type"] else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def ghd_of(state: dict) -> GHD:
    g = state["ghd"]
    nodes = {str(n["id"]): (n["bag"], n["cover"]) for n in g["nodes"]}
    children = {str(n["id"]): [str(c) for c in n["children"]] for n in g["nodes"]}
    return GHD.from_spec({"root": str(g["root"]), "nodes": nodes, "children": children})


def check_state(state: dict) -> None:
    """The served decomposition is a valid GHD of the served hypergraph, of width k = ghw."""
    h = Hypergraph(state["hypergraph"]["edges"])
    rep = validate(h, ghd_of(state))
    assert rep.ok and rep.width == state["k"], rep.violations
    assert state["valid"] is True
    assert state["exact"] and state["k"] == exact_ghw(h)[0]


def test_page_and_examples(server) -> None:
    code, page = call(server, "/")
    assert code == 200 and "Incremental GHD" in page
    for name, marker in [("style.css", "--width"), ("app.js", "function render")]:
        req = urllib.request.Request(f"{server}/static/{name}")
        with urllib.request.urlopen(req, timeout=10) as r:
            assert r.status == 200 and marker in r.read().decode()
    for bad in ["/static/../web.py", "/static/index.html", "/static/nope.js"]:
        assert call(server, bad)[0] == 404, bad          # allow-list only
    code, ex = call(server, "/api/examples")
    assert code == 200 and len(ex) >= 3
    for x in ex:
        parse_edge_text(x["text"])
    assert call(server, "/api/nope")[0] == 404


def test_full_session_every_modification(server) -> None:
    code, st = call(server, "/api/start", {"text": "e1: a b\ne2: b c\ne3: c d"})
    assert code == 200 and st["k"] == 1 and st["last"]["status"] == "built"
    check_state(st)
    steps = [
        ({"kind": "AddConstr", "name": "e4", "vertices": ["d", "a"]}, "proven_no", 2),
        ({"kind": "AddVar", "vertex": "x", "edges": ["e1", "e3"]}, "updated", 2),
        ({"kind": "AddEq", "merge": ["b", "c"], "into": "b"}, "updated", None),
        ({"kind": "DelEq", "vertex": "b", "parts": {"b": ["e1", "e2"], "c": ["e2", "e3"]}}, "updated", None),
        ({"kind": "DelVar", "vertex": "x"}, "updated", None),
        ({"kind": "DelConstr", "name": "e4"}, "updated", 1),
    ]
    for body, status, k in steps:
        code, st = call(server, "/api/modify", body)
        assert code == 200, st
        assert st["last"]["status"] == status, (body, st["last"])
        if k is not None:
            assert st["k"] == k, body
        check_state(st)
        assert set(st["last"]["changed_edges"]) <= set(st["hypergraph"]["edges"])
    assert len(st["history"]) == 1 + len(steps)


def test_errors_leave_state_unchanged(server) -> None:
    call(server, "/api/start", {"text": "e1(a,b), e2(b,c)."})
    _, before = call(server, "/api/state")
    for body in [{"kind": "AddVar", "vertex": "z", "edges": ["nope"]},
                 {"kind": "AddEq", "merge": [], "into": "a"},
                 {"kind": "DelConstr", "name": "e1 e2"},
                 {"kind": "Frobnicate"},
                 {"kind": "DelEq", "vertex": "b", "parts": {"b": ["e1"]}}]:
        code, res = call(server, "/api/modify", body)
        assert code == 400 and res["error"], body
    _, after = call(server, "/api/state")
    assert after["hypergraph"] == before["hypergraph"] and after["k"] == before["k"]
    assert call(server, "/api/start", {"text": ""})[0] == 400
    assert call(server, "/api/start", {"text": "e1: a b\ne1: c d"})[0] == 400
    assert call(server, "/api/settings", {"strategy": "magic"})[0] == 400
    assert call(server, "/api/settings", {"timeout": "soon"})[0] == 400


def test_undo_reset_settings(server) -> None:
    call(server, "/api/start", {"text": "e1: a b\ne2: b c\ne3: c a"})
    _, st = call(server, "/api/modify", {"kind": "DelConstr", "name": "e3"})
    assert st["k"] == 1 and st["can_undo"]
    _, st = call(server, "/api/undo", {})
    assert st["k"] == 2 and "e3" in st["hypergraph"]["edges"]
    _, st = call(server, "/api/settings", {"strategy": "recompute", "oracle": False, "timeout": "5"})
    assert st["settings"] == {"strategy": "recompute", "tighten": True, "oracle": False, "timeout": 5.0}
    _, st = call(server, "/api/settings", {"timeout": ""})
    assert st["settings"]["timeout"] is None
    _, st = call(server, "/api/reset", {})
    assert not st["started"] and st["settings"]["strategy"] == "recompute"


def test_parse_edge_text_formats() -> None:
    assert parse_edge_text("e1: a b c\n# comment\ne2 c, d").edges == {"e1": fs("abc"), "e2": fs("cd")}
    assert parse_edge_text("e1(a,b), e2(b,c).").edges == {"e1": fs("ab"), "e2": fs("bc")}
    for bad in ["", "e1", "e1: a\ne1: b"]:
        with pytest.raises((InputError, ValueError)):
            parse_edge_text(bad)


def fs(xs: str) -> frozenset[str]:
    return frozenset(xs)

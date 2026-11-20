"""Public (hosted) mode of the web interface: one private workspace per visitor, size and time
limits, health check. Exercised over real HTTP with separate cookie jars per simulated visitor."""

from __future__ import annotations

import http.cookiejar
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from ighd.online.web import App, Limits, make_handler


def serve(app: App):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture()
def public():
    app = App(limits=Limits.public_defaults(), secure_cookie=False)   # plain http in tests
    srv, base = serve(app)
    yield app, base
    srv.shutdown()
    srv.server_close()


class Visitor:
    """A browser: its own cookie jar."""

    def __init__(self, base: str) -> None:
        self.base = base
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode()), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode()), e.headers


def test_visitors_have_private_workspaces(public) -> None:
    app, base = public
    alice, bob = Visitor(base), Visitor(base)
    code, st, headers = alice.call("/api/start", {"text": "e1: a b\ne2: b c\ne3: c a"})
    assert code == 200 and st["k"] == 2
    cookie = headers.get("Set-Cookie")
    assert cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    _, st_bob, _ = bob.call("/api/state")
    assert st_bob["started"] is False                       # Bob does not see Alice's hypergraph
    bob.call("/api/start", {"text": "e1: x y"})
    _, st_alice, _ = alice.call("/api/state")
    assert set(st_alice["hypergraph"]["edges"]) == {"e1", "e2", "e3"} and st_alice["k"] == 2
    _, st_bob, _ = bob.call("/api/state")
    assert st_bob["hypergraph"]["edges"] == {"e1": ["x", "y"]} and st_bob["k"] == 1
    assert app.sessions == 2
    assert st_bob["limits"]["public"] is True


def test_public_limits_are_enforced(public) -> None:
    _, base = public
    v = Visitor(base)
    big = "\n".join(f"e{i}: v{i} v{i + 1}" for i in range(61))           # 61 edges > 60
    code, res, _ = v.call("/api/start", {"text": big})
    assert code == 400 and "at most 60 edges" in res["error"]
    code, st, _ = v.call("/api/start", {"text": "e1: a b"})
    assert code == 200 and st["settings"]["timeout"] == 10.0             # public default
    code, res, _ = v.call("/api/settings", {"timeout": ""})
    assert code == 400 and "always uses a time limit" in res["error"]
    code, res, _ = v.call("/api/settings", {"timeout": "60"})
    assert code == 400 and "at most 20" in res["error"]
    code, st, _ = v.call("/api/settings", {"timeout": "5"})
    assert code == 200 and st["settings"]["timeout"] == 5.0
    # a modification may not grow the hypergraph past the limit either
    at_limit = [f"e{i}: v{i} v{i + 1}" for i in range(59)] + ["e59: v0 v1"]   # 60 edges, 60 vertices
    code, st, _ = v.call("/api/start", {"text": "\n".join(at_limit)})
    assert code == 200 and len(st["hypergraph"]["edges"]) == 60
    code, res, _ = v.call("/api/modify", {"kind": "AddConstr", "name": "extra", "vertices": ["v0", "v5"]})
    assert code == 400 and "at most 60 edges" in res["error"]


def test_health_check_and_bad_cookie(public) -> None:
    _, base = public
    v = Visitor(base)
    code, body, _ = v.call("/healthz")
    assert code == 200 and body == {"ok": True}
    req = urllib.request.Request(base + "/api/state", headers={"Cookie": "ghd_sid=../../etc; other=1"})
    with urllib.request.urlopen(req, timeout=10) as r:          # malformed id: a new session, no error
        assert r.status == 200 and "ghd_sid=" in (r.headers.get("Set-Cookie") or "")


def test_session_cap_and_idle_expiry() -> None:
    app = App(limits=Limits.public_defaults(), max_sessions=3, idle_s=3600)
    ids = [app.workspace(None)[1] for _ in range(5)]
    assert app.sessions == 3                                    # least recently used dropped
    assert app.workspace(ids[-1])[1] is None                    # the newest is still known
    _, again = app.workspace(ids[0])
    assert again is not None                                    # the oldest was evicted: new id
    app2 = App(limits=Limits.public_defaults(), idle_s=60.0)
    sid = app2.workspace(None)[1]
    app2._spaces[sid].last_used -= 61                           # pretend it was idle for 61 s
    assert app2.workspace(sid)[1] is not None                   # expired: a new id is issued


def test_secure_cookie_flag_in_production() -> None:
    app = App(limits=Limits.public_defaults(), secure_cookie=True)
    assert app.cookie_header("0" * 32).endswith("; Secure")


def test_local_mode_shares_one_workspace() -> None:
    app = App(timeout_s=None)
    a, ca = app.workspace(None)
    b, cb = app.workspace("f" * 32)
    assert a is b and ca is None and cb is None and app.sessions == 1

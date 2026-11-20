"""The runnable examples in examples/ stay working (S15)."""

from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "examples" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_walkthrough_runs(capsys) -> None:
    mod = _load("walkthrough")
    mod.part1()
    mod.part2()
    mod.part3()
    out = capsys.readouterr().out
    assert "T* = {u1,u2}" in out and "BAD" not in out
    assert "status = proven_no" in out and "validator refused it" in out


def test_modifications_tour_agrees_with_oracle_and_draws(tmp_path, capsys) -> None:
    log = _load("modifications_tour").tour(str(tmp_path / "tour.png"))   # asserts oracle agreement
    assert [(r["before"], r["after"]) for r in log][:5] == [(1, 2), (2, 2), (2, 2), (2, 2), (2, 3)]
    assert {r["kind"] for r in log} == {"AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq"}
    assert (tmp_path / "tour.png").stat().st_size > 10_000


def test_quickstart_runs_and_every_answer_is_an_update() -> None:
    mod = _load("quickstart")
    log = mod.main()               # asserts validity of every UPDATED output itself
    assert [s for _, s, _ in log] == ["updated"] * 5
    assert all(w is not None and w <= 2 for _, _, w in log)

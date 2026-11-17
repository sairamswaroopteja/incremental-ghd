"""The runnable examples in examples/ stay working (S15)."""

from __future__ import annotations

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_quickstart_runs_and_every_answer_is_an_update() -> None:
    spec = importlib.util.spec_from_file_location("quickstart", ROOT / "examples" / "quickstart.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    log = mod.main()               # asserts validity of every UPDATED output itself
    assert [s for _, s, _ in log] == ["updated"] * 5
    assert all(w is not None and w <= 2 for _, _, w in log)

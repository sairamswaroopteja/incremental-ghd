"""S14 benchmark framework: the paper's §6 comparison protocol (Update vs Classic).

Not part of the ``ighd`` package. ``python -m benchmarks.run`` works from a checkout without an
install step: if ``ighd`` is not importable, ``<project>/src`` is put on ``sys.path`` (the same
layout pytest uses via ``pythonpath = ["src", "."]``).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "benchmarks" / "data" / "hyperbench" / "all"
RESULTS_DIR = PROJECT_ROOT / "benchmarks" / "results"

try:  # pragma: no cover - depends on how the interpreter was started
    import ighd  # noqa: F401
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

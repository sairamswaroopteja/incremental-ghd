"""Launcher for the online, query-based GHD system (no install needed):

    python online.py                    type the hypergraph and modifications interactively
    python online.py --load file.hg     start from a HyperBench file
    python online.py --help             all options
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from ighd.online.cli import main  # noqa: E402

raise SystemExit(main())

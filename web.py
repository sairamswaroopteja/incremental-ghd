"""Launcher for the web interface of the online GHD system (no install needed):

    python web.py                       opens http://127.0.0.1:8765 in your browser
    python web.py --port 9000 --no-browser --timeout 0
    python web.py --public              hosted mode (used on Render, see render.yaml): a private
                                        session per visitor, size and time limits, listens on
                                        0.0.0.0 and on $PORT
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from ighd.online.web import main  # noqa: E402

raise SystemExit(main())

"""Make ``app.*`` and ``ui.*`` importable for the UI's pure-logic tests.

``backend`` must come first: ``streamlit_app/app.py`` would otherwise shadow the
backend's ``app`` package, which is exactly the clash the app's own bootstrap
avoids by adding ``backend/`` before its own directory.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = str(_ROOT / "backend")
_UI = str(_ROOT / "streamlit_app")

if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
if _UI not in sys.path:
    sys.path.append(_UI)

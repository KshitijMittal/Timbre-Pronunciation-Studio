"""Make ``app.*`` (backend) and the streamlit app's modules importable in tests.

``backend`` must come first: ``streamlit_app/app.py`` would otherwise shadow the
backend's ``app`` package, which is exactly the clash the app's own bootstrap
avoids by adding ``backend/`` before its own directory.
"""

import sys
from pathlib import Path

import pytest
import streamlit as st

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = str(_ROOT / "backend")
_APP = str(_ROOT / "streamlit_app")

if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
if _APP not in sys.path:
    sys.path.append(_APP)


@pytest.fixture(autouse=True)
def fresh_caches():
    """``services()`` is cached per process; tests must not share a data dir."""
    st.cache_resource.clear()
    st.cache_data.clear()
    yield
    st.cache_resource.clear()
    st.cache_data.clear()

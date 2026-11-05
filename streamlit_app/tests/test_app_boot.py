"""Boot the real Streamlit app once, against a placeholder key and a temp data folder.

The rest of the UI tests import modules directly. This is the only test that runs
``app.py`` end to end, so it catches the failures a module import cannot: a wrong
import order, a missing session-state key, a page that raises on first render.

No credit can be spent: nothing is clicked, and ``GNANI_API_KEY`` is a placeholder
that the app only stores for a later Generate.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_boots_and_seeds_a_fresh_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GNANI_API_KEY", "placeholder-not-a-real-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    app = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not app.exception
    assert app.title[0].value == "Timbre Pronunciation Studio"
    assert (tmp_path / "dictionaries").is_dir()
    assert app.session_state["script"]
    assert app.session_state["active_dictionary_id"]

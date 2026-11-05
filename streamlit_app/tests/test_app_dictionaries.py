"""Dictionary create/delete through the real dialogs, against a temp store.

Dialogs are re-opened by their pending flag on each run: Streamlit closes a
dialog on the next full run, and AppTest runs the whole script every time.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.core.dictionary_store import DictionaryStore

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("GNANI_API_KEY", "placeholder-not-a-real-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not run.exception
    return run, DictionaryStore(tmp_path)


def test_the_plus_opens_the_new_dictionary_dialog_with_import_inside(app):
    run, _ = app

    run.button(key="dict_new").click().run()

    assert not run.exception
    assert run.text_input(key="new_name_0")
    assert run.button(key="new_import")


def test_creating_a_dictionary_writes_it_and_selects_it(app):
    run, store = app

    run.button(key="dict_new").click().run()
    run.text_input(key="new_name_0").set_value("Brand names")
    run.session_state["pending_new"] = True
    run.button(key="create_dictionary").click().run()

    assert not run.exception
    dictionaries, _ = store.list_all()
    assert sorted(d.name for d in dictionaries) == ["Brand names", "Gnani Demo"]
    created = next(d for d in dictionaries if d.name == "Brand names")
    assert run.session_state["active_id"] == created.id


def test_deleting_a_dictionary_removes_its_file(app):
    run, store = app
    dictionaries, _ = store.list_all()
    target = dictionaries[0]

    run.button(key=f"ask_delete_{target.id}").click().run()
    run.session_state["pending_delete"] = target.id
    run.button(key="confirm_delete").click().run()

    assert not run.exception
    assert [d.id for d in store.list_all()[0]] == []
    assert run.session_state["active_id"] is None

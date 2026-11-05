"""The rule editor through the real widgets: add, save, cancel.

Drives ``app.py`` with AppTest. Saving writes to the temp store, so these tests
prove the editor's contract, not just its rendering. No synthesis is involved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from app.core.dictionary_store import DictionaryStore

APP = Path(__file__).resolve().parents[1] / "app.py"


def row_input(run: AppTest, index: int, field: str):
    """Find a draft cell by position: the sequence number changes on every reload."""
    return next(
        t for t in run.text_input
        if t.key.startswith("rule_") and t.key.endswith(f"_{index}_{field}")
    )


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("GNANI_API_KEY", "placeholder-not-a-real-key")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    run = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not run.exception
    return run, DictionaryStore(tmp_path)


def test_editing_a_row_and_saving_persists_it(app):
    run, store = app
    dictionary_id = run.session_state["active_id"]

    row_input(run, 0, "says").set_value("Tim-ber!").run()
    assert run.button(key="save_rules").disabled is False

    run.button(key="save_rules").click().run()

    assert not run.exception
    stored = store.get(dictionary_id)
    assert stored.rules[0].replacement == "Tim-ber!"
    # The saved draft reloads under a new sequence, and nothing is dirty.
    assert run.button(key="save_rules").disabled is True


def test_cancel_restores_the_stored_rules(app):
    run, store = app
    dictionary_id = run.session_state["active_id"]

    row_input(run, 0, "says").set_value("wrong").run()
    run.button(key="cancel_rules").click().run()

    assert not run.exception
    assert store.get(dictionary_id).rules[0].replacement == "Tim-ber"
    assert row_input(run, 0, "says").value == "Tim-ber"


def test_adding_a_rule_is_a_draft_until_it_is_saved(app):
    run, store = app
    dictionary_id = run.session_state["active_id"]

    run.text_input(key="add_term_0").set_value("Kubernetes")
    run.text_input(key="add_says_0").set_value("Koo-ber-NET-eez")
    next(b for b in run.button if b.label == "Add rule").click().run()

    assert not run.exception
    assert [row["source"] for row in run.session_state["draft_rows"]][-1] == "Kubernetes"
    assert len(store.get(dictionary_id).rules) == 3
    assert run.button(key="save_rules").disabled is False


def test_a_duplicate_term_is_refused_before_it_reaches_the_draft(app):
    run, store = app
    dictionary_id = run.session_state["active_id"]

    run.text_input(key="add_term_0").set_value("timbre")
    run.text_input(key="add_says_0").set_value("Tim-ber")
    next(b for b in run.button if b.label == "Add rule").click().run()

    assert not run.exception
    assert len(run.session_state["draft_rows"]) == 3
    assert store.get(dictionary_id).rules[0].replacement == "Tim-ber"

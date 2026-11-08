"""Boot the real Streamlit app against a placeholder key and a temp data folder.

No credit can be spent: nothing is clicked, and ``GNANI_API_KEY`` is a placeholder
that the app only stores for a later Generate.
"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from app.core.dictionary_store import DictionaryStore
from seed import SAMPLE_SCRIPT, SEED_NAME, SEED_RULES

APP = Path(__file__).resolve().parents[1] / "app.py"


def boot(monkeypatch, data_dir: Path) -> AppTest:
    monkeypatch.setenv("GNANI_API_KEY", "placeholder-not-a-real-key")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    return AppTest.from_file(str(APP), default_timeout=60).run()


def test_first_run_seeds_the_verified_dictionary_and_sample_script(monkeypatch, tmp_path):
    app = boot(monkeypatch, tmp_path)

    assert not app.exception
    assert app.session_state["seeded"] is True

    dictionaries, warnings = DictionaryStore(tmp_path).list_all()
    assert warnings == []
    assert [d.name for d in dictionaries] == [SEED_NAME]
    assert [(r.source, r.replacement) for r in dictionaries[0].rules] == list(SEED_RULES)

    assert app.session_state["active_id"] == dictionaries[0].id
    assert app.text_area(key="script_text").value == SAMPLE_SCRIPT


def test_script_meter_tracks_use_and_flags_the_warn_threshold(monkeypatch, tmp_path):
    app = boot(monkeypatch, tmp_path)

    app.text_area(key="script_text").set_value("x" * 1000).run()
    warn = next(h.value for h in app.html if "char-meter" in h.value)
    assert "1,000 / 2,000 characters" in warn
    assert "script-count is-warn" in warn

    app.text_area(key="script_text").set_value("x" * 2100).run()
    over = next(h.value for h in app.html if "char-meter" in h.value)
    assert "script-count is-over" in over
    assert any("2100 characters" in e.value for e in app.error)


def test_the_live_counter_bridge_mirrors_the_script_field_and_its_limits(
    monkeypatch, tmp_path
):
    app = boot(monkeypatch, tmp_path)

    bridge = app.get("iframe")[0].proto.srcdoc
    assert ".st-key-script_text" in bridge
    assert "LIMIT = 2000, WARN = 800" in bridge


def test_a_clip_from_an_older_draft_is_dropped(monkeypatch, tmp_path):
    app = boot(monkeypatch, tmp_path)
    app.session_state["audio_result"] = {
        "sig": ("old text", "old transformed text", "m", "v"),
        "original": b"",
        "adjusted": b"",
        "original_cached": True,
        "adjusted_cached": True,
    }

    app.run()

    assert not app.exception
    assert app.session_state["audio_result"] is None


def test_generate_is_disabled_when_no_rule_matches(monkeypatch, tmp_path):
    app = boot(monkeypatch, tmp_path)
    app.text_area(key="script_text").set_value("Nothing to change here.").run()

    assert not app.exception
    assert app.button(key="generate").disabled is True
    assert any("No rules matched" in c.value for c in app.caption)


def test_a_later_session_keeps_the_dictionary_but_starts_with_an_empty_editor(
    monkeypatch, tmp_path
):
    boot(monkeypatch, tmp_path)

    app = boot(monkeypatch, tmp_path)

    assert not app.exception
    dictionaries, _ = DictionaryStore(tmp_path).list_all()
    assert len(dictionaries) == 1
    assert app.session_state["active_id"] == dictionaries[0].id
    assert app.text_area(key="script_text").value == ""

"""Session-state helpers (``TRD`` §12.2).

Kept free of ``app.*`` imports so it can be imported and tested on its own.
"""

from __future__ import annotations

import streamlit as st

_DEFAULTS: dict[str, object] = {
    # Domain state (TRD §12.2)
    "dictionaries": [],
    "active_dictionary_id": None,
    "rules": [],
    "script": "",
    "transform_result": None,
    "audio_result": None,
    "settings_snapshot": None,
    "audio_notice": None,
    "error": None,
    "store_warnings": [],
    # Rule-table drafts (App Flow §7): edits and new rows live here until Save.
    # The table key carries a sequence so Save/Cancel can replace the widget's
    # own state instead of leaving discarded cells behind.
    "rule_drafts": [],
    "rule_drafts_dictionary": None,
    "rule_table_seq": 0,
    "ui_rule_delete_open": False,
    "delete_rule_id": None,
    # Voice settings — widget keys, seeded from backend/.env on first run
    "model": "",
    "voice": "",
    # Sidebar form state (App Flow §6). The *_seq counters give each opening of
    # the inline form a fresh widget key, so a cancelled or failed attempt
    # cannot leak its old text into the next one.
    "form_error": None,
    "ui_new_open": False,
    "ui_new_seq": 0,
    "ui_rename_open": False,
    "ui_rename_seq": 0,
    "ui_delete_open": False,
    # First-run seed flag: false until the seed attempt succeeds, so a failed
    # attempt is retried on the next rerun rather than leaving no dictionary.
    "seeded": False,
    # Set while synthesis is in flight; settings lock the sidebar (App Flow §4)
    "busy": False,
}


def init_state() -> None:
    """Create missing keys only.

    ``setdefault`` rather than assignment: assignment would wipe the user's
    script and rules on every Streamlit rerun.
    """
    for key, value in _DEFAULTS.items():
        st.session_state.setdefault(key, value)


def show_error(exc: Exception) -> None:
    """Park the last ``AppError`` so it survives the next rerun.

    ``App Flow`` §11: the banner is dismissible but never auto-dismissing, and it
    never replaces existing results. Storing it in session state is what makes
    both true.
    """
    st.session_state.error = exc


def dismiss_error() -> None:
    st.session_state.error = None


def clear_audio(reason: str | None = None) -> None:
    """Drop both players (FR-21).

    Called whenever model or voice changes: an "Adjusted" player generated with
    a different voice is worse than no player at all (``App Flow`` §9.1).
    """
    st.session_state.audio_result = None
    st.session_state.settings_snapshot = None
    st.session_state.audio_notice = reason

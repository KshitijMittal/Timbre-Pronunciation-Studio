"""Timbre Pronunciation Studio — Streamlit entry point.

One process, no HTTP layer: the UI imports ``backend/app/core/`` directly
(``TRD`` §12.4). The bootstrap below must stay at the top, before any
``from app...`` import, because Streamlit does not reliably put ``backend/`` on
``sys.path`` (``TRD`` §16.2).

Both directories are added explicitly: ``backend/`` so ``app.*`` imports resolve,
and this script's own directory so ``state`` and ``ui`` resolve. ``streamlit
run`` usually adds the latter itself, but ``streamlit.testing.v1.AppTest`` does
not, and the app must behave identically under both.
"""

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path[:0] = [str(_HERE.parents[1] / "backend"), str(_HERE.parent)]

import streamlit as st

from app.config import load_settings
from app.core.audio_cache import AudioCache
from app.core.dictionary_store import DictionaryStore
from app.core.gnani_tts import TimbreClient
from app.errors import AppError

from seed import SAMPLE_SCRIPT, ensure_seed
from state import dismiss_error, init_state, show_error
from ui import audio, dictionaries, editor, preview, rules
from ui import settings as settings_ui

LIMITATION_NOTE = (
    "This is text substitution, not phoneme control. Your replacement text is "
    "what Timbre receives. The original wording is kept only for display."
)

st.set_page_config(page_title="Timbre Pronunciation Studio", layout="wide")


@st.cache_resource
def services():
    """Build the domain objects once per process, not once per rerun.

    ``AudioCache`` holds the in-memory tier that makes replaying a clip free
    (FR-28), so rebuilding it on every interaction would quietly discard it.
    """
    settings = load_settings()
    return (
        settings,
        DictionaryStore(settings.data_dir),
        AudioCache(settings.data_dir / "audio"),
        TimbreClient(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout_seconds=settings.timeout_seconds,
        ),
    )


try:
    settings, store, cache, client = services()
except AppError as exc:
    # FR-31 / NFR-07: a missing key fails at startup with the canonical message,
    # not on the first click after the user has typed a script.
    st.error(exc.message)
    st.caption(f"{exc.status_code} · {exc.error_type}")
    st.stop()

init_state()
settings_ui.ensure(settings)

# First run only: seed the three verified Gate B rules and preload the sample
# script (App Flow §5). A later browser session starts with an empty editor but
# keeps the dictionary, because dictionaries are files on disk (TRD §12.6).
if not st.session_state.seeded:
    try:
        created = ensure_seed(store)
    except AppError as exc:
        # Left unseeded so the next rerun retries rather than leaving the app
        # with no dictionary and no explanation.
        show_error(exc)
    else:
        st.session_state.seeded = True
        if created is not None:
            st.session_state.script = SAMPLE_SCRIPT
            st.session_state.active_dictionary_id = created.id

dictionaries.refresh(store)

st.title("Timbre Pronunciation Studio")

# One dismissible banner at the top of the main column, never auto-dismissed and
# never replacing existing results (App Flow §4, §11).
if st.session_state.error is not None:
    error = st.session_state.error
    st.error(getattr(error, "message", str(error)))
    status_code = getattr(error, "status_code", None)
    error_type = getattr(error, "error_type", None)
    if status_code is not None and error_type is not None:
        st.caption(f"{status_code} · {error_type}")
    st.button("Dismiss", key="dismiss_error", on_click=dismiss_error)

has_dictionaries = dictionaries.render(store)
settings_ui.render(settings)

# Permanent, non-dismissible honesty note (US-09, UI-UX §8.4).
st.sidebar.info(LIMITATION_NOTE)

if has_dictionaries:
    # Script → Rules → Preview, the panel order in UI-UX §8. The transform is
    # computed once between the editor and the table, because both the Matches
    # column and the preview report must describe the same draft rules.
    count, limit_status = editor.render(settings)
    drafts = rules.prepare()
    transform, blocked = preview.compute(settings, count, limit_status, drafts)
    rules.render(store, transform)
    preview.render(settings, count, limit_status, drafts, transform, blocked)
    audio.render(settings, cache, client, transform, blocked)
else:
    dictionaries.render_empty_state()

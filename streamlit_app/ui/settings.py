"""Sidebar voice settings (``App Flow`` §3, §9.1; ``TRD`` §12.3).

Model and Voice are the only editable rows. Language and Speed are fixed for this
release (FR-19) and are shown as read-only text rather than disabled controls, so
they cannot look like something the user broke.
"""

from __future__ import annotations

import streamlit as st

from app.catalogue import MODELS, find_model
from app.config import Settings

from state import clear_audio

SETTINGS_CHANGED = "Settings changed — regenerate to compare"


def ensure(settings: Settings) -> None:
    """Seed the widget keys from configuration on first run.

    Runs before any widget is instantiated, so assigning the keys is safe. If the
    configured default is not in the catalogue, the first catalogue model is used
    rather than rendering a selectbox with a value it does not contain.
    """
    model = find_model(st.session_state.get("model") or settings.default_model)
    if model is None:
        model = find_model(settings.default_model) or MODELS[0]

    st.session_state.model = model.id
    if model.voice(st.session_state.get("voice") or "") is None:
        st.session_state.voice = model.default_voice


def render(settings: Settings) -> None:
    busy = bool(st.session_state.busy)

    st.sidebar.subheader("Voice settings")
    if busy:
        st.sidebar.caption("Locked while generating")

    labels = {model.id: model.label for model in MODELS}
    st.sidebar.selectbox(
        "Model",
        options=[model.id for model in MODELS],
        format_func=lambda model_id: labels[model_id],
        key="model",
        disabled=busy,
        on_change=_on_model_change,
    )

    model = find_model(st.session_state.model) or MODELS[0]
    st.sidebar.selectbox(
        "Voice",
        options=[voice.id for voice in model.voices],
        key="voice",
        disabled=busy,
        on_change=_on_voice_change,
    )

    st.sidebar.caption(f"Language · {settings.language}")
    st.sidebar.caption(f"Speed · {settings.speed:g}× · Fixed for this release")


def _on_model_change() -> None:
    """A model change resets the voice to that model's default (FR-18).

    Voices are not shared between models, so keeping the old one would select a
    voice the new model cannot speak.
    """
    model = find_model(st.session_state.model)
    if model is None:
        return
    st.session_state.voice = model.default_voice
    _drop_audio()


def _on_voice_change() -> None:
    _drop_audio()


def _drop_audio() -> None:
    """Clear a stale comparison, but only announce it if one existed (FR-21)."""
    had_audio = st.session_state.audio_result is not None
    clear_audio(SETTINGS_CHANGED if had_audio else None)

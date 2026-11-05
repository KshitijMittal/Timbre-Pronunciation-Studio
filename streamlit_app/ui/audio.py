"""Audio panel: Generate comparison, two players, settings echo.

``App Flow`` §9, ``UI-UX Brief`` §8.8/§8.9. This is the only place in the UI that
can spend credits. Synthesis runs solely inside the branch that handles a click
on **Generate comparison** — no auto-generation on load, on a script change or on
a rule change (FR-23, Flow 5's credit-safety rule).

Two framework limits shape the module, both recorded in ``TRD`` §12.3/§12.5 and
``docs/LIMITATIONS.md``:

* A Streamlit button cannot be relabelled while its own click handler is running,
  so the pressed control is swapped for a disabled ``Generating…`` button in a
  placeholder, alongside the ``st.status`` line ("Generating original…" then
  "Generating adjusted…").
* A dashed placeholder box is impossible without ``unsafe_allow_html``, so an
  empty audio block is a bordered container with the canonical muted text.

The cache-first sequence is ``AudioCache.get_or_synthesize``, the same helper
``api/synthesize.py`` uses, so the API and the UI cannot drift on the cache key or
the sidecar shape (``TRD`` §12.4, §11.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import streamlit as st

from app.config import Settings
from app.core.audio_cache import AudioCache, Clip
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG, TimbreClient
from app.core.pronunciation_rules import TransformResult
from app.errors import AppError

from state import clear_audio, show_error
from ui.preview import BLOCKED_EMPTY, BLOCKED_LIMIT, EMPTY_PREVIEW, NO_MATCH
from ui.settings import SETTINGS_CHANGED

GENERATE_LABEL = "Generate comparison"
GENERATING_LABEL = "Generating…"
ORIGINAL_LABEL = "Original"
ADJUSTED_LABEL = "Adjusted"
NOT_GENERATED = "Not generated yet"
GENERATING_ORIGINAL = "Generating original…"
GENERATING_ADJUSTED = "Generating adjusted…"
STEP_ONE = "1 of 2"
STEP_TWO = "2 of 2"
TEXT_CHANGED = "Script or rules changed — regenerate to compare"


@dataclass(frozen=True, slots=True)
class Snapshot:
    """The model, voice, language and speed frozen at click time (FR-21)."""

    model: str
    voice: str
    language: str
    speed: float


@dataclass(frozen=True, slots=True)
class AudioPair:
    """The players. ``adjusted`` is ``None`` when only the original succeeded."""

    original: bytes
    adjusted: bytes | None


@dataclass(frozen=True, slots=True)
class PairOutcome:
    """What :func:`generate_pair` produced, including the failing half."""

    original: bytes | None
    adjusted: bytes | None
    error: AppError | None
    failed_step: str | None


def current_snapshot(settings: Settings) -> Snapshot:
    return Snapshot(
        model=st.session_state.model,
        voice=st.session_state.voice,
        language=settings.language,
        speed=float(settings.speed),
    )


def format_speed(speed: float) -> str:
    """``1`` renders as ``1.0`` for the echo; a real fraction keeps its digits."""
    return f"{speed:.1f}" if float(speed).is_integer() else f"{speed:g}"


def echo(snapshot: Snapshot) -> str:
    """The one line shown under both players (``UI-UX Brief`` §8.9)."""
    return (
        f"{snapshot.model} · {snapshot.voice} · {snapshot.language} · "
        f"{format_speed(snapshot.speed)}×"
    )


def preflight(
    settings: Settings,
    result: TransformResult | None,
    blocked: str | None,
) -> tuple[bool, str | None]:
    """Return (ready, reason). Every disabled path names why (``TRD`` §12.3)."""
    if blocked == BLOCKED_EMPTY:
        return False, EMPTY_PREVIEW
    if blocked == BLOCKED_LIMIT:
        return False, (
            f"Script is over the {settings.script_block_chars:,} character limit"
        )
    if result is None:
        return False, EMPTY_PREVIEW
    if not result.changed:
        return False, NO_MATCH
    return True, None


def texts_changed(
    result: TransformResult | None, saved: tuple[str, str] | None
) -> bool:
    """True when the script or the rules changed since the pair was generated.

    A pair is only labelled with text it was generated from: a silent change
    would let the user compare two clips that do not match the current draft.
    """
    if result is None or saved is None:
        return False
    return (result.original_text, result.transformed_text) != saved


def generate_pair(
    cache: AudioCache,
    client: TimbreClient,
    texts: tuple[str, str],
    snapshot: Snapshot,
    on_step: Callable[[str], None] | None = None,
    on_original: Callable[[bytes], None] | None = None,
) -> PairOutcome:
    """Synthesise original then transformed, sequentially and cache-first.

    Flow 5: if the first call fails the second is never attempted, and a failure
    of the second keeps the original. ``on_original`` receives the first clip so
    the UI can show it before the second call starts; ``on_step`` reports which
    half is running.
    """
    original_text, adjusted_text = texts

    if on_step is not None:
        on_step("original")
    try:
        original = _clip(cache, client, original_text, snapshot).audio
    except AppError as exc:
        return PairOutcome(None, None, exc, "original")

    if on_original is not None:
        on_original(original)
    if on_step is not None:
        on_step("adjusted")
    try:
        adjusted = _clip(cache, client, adjusted_text, snapshot).audio
    except AppError as exc:
        return PairOutcome(original, None, exc, "adjusted")

    return PairOutcome(original, adjusted, None, None)


def _clip(
    cache: AudioCache,
    client: TimbreClient,
    text: str,
    snapshot: Snapshot,
) -> Clip:
    """Cache-first, one synthesis at a time; a hit costs nothing (FR-28)."""
    return cache.get_or_synthesize(
        client,
        text=text.strip(),
        model=snapshot.model,
        voice=snapshot.voice,
        language=snapshot.language,
        speed=snapshot.speed,
        audio_config=DEFAULT_AUDIO_CONFIG,
    )


def render(
    settings: Settings,
    cache: AudioCache,
    client: TimbreClient,
    result: TransformResult | None,
    blocked: str | None,
) -> None:
    """Draw the Generate control and the two players, in that order."""
    st.subheader("Audio")
    _drop_stale(settings, result)

    ready, reason = preflight(settings, result, blocked)
    button_slot = st.empty()
    with button_slot.container():
        clicked = st.button(
            GENERATE_LABEL,
            key="generate_comparison",
            type="primary",
            disabled=not ready,
        )
    if not ready and reason is not None:
        st.caption(reason)

    # These placeholders exist on every run so a rerun always clears the
    # in-flight status, step counter and first player. Without them, Streamlit
    # leaves the previous run's placeholder content in the element tree.
    status_slot = st.empty()
    step_slot = st.empty()
    player_slot = st.empty()

    if clicked and ready:
        _show_busy_button(button_slot)
        _generate(
            settings,
            cache,
            client,
            result,
            status_slot,
            step_slot,
            player_slot,
        )
        # The players and the restored button need one fresh pass; the editor
        # and rule table have already rendered, so their widget state is kept.
        st.rerun()

    _render_panel()


def _show_busy_button(slot) -> None:
    """Replace the pressed button with the Busy label (UI-UX §8.8).

    A button cannot change its own label while its handler runs, but a
    placeholder can be emptied and redrawn before the blocking calls. The new
    button is disabled and uses a different key, so it cannot be clicked and
    cannot collide with the real control.
    """
    slot.empty()
    with slot.container():
        st.button(GENERATING_LABEL, key="generating_indicator", disabled=True)


def _drop_stale(settings: Settings, result: TransformResult | None) -> None:
    """Clear a pair that no longer matches the current settings or text.

    The sidebar callbacks already clear the pair on a settings change, and this
    catches any other route into a mismatched snapshot (FR-21). The text check
    does the same for the script and the rules, so a player is never labelled
    with a pair it was not generated from.
    """
    if st.session_state.audio_result is None:
        return
    if st.session_state.settings_snapshot != current_snapshot(settings):
        clear_audio(SETTINGS_CHANGED)
    elif texts_changed(result, st.session_state.audio_texts):
        clear_audio(TEXT_CHANGED)


def _generate(
    settings: Settings,
    cache: AudioCache,
    client: TimbreClient,
    result: TransformResult,
    status_slot,
    step_slot,
    player_slot,
) -> None:
    """The click's one path into synthesis. Two calls, sequential, frozen settings."""
    snapshot = current_snapshot(settings)
    st.session_state.settings_snapshot = snapshot
    st.session_state.audio_texts = (result.original_text, result.transformed_text)
    st.session_state.busy = True

    with status_slot.container():
        status = st.status(GENERATING_ORIGINAL, expanded=False)
    step_slot.caption(STEP_ONE)

    def on_original(audio: bytes) -> None:
        _show_original(player_slot, audio, snapshot)

    def on_step(name: str) -> None:
        if name != "adjusted":
            return
        status.update(label=GENERATING_ADJUSTED, state="running")
        step_slot.caption(STEP_TWO)

    try:
        outcome = generate_pair(
            cache,
            client,
            (result.original_text, result.transformed_text),
            snapshot,
            on_step=on_step,
            on_original=on_original,
        )
    finally:
        st.session_state.busy = False

    _apply(outcome)


def _show_original(slot, audio: bytes, snapshot: Snapshot) -> None:
    """Show the first player before the second call starts (Flow 9 step H)."""
    slot.empty()
    with slot.container():
        left, right = st.columns(2)
        _render_clip(left, ORIGINAL_LABEL, audio, snapshot)
        _render_empty_clip(right, ADJUSTED_LABEL)


def _apply(outcome: PairOutcome) -> None:
    """Store the result, or keep the surviving half and park the error banner."""
    if outcome.error is not None:
        if outcome.failed_step == "adjusted" and outcome.original is not None:
            st.session_state.audio_result = AudioPair(outcome.original, None)
        # A failed original leaves any previous pair untouched: an error never
        # replaces existing results (App Flow §11, UI-UX §8.10).
        show_error(outcome.error)
        return

    st.session_state.audio_result = AudioPair(outcome.original, outcome.adjusted)
    st.session_state.audio_notice = None


def _render_panel() -> None:
    pair = st.session_state.audio_result
    if pair is None:
        _render_placeholder()
        return

    snapshot = st.session_state.settings_snapshot
    left, right = st.columns(2)
    _render_clip(left, ORIGINAL_LABEL, pair.original, snapshot)
    if pair.adjusted is None:
        _render_empty_clip(right, ADJUSTED_LABEL)
    else:
        _render_clip(right, ADJUSTED_LABEL, pair.adjusted, snapshot)


def _render_placeholder() -> None:
    """Both blocks empty, with the settings-changed caption when it applies."""
    left, right = st.columns(2)
    _render_empty_clip(left, ORIGINAL_LABEL)
    _render_empty_clip(right, ADJUSTED_LABEL)

    if st.session_state.audio_notice:
        st.caption(st.session_state.audio_notice)


def _render_empty_clip(column, label: str) -> None:
    with column:
        st.markdown(f"**{label}**")
        with st.container(border=True):
            st.caption(NOT_GENERATED)


def _render_clip(column, label: str, audio: bytes, snapshot: Snapshot | None) -> None:
    with column:
        st.markdown(f"**{label}**")
        st.audio(audio, format="audio/wav")
        if snapshot is not None:
            # One snapshot, one string: the echo under both players is identical
            # by construction, which is the correctness claim of Flow 5.
            st.caption(echo(snapshot))

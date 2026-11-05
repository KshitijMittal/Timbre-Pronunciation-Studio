"""Preview panes and per-rule match report (``App Flow`` §8, ``UI-UX Brief`` §8.7).

The transform is local and free, so it runs on every rerun: it calls
``apply_rules`` directly and never touches the network or spends credits. This is
the one place in the UI that mirrors API behaviour without calling it (``TRD``
§12.4) — the limit and markup checks are repeated here because the API's versions
live behind FastAPI.

Split into :func:`compute` and :func:`render` in step 4, because the rule table's
Matches column needs the same transform the preview shows. The rule table is
drawn between the script and the preview (``UI-UX Brief`` §8), so the transform
must exist before both.
"""

from __future__ import annotations

import streamlit as st

from app.config import Settings
from app.core.pronunciation_rules import TransformResult, apply_rules

from ui.editor import BLOCK
from ui.rule_draft import DraftRule, MARKUP_WARNING, engine_rules

ORIGINAL_LABEL = "ORIGINAL — kept for reference"
TRANSFORMED_LABEL = "TRANSFORMED — sent to Timbre"
EMPTY_PREVIEW = "Nothing to preview yet."
NO_MATCH = "No rules matched — nothing to compare"
NOT_FOUND_HEADING = "Not found in this script"

BLOCKED_EMPTY = "empty"
BLOCKED_LIMIT = "limit"


def compute(
    status: str,
    drafts: list[DraftRule],
) -> tuple[TransformResult | None, str | None]:
    """Transform the script with the **draft** rules; return (result, blocked).

    ``blocked`` is ``"empty"``, ``"limit"`` or ``None``. In the blocked cases no
    stale result is left in session state for the Generate step to mistake for a
    live transform (Flow 4).
    """
    script = st.session_state.script

    if not script.strip():
        st.session_state.transform_result = None
        return None, BLOCKED_EMPTY

    if status == BLOCK:
        st.session_state.transform_result = None
        return None, BLOCKED_LIMIT

    result = apply_rules(script, engine_rules(drafts))
    st.session_state.transform_result = result
    return result, None


def render(
    settings: Settings,
    count: int,
    drafts: list[DraftRule],
    result: TransformResult | None,
    blocked: str | None,
) -> None:
    """Draw the preview from the already-computed transform."""
    st.subheader("Preview")

    if blocked == BLOCKED_EMPTY:
        # Flow 4: an empty script leaves the preview blank.
        _render_empty()
        return

    if blocked == BLOCKED_LIMIT:
        # Flow 4 sends an over-limit script to a limit error, not to apply_rules.
        st.error(
            f"Script is {count:,} characters. "
            f"The limit is {settings.script_block_chars:,}."
        )
        return

    if result is None:
        _render_empty()
        return

    _render_panes(result)
    _render_report(result, drafts)
    _render_markup_warning(drafts)


def _render_panes(result: TransformResult) -> None:
    left, right = st.columns(2)
    _pane(left, ORIGINAL_LABEL, result.original_text)
    _pane(right, TRANSFORMED_LABEL, result.transformed_text)


def _pane(column, label: str, text: str) -> None:
    # A disabled text area keeps whitespace and wraps, and both panes stay the
    # same height. No widget key: the element's identity includes the value, so
    # the pane follows the script instead of freezing on its first render.
    column.caption(label)
    column.text_area(
        label,
        value=text,
        height=220,
        disabled=True,
        label_visibility="collapsed",
    )


def _render_empty() -> None:
    left, right = st.columns(2)
    for column, label in ((left, ORIGINAL_LABEL), (right, TRANSFORMED_LABEL)):
        column.caption(label)
        column.caption(EMPTY_PREVIEW)


def _render_report(result: TransformResult, drafts: list[DraftRule]) -> None:
    # The engine reports matches longest-source-first; the reader expects the
    # dictionary's own order, which is also the rule table's order.
    order = {draft.id: index for index, draft in enumerate(drafts)}
    matches = sorted(
        result.matches, key=lambda match: order.get(match.rule_id, len(order))
    )
    matched = [match for match in matches if match.count > 0]
    missing = [match for match in matches if match.count == 0]

    if not matched:
        # Verbatim from UI-UX §11; the same string gates Generate in step 5.
        st.caption(NO_MATCH)
        return

    st.text(
        "\n".join(
            f"{match.source} → {match.replacement}  ×{match.count}"
            for match in matched
        )
    )

    if missing:
        st.caption(NOT_FOUND_HEADING)
        st.text(
            "\n".join(
                f"{match.source} → {match.replacement}" for match in missing
            )
        )


def _render_markup_warning(drafts: list[DraftRule]) -> None:
    if any(
        "<" in draft.replacement or ">" in draft.replacement for draft in drafts
    ):
        st.warning(MARKUP_WARNING)

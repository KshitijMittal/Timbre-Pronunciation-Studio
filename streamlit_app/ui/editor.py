"""Script editor and character counter (``App Flow`` §8, ``UI-UX Brief`` §8.5).

The counter reads its thresholds from configuration, not from the numbers in the
copy, so changing ``SCRIPT_WARN_CHARS``/``SCRIPT_BLOCK_CHARS`` changes both the
counter and the limit behaviour. The states match the API's own boundary rules:
exactly ``warn_at`` is still ``ok``, exactly ``block_at`` is still accepted.
"""

from __future__ import annotations

import streamlit as st

from app.config import Settings

OK = "ok"
WARN = "warn"
BLOCK = "block"


def render(settings: Settings) -> tuple[int, str]:
    """Draw the editor and counter; return ``(character_count, limit_status)``."""
    st.subheader("Script")

    # The label stays for screen readers; the visible affordance is the heading.
    script = st.text_area(
        "Script",
        key="script",
        label_visibility="collapsed",
        height=180,
    )

    count = len(script)
    status = limit_status(count, settings)
    _render_counter(count, status, settings)
    return count, status


def limit_status(count: int, settings: Settings) -> str:
    """The same three states the API reports as ``limit.status``."""
    if count > settings.script_block_chars:
        return BLOCK
    if count > settings.script_warn_chars:
        return WARN
    return OK


def _render_counter(count: int, status: str, settings: Settings) -> None:
    # Colour is the only difference Streamlit can render without unsafe HTML;
    # the wording is verbatim from UI-UX §8.5.
    if status == BLOCK:
        st.caption(
            f":red[{count:,} characters — over the "
            f"{settings.script_block_chars:,} limit. Shorten the script.]"
        )
    elif status == WARN:
        st.caption(
            f":orange[{count:,} characters — long scripts take longer to generate]"
        )
    else:
        st.caption(f":gray[{count} / {settings.script_warn_chars:,} characters]")

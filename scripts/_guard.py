"""Shared credit guard and key loader for the developer scripts.

One copy of the rule, so a new script cannot quietly ship a weaker guard. See
``AGENTS.md`` section 1: a paid call needs the owner's explicit approval in the
current conversation, and the guard firing is an answer, not an obstacle.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"


def load_api_key() -> str:
    """Read the key from ``backend/.env``; exit 2 when it is missing."""
    load_dotenv(BACKEND_DIR / ".env")
    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        print("GNANI_API_KEY is not set. Add it to backend/.env.")
        raise SystemExit(2)
    return key


def confirm_credit_spend(estimate: int, *, detail: str = "") -> None:
    """Stop before the first paid call unless a human types the word.

    An agent, a heredoc or a pipe cannot answer this: ``input()`` raises
    ``EOFError`` and the run aborts with no call made. ``--confirm-spend`` is
    the deliberate, visible opt-in for a scripted run.
    """
    if estimate <= 0:
        print(
            "Nothing to generate: every file this run needs is already cached. "
            "No credits will be spent."
        )
        return

    print(f"This run can make up to {estimate} paid Timbre call(s).")
    if detail:
        print(detail)
    print("Nothing has been sent yet. No credits have been spent.")
    try:
        answer = input('Type "spend" to continue, or press Enter to cancel: ')
    except EOFError:
        answer = ""
    if answer.strip().lower() != "spend":
        raise SystemExit("Cancelled before any API call. No credits were spent.")

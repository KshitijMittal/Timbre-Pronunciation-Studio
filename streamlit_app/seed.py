"""First-run seed dictionary (``App Flow`` §5).

These are the three Gate B winners, not placeholders: each was judged ``closer``
against its original with model, voice, language and speed held constant. The
per-term record is ``docs/evidence/gate-b-try_results.json``.

Coimbatore is deliberately absent — it improved only partly, and a half-improved
place name is not evidence for a demo.
"""

from __future__ import annotations

from app.core.dictionary_store import DictionaryStore
from app.models.schemas import Dictionary, Rule

SEED_NAME = "Gnani Demo"

SEED_LABEL = (
    "Sample — verified in the Gate B listening test; replace with your own terms"
)

SEED_RULES: tuple[tuple[str, str], ...] = (
    ("Timbre", "Tim-ber"),
    ("Gnani", "Gyaa-nee"),
    ("Zentara", "Zen Taara"),
)

SAMPLE_SCRIPT = (
    "Timbre speaks Indian languages clearly. "
    "Gnani and Zentara are pronounced the way their teams say them."
)


def ensure_seed(store: DictionaryStore) -> Dictionary | None:
    """Create the seed dictionary, but only when the store is completely empty.

    Returns the created dictionary, or ``None`` when one already existed. The
    caller uses that distinction to decide whether to preload ``SAMPLE_SCRIPT``
    (first run only — a later load starts with an empty editor, ``TRD`` §12.6).
    """
    existing, warnings = store.list_all()
    if existing or warnings:
        # Warnings mean the folder is not empty: it holds files this build cannot
        # read. Seeding next to them would hide the problem instead of surfacing
        # it, so leave the store alone and let the sidebar report the warnings.
        return None

    dictionary = store.create(SEED_NAME)
    try:
        for source, replacement in SEED_RULES:
            dictionary, _ = store.add_rule(
                dictionary.id, source=source, replacement=replacement
            )
    except Exception:
        # Leaving a half-built seed behind would make the next run think the
        # store is populated and never retry. The store was empty on entry, so
        # removing the dictionary we just created cannot destroy user data.
        store.delete(dictionary.id)
        raise

    return dictionary


def is_seed_dictionary(dictionary: Dictionary) -> bool:
    """True when the rules still match the seed exactly.

    Used to show ``SEED_LABEL``. Matched on content rather than name or id so the
    label survives a restart and a rename, and disappears as soon as the user
    edits the rules — which is exactly when it stops being true.
    """
    pairs = {(rule.source.casefold(), rule.replacement.casefold()) for rule in dictionary.rules}
    expected = {(source.casefold(), replacement.casefold()) for source, replacement in SEED_RULES}
    return pairs == expected

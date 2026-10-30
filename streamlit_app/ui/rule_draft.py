"""Editable rule drafts, local validation and the commit plan (``App Flow`` §7).

The rule table is a workbench, not a form: edits live in a draft copy of the
dictionary's rules, the preview transforms the draft, and only **Save** writes.
This module holds that logic with no Streamlit import, so it can be unit-tested
directly — ``AppTest`` cannot type into a ``data_editor`` cell.

Validation repeats ``DictionaryStore``'s own rules with the same wording, because
the store remains the authoritative gate before anything is written. The markup
check is the one advisory (non-blocking) warning (``UI-UX Brief`` §8.6).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from uuid import uuid4

from app.core.pronunciation_rules import Rule as EngineRule
from app.models.schemas import (
    MAX_REPLACEMENT_LENGTH,
    MAX_RULES,
    MAX_SOURCE_LENGTH,
    Rule,
)

NEW_ID_PREFIX = "draft_"

MARKUP_WARNING = (
    "Timbre strips angle-bracket markup, so this replacement may not be spoken "
    "as written."
)
DUPLICATE_MESSAGE = "This term already has a rule."
EMPTY_SOURCE_MESSAGE = "Source term cannot be empty."
EMPTY_REPLACEMENT_MESSAGE = "Replacement cannot be empty."


@dataclass(frozen=True, slots=True)
class DraftRule:
    """One table row. ``id`` survives reruns; new rows keep a ``draft_`` id."""

    id: str
    source: str
    replacement: str
    created_at: str = ""

    @property
    def is_new(self) -> bool:
        return self.id.startswith(NEW_ID_PREFIX)

    @classmethod
    def new(cls, source: str = "", replacement: str = "") -> "DraftRule":
        return cls(id=f"{NEW_ID_PREFIX}{uuid4().hex}", source=source, replacement=replacement)


@dataclass(frozen=True, slots=True)
class RowIssue:
    """A message about one row. Blocking issues disable Save; warnings do not."""

    index: int
    source: str
    message: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class CommitPlan:
    """What Save would write, in the order the store expects."""

    updated: tuple[tuple[str, str, str], ...]
    added: tuple[tuple[str, str], ...]


def from_rules(rules: list[Rule]) -> list[DraftRule]:
    """Copy stored rules into drafts, preserving their insertion order."""
    return [
        DraftRule(
            id=rule.id,
            source=rule.source,
            replacement=rule.replacement,
            created_at=rule.created_at,
        )
        for rule in rules
    ]


def validate(drafts: list[DraftRule]) -> list[RowIssue]:
    """Check every row on every rerun; the first blocking problem wins per row."""
    source_counts = Counter(
        draft.source.strip().casefold()
        for draft in drafts
        if draft.source.strip()
    )

    issues: list[RowIssue] = []
    for index, draft in enumerate(drafts):
        source = draft.source.strip()
        replacement = draft.replacement.strip()

        if not source:
            issues.append(RowIssue(index, source, EMPTY_SOURCE_MESSAGE, True))
        elif len(source) > MAX_SOURCE_LENGTH:
            issues.append(
                RowIssue(
                    index,
                    source,
                    f"Source term must be {MAX_SOURCE_LENGTH} characters or fewer.",
                    True,
                )
            )
        elif source_counts[source.casefold()] > 1:
            issues.append(RowIssue(index, source, DUPLICATE_MESSAGE, True))

        if not replacement:
            issues.append(RowIssue(index, source, EMPTY_REPLACEMENT_MESSAGE, True))
        elif len(replacement) > MAX_REPLACEMENT_LENGTH:
            issues.append(
                RowIssue(
                    index,
                    source,
                    f"Replacement must be {MAX_REPLACEMENT_LENGTH} characters or fewer.",
                    True,
                )
            )
        elif "<" in replacement or ">" in replacement:
            issues.append(RowIssue(index, source, MARKUP_WARNING, False))

    return issues


def has_blocking(issues: list[RowIssue]) -> bool:
    return any(issue.blocking for issue in issues)


def is_dirty(drafts: list[DraftRule], rules: list[Rule]) -> bool:
    """True when the draft differs from disk and Save/Cancel should be offered."""
    if len(drafts) != len(rules):
        return True

    for draft, rule in zip(drafts, rules):
        if draft.id != rule.id:
            return True
        if draft.source.strip() != rule.source:
            return True
        if draft.replacement.strip() != rule.replacement:
            return True
    return False


def same(left: list[DraftRule], right: list[DraftRule]) -> bool:
    """Exact draft equality, used to detect a fresh ``data_editor`` edit."""
    return len(left) == len(right) and all(
        (a.id, a.source, a.replacement) == (b.id, b.source, b.replacement)
        for a, b in zip(left, right)
    )


def with_values(
    drafts: list[DraftRule], index: int, source: str, replacement: str
) -> DraftRule:
    """Replace one row's text while keeping its identity."""
    return replace(drafts[index], source=source, replacement=replacement)


def commit_plan(drafts: list[DraftRule], rules: list[Rule]) -> CommitPlan:
    """Split drafts into changed rows and new rows.

    Deletes are not part of this plan: they are confirmed separately, so a row
    can never vanish because a table edit was abandoned.
    """
    stored = {rule.id: rule for rule in rules}

    updated: list[tuple[str, str, str]] = []
    for draft in drafts:
        if draft.is_new:
            continue
        rule = stored.get(draft.id)
        if rule is None:
            continue
        source = draft.source.strip()
        replacement = draft.replacement.strip()
        if source != rule.source or replacement != rule.replacement:
            updated.append((draft.id, source, replacement))

    added = [
        (draft.source.strip(), draft.replacement.strip())
        for draft in drafts
        if draft.is_new
    ]
    return CommitPlan(updated=tuple(updated), added=tuple(added))


def engine_rules(drafts: list[DraftRule]) -> list[EngineRule]:
    """Rules for the preview transform, including unsaved rows.

    Blank rows are dropped: an empty source would build a regex that matches
    everywhere. Markup and duplicate rows are still applied — they are local
    warnings, not reasons to hide their effect from the preview.
    """
    return [
        EngineRule(
            source=draft.source.strip(),
            replacement=draft.replacement.strip(),
            rule_id=draft.id,
            created_at=draft.created_at,
        )
        for draft in drafts
        if draft.source.strip() and draft.replacement.strip()
    ]


def at_rule_limit(drafts: list[DraftRule]) -> bool:
    return len(drafts) >= MAX_RULES

"""Unit tests for rule drafts (``App Flow`` §7, task 7c.4).

``AppTest`` cannot type into a ``st.data_editor`` cell, so the draft, validation
and commit logic is kept Streamlit-free in ``ui/rule_draft.py`` and tested here
directly. The widget paths (Add, Save, Cancel, Delete) are covered by the
``AppTest`` verification runs, not by these tests.
"""

from __future__ import annotations

import pytest

from app.models.schemas import MAX_REPLACEMENT_LENGTH, MAX_RULES, MAX_SOURCE_LENGTH, Rule
from ui import rule_draft
from ui.rule_draft import DraftRule

CREATED = "2026-10-26T00:00:00Z"


def stored(rule_id: str, source: str, replacement: str) -> Rule:
    return Rule(
        id=rule_id,
        source=source,
        replacement=replacement,
        created_at=CREATED,
        updated_at=CREATED,
    )


def draft(rule_id: str, source: str, replacement: str) -> DraftRule:
    return DraftRule(id=rule_id, source=source, replacement=replacement, created_at=CREATED)


def messages(drafts: list[DraftRule]) -> list[str]:
    return [issue.message for issue in rule_draft.validate(drafts)]


def test_from_rules_preserves_order_ids_and_created_at():
    rules = [stored("rule_a", "Timbre", "Tim-ber"), stored("rule_b", "Gnani", "Gyaa-nee")]

    drafts = rule_draft.from_rules(rules)

    assert [(d.id, d.source, d.replacement, d.created_at) for d in drafts] == [
        ("rule_a", "Timbre", "Tim-ber", CREATED),
        ("rule_b", "Gnani", "Gyaa-nee", CREATED),
    ]
    assert not any(d.is_new for d in drafts)


def test_new_draft_has_a_stable_temporary_id():
    first = DraftRule.new("Coimbatore", "Ko-yam-ba-toor")

    assert first.is_new
    assert first.id.startswith(rule_draft.NEW_ID_PREFIX)
    assert first.created_at == ""


def test_valid_drafts_produce_no_issues():
    assert rule_draft.validate([draft("rule_a", "Timbre", "Tim-ber")]) == []
    assert not rule_draft.has_blocking([])


def test_empty_source_and_replacement_are_blocking():
    issues = rule_draft.validate([draft("draft_1", "   ", "  ")])

    assert [issue.message for issue in issues] == [
        rule_draft.EMPTY_SOURCE_MESSAGE,
        rule_draft.EMPTY_REPLACEMENT_MESSAGE,
    ]
    assert all(issue.blocking for issue in issues)


def test_duplicate_source_is_case_and_whitespace_insensitive_and_flags_both_rows():
    drafts = [draft("rule_a", "Timbre", "Tim-ber"), draft("draft_1", " timbre ", "Tim-burr")]

    issues = rule_draft.validate(drafts)

    assert [issue.index for issue in issues] == [0, 1]
    assert {issue.message for issue in issues} == {rule_draft.DUPLICATE_MESSAGE}
    assert rule_draft.has_blocking(issues)


def test_length_limits_match_the_store():
    too_long_source = draft("draft_1", "a" * (MAX_SOURCE_LENGTH + 1), "ok")
    too_long_replacement = draft("draft_2", "ok", "b" * (MAX_REPLACEMENT_LENGTH + 1))
    at_source_limit = draft("draft_3", "a" * MAX_SOURCE_LENGTH, "ok")
    at_replacement_limit = draft("draft_4", "ok2", "b" * MAX_REPLACEMENT_LENGTH)

    assert messages([too_long_source]) == [
        f"Source term must be {MAX_SOURCE_LENGTH} characters or fewer."
    ]
    assert messages([too_long_replacement]) == [
        f"Replacement must be {MAX_REPLACEMENT_LENGTH} characters or fewer."
    ]
    assert messages([at_source_limit, at_replacement_limit]) == []


def test_markup_is_the_only_non_blocking_warning():
    issues = rule_draft.validate([draft("rule_a", "Markup", "<b>Markup</b>")])

    assert len(issues) == 1
    assert issues[0].message == rule_draft.MARKUP_WARNING
    assert issues[0].blocking is False
    assert not rule_draft.has_blocking(issues)


def test_is_dirty_compares_trimmed_text_and_identity():
    rules = [stored("rule_a", "Timbre", "Tim-ber")]

    assert not rule_draft.is_dirty(rule_draft.from_rules(rules), rules)
    assert not rule_draft.is_dirty([draft("rule_a", " Timbre ", "Tim-ber ")], rules)
    assert rule_draft.is_dirty([draft("rule_a", "Timbre", "Tim-burr")], rules)
    assert rule_draft.is_dirty([draft("rule_b", "Timbre", "Tim-ber")], rules)
    assert rule_draft.is_dirty([], rules)
    assert rule_draft.is_dirty([*rule_draft.from_rules(rules), DraftRule.new("X", "Y")], rules)


def test_same_ignores_created_at_but_not_text_or_identity():
    left = [draft("rule_a", "Timbre", "Tim-ber")]
    right = [DraftRule(id="rule_a", source="Timbre", replacement="Tim-ber", created_at="other")]

    assert rule_draft.same(left, right)
    assert not rule_draft.same(left, [draft("rule_a", "Timbre", "Tim-burr")])
    assert not rule_draft.same(left, [])


def test_commit_plan_reports_only_changed_rows_and_new_rows():
    rules = [stored("rule_a", "Timbre", "Tim-ber"), stored("rule_b", "Gnani", "Gyaa-nee")]
    drafts = [
        draft("rule_a", "Timbre", "Tim-ber"),      # unchanged
        draft("rule_b", " Gnani ", "Gyaa-nee2"),   # changed, trimmed
        DraftRule.new("Zentara", " Zen Taara "),   # new, trimmed
    ]

    plan = rule_draft.commit_plan(drafts, rules)

    assert plan.updated == (("rule_b", "Gnani", "Gyaa-nee2"),)
    assert plan.added == (("Zentara", "Zen Taara"),)


def test_commit_plan_is_empty_when_nothing_changed():
    rules = [stored("rule_a", "Timbre", "Tim-ber")]

    plan = rule_draft.commit_plan(rule_draft.from_rules(rules), rules)

    assert plan.updated == ()
    assert plan.added == ()


def test_engine_rules_drop_blank_rows_and_strip_text():
    drafts = [
        draft("rule_a", " Timbre ", "Tim-ber"),
        DraftRule.new("", "orphan replacement"),
        DraftRule.new("orphan source", ""),
        DraftRule.new("Zentara", " Zen Taara "),
    ]

    rules = rule_draft.engine_rules(drafts)

    assert [(r.rule_id, r.source, r.replacement) for r in rules] == [
        ("rule_a", "Timbre", "Tim-ber"),
        (drafts[3].id, "Zentara", "Zen Taara"),
    ]


@pytest.mark.parametrize("count,expected", [(MAX_RULES - 1, False), (MAX_RULES, True), (MAX_RULES + 1, True)])
def test_at_rule_limit(count, expected):
    drafts = [DraftRule.new(f"term {index}", "replacement") for index in range(count)]

    assert rule_draft.at_rule_limit(drafts) is expected

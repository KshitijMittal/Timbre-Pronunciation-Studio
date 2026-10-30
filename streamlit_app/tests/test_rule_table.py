"""Tests for the pieces of ``ui/rules.py`` that ``AppTest`` cannot drive.

``AppTest`` exposes no ``data_editor`` cell editing, so the merge between the
editor's returned rows and the drafts is tested here with the same list-of-dicts
shape Streamlit returns.
"""

from __future__ import annotations

from ui import rules
from ui.rule_draft import DraftRule

CREATED = "2026-10-26T00:00:00Z"


def draft(rule_id: str = "rule_a") -> DraftRule:
    return DraftRule(
        id=rule_id,
        source="Timbre",
        replacement="Tim-ber",
        created_at=CREATED,
    )


def test_merge_reads_edited_cells_and_keeps_row_identity():
    drafts = [draft(), draft("rule_b")]
    rows = rules._rows(drafts, {"rule_a": 2, "rule_b": 0})

    rows[0][rules.SOURCE_COLUMN] = "Timbre AI"
    rows[0][rules.REPLACEMENT_COLUMN] = "Tim-ber A-I"
    merged = rules._merge(rows, drafts)

    assert [row.id for row in merged] == ["rule_a", "rule_b"]
    assert (merged[0].source, merged[0].replacement) == ("Timbre AI", "Tim-ber A-I")
    assert (merged[1].source, merged[1].replacement) == ("Timbre", "Tim-ber")


def test_merge_keeps_an_emptied_cell_empty_instead_of_restoring_it():
    drafts = [draft()]
    rows = rules._rows(drafts, {"rule_a": 1})
    rows[0][rules.REPLACEMENT_COLUMN] = ""

    merged = rules._merge(rows, drafts)

    assert merged[0].replacement == ""
    assert merged[0].source == "Timbre"


def test_merge_falls_back_only_when_the_column_is_absent():
    drafts = [draft()]
    rows = [{rules.SOURCE_COLUMN: "New term"}]

    merged = rules._merge(rows, drafts)

    assert merged[0].source == "New term"
    assert merged[0].replacement == "Tim-ber"


def test_match_label_never_invents_a_count():
    row = draft()

    assert rules._match_label(row, None) == "\u2014"
    assert rules._match_label(row, {}) == "\u2014"
    assert rules._match_label(row, {row.id: 0}) == "0"
    assert rules._match_label(row, {row.id: 3}) == "3"

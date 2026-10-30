"""Rule table: add, inline edit, validate, save, cancel and delete.

``App Flow`` §7 and ``UI-UX Brief`` §8.6. The table is a *draft*: edits never
write until Save, and the preview transforms the draft so an unsaved rule still
shows its effect. The preview never waits for a save.

Two Streamlit limits shape this module, both recorded in ``TRD`` §12.3 and
``docs/LIMITATIONS.md``:

* ``st.data_editor`` has no per-row Save/Cancel, so Save/Cancel act on the whole
  table (which is what ``App Flow`` §7 actually describes).
* it exposes no row selection, so Delete uses a rule selector and confirms in
  place with a second button (``UI-UX Brief`` §8.11).
"""

from __future__ import annotations

import streamlit as st

from app.core.dictionary_store import DictionaryStore
from app.core.pronunciation_rules import TransformResult
from app.errors import AppError
from app.models.schemas import MAX_REPLACEMENT_LENGTH, MAX_RULES, MAX_SOURCE_LENGTH

from state import show_error
from ui import dictionaries, rule_draft
from ui.rule_draft import DraftRule

SOURCE_COLUMN = "Source term"
REPLACEMENT_COLUMN = "Replacement"
MATCHES_COLUMN = "Matches"
ID_COLUMN = "id"

ZERO_MATCH = "term not found in script"
NO_RULES = "No rules yet."
SAVE_BLOCKED = "Fix the flagged rows to save."
DELETE_BLOCKED = "Save or cancel your edits before deleting a rule."


def prepare() -> list[DraftRule]:
    """Return the drafts, resyncing them when the active dictionary changed.

    Called before the transform so the preview and the Matches column both see
    the same rows. Unsaved edits survive reruns because the dictionary id is
    unchanged; switching dictionaries starts from that dictionary's stored rules
    (Flow 6 swaps the rule set).
    """
    if st.session_state.rule_drafts_dictionary != st.session_state.active_dictionary_id:
        reload_rules()
        # The add form is drawn after this point, so clearing its widget keys is
        # safe; stale text from another dictionary must not be carried across.
        st.session_state.add_source = ""
        st.session_state.add_replacement = ""
    return st.session_state.rule_drafts


def reload_rules() -> None:
    """Discard drafts and rebuild them from the stored rules.

    Also forces a fresh ``data_editor`` instance, because the widget's own state
    still holds the discarded cells until its key changes. Safe to call from a
    callback (before the page is drawn) or after Save, which calls
    ``st.rerun`` immediately afterwards.
    """
    st.session_state.rule_drafts = rule_draft.from_rules(st.session_state.rules)
    st.session_state.rule_drafts_dictionary = st.session_state.active_dictionary_id
    st.session_state.rule_table_seq += 1
    st.session_state.ui_rule_delete_open = False
    st.session_state.delete_rule_id = None


def render(store: DictionaryStore, result: TransformResult | None) -> None:
    """Draw the panel. Drafts must already be prepared by :func:`prepare`."""
    st.subheader("Rules")

    drafts: list[DraftRule] = st.session_state.rule_drafts
    at_limit = rule_draft.at_rule_limit(drafts)
    _render_add_form(at_limit)

    if not drafts:
        st.caption(NO_RULES)

    counts = _counts(result)
    edited = st.data_editor(
        _rows(drafts, counts),
        key=f"rule_table_{st.session_state.rule_table_seq}",
        hide_index=True,
        num_rows="fixed",
        column_order=[SOURCE_COLUMN, REPLACEMENT_COLUMN, MATCHES_COLUMN],
        column_config={
            SOURCE_COLUMN: st.column_config.TextColumn(
                SOURCE_COLUMN,
                help=f"Up to {MAX_SOURCE_LENGTH} characters.",
                max_chars=MAX_SOURCE_LENGTH,
            ),
            REPLACEMENT_COLUMN: st.column_config.TextColumn(
                REPLACEMENT_COLUMN,
                help=f"How Timbre should say it. Up to {MAX_REPLACEMENT_LENGTH} characters.",
                max_chars=MAX_REPLACEMENT_LENGTH,
            ),
            MATCHES_COLUMN: st.column_config.TextColumn(
                MATCHES_COLUMN,
                help="How many times this term occurs in the current script.",
            ),
            ID_COLUMN: None,
        },
        disabled=[MATCHES_COLUMN, ID_COLUMN],
    )

    merged = _merge(edited, drafts)
    if not rule_draft.same(merged, drafts):
        # The fresh cell edit is only readable after the widget has rendered,
        # which is after this run's transform. Rerun once so the Matches column
        # and the preview both transform the edited rows, never the previous
        # ones. The editor above has already rendered, so the script is kept.
        st.session_state.rule_drafts = merged
        st.rerun()

    drafts = merged
    issues = rule_draft.validate(drafts)
    blocking = rule_draft.has_blocking(issues)

    _render_issues(issues, drafts)
    _render_zero_matches(drafts, counts)
    _render_save_cancel(store, drafts, blocking)
    _render_delete(
        store,
        drafts,
        dirty=rule_draft.is_dirty(drafts, st.session_state.rules),
    )


def _render_add_form(at_limit: bool) -> None:
    """Two fields, one button (Flow 3). Appends a draft; never writes."""
    with st.form("add_rule", clear_on_submit=False):
        source_column, replacement_column, button_column = st.columns([1, 1, 0.6])
        source_column.text_input(
            SOURCE_COLUMN,
            key="add_source",
            max_chars=MAX_SOURCE_LENGTH,
            placeholder="e.g. Coimbatore",
        )
        replacement_column.text_input(
            REPLACEMENT_COLUMN,
            key="add_replacement",
            max_chars=MAX_REPLACEMENT_LENGTH,
            placeholder="e.g. Ko-yam-ba-toor",
        )
        button_column.form_submit_button(
            "+ Add rule",
            disabled=at_limit,
            on_click=_append_draft,
        )

    if at_limit:
        st.caption(
            f"This dictionary has {MAX_RULES} rules, the maximum for this release."
        )


def _append_draft() -> None:
    """Submit callback: append the row before the table is drawn."""
    if rule_draft.at_rule_limit(st.session_state.rule_drafts):
        # The button is disabled at the limit; this is the second line of
        # defence, because the store's limit is authoritative.
        return

    source = st.session_state.get("add_source", "")
    replacement = st.session_state.get("add_replacement", "")
    if not source.strip() and not replacement.strip():
        return

    st.session_state.rule_drafts = [
        *st.session_state.rule_drafts,
        DraftRule.new(source, replacement),
    ]
    st.session_state.add_source = ""
    st.session_state.add_replacement = ""
    st.session_state.rule_table_seq += 1


def _rows(drafts: list[DraftRule], counts: dict[str, int] | None) -> list[dict[str, str]]:
    # A list of dicts keeps the UI free of a direct pandas dependency; Streamlit
    # already depends on pandas, but this module does not import it.
    return [
        {
            ID_COLUMN: draft.id,
            SOURCE_COLUMN: draft.source,
            REPLACEMENT_COLUMN: draft.replacement,
            MATCHES_COLUMN: _match_label(draft, counts),
        }
        for draft in drafts
    ]


def _match_label(draft: DraftRule, counts: dict[str, int] | None) -> str:
    if counts is None:
        # Empty or over-limit script: no transform exists, so no count can be
        # claimed. The preview says why.
        return "—"
    count = counts.get(draft.id)
    return "—" if count is None else str(count)


def _merge(edited, drafts: list[DraftRule]) -> list[DraftRule]:
    """Read the editor's rows back by position.

    Row identity is positional on purpose: the table has fixed rows and any
    structural change replaces the widget key, so position always maps 1:1.
    """
    try:
        records = edited.to_dict("records")
    except AttributeError:
        records = list(edited)

    merged: list[DraftRule] = []
    for index, draft in enumerate(drafts):
        row = records[index] if index < len(records) else {}
        row = row or {}
        merged.append(
            rule_draft.with_values(
                drafts,
                index,
                _cell(row, SOURCE_COLUMN, draft.source),
                _cell(row, REPLACEMENT_COLUMN, draft.replacement),
            )
        )
    return merged


def _cell(row: dict, name: str, fallback: str) -> str:
    """Read one edited cell. An emptied cell is "", not the previous value."""
    if name not in row:
        return fallback
    return _text(row[name])


def _text(value: object) -> str:
    return "" if value is None else str(value)


def _counts(result: TransformResult | None) -> dict[str, int] | None:
    if result is None:
        return None
    return {match.rule_id: match.count for match in result.matches}


def _render_issues(issues: list[rule_draft.RowIssue], drafts: list[DraftRule]) -> None:
    for issue in issues:
        label = drafts[issue.index].source.strip() or f"Rule {issue.index + 1}"
        colour = "red" if issue.blocking else "orange"
        st.caption(f":{colour}[{label} — {issue.message}]")


def _render_zero_matches(drafts: list[DraftRule], counts: dict[str, int] | None) -> None:
    if counts is None:
        return
    for draft in drafts:
        if counts.get(draft.id) == 0:
            st.caption(f"{draft.source.strip()} — {ZERO_MATCH}")


def _render_save_cancel(
    store: DictionaryStore, drafts: list[DraftRule], blocking: bool
) -> None:
    if not rule_draft.is_dirty(drafts, st.session_state.rules):
        return

    save_column, cancel_column = st.columns(2)
    save_clicked = save_column.button(
        "Save", key="save_rules", type="primary", disabled=blocking
    )
    cancel_clicked = cancel_column.button("Cancel", key="cancel_rules")

    if blocking:
        st.caption(SAVE_BLOCKED)

    if save_clicked:
        _save(store)
    elif cancel_clicked:
        reload_rules()
        st.rerun()


def _save(store: DictionaryStore) -> None:
    """Write updates then additions, then reload from disk (Flow 3).

    A failure shows the banner and reloads from disk, so a partial write is
    visible as what actually persisted rather than as an optimistic table.
    """
    drafts = st.session_state.rule_drafts
    if rule_draft.has_blocking(rule_draft.validate(drafts)):
        # Save is disabled for invalid rows; never rely on the widget alone,
        # because the store would reject the same row one call later.
        return

    plan = rule_draft.commit_plan(drafts, st.session_state.rules)
    dictionary_id = st.session_state.active_dictionary_id

    try:
        for rule_id, source, replacement in plan.updated:
            store.update_rule(rule_id, source=source, replacement=replacement)
        for source, replacement in plan.added:
            store.add_rule(dictionary_id, source=source, replacement=replacement)
    except AppError as exc:
        show_error(exc)

    dictionaries.refresh(store)
    reload_rules()
    st.rerun()


def _render_delete(
    store: DictionaryStore,
    drafts: list[DraftRule],
    *,
    dirty: bool,
) -> None:
    """Select, then confirm in place (Flow 3). Disabled while edits are unsaved."""
    stored = [draft for draft in drafts if not draft.is_new]
    if not stored:
        return

    sequence = st.session_state.rule_table_seq
    labels = {draft.id: draft.source.strip() or "(untitled)" for draft in stored}

    st.divider()
    selected = st.selectbox(
        "Rule to delete",
        options=list(labels),
        format_func=lambda rule_id: labels[rule_id],
        index=None,
        placeholder="Choose a rule",
        key=f"delete_rule_select_{sequence}",
    )
    st.button(
        "Delete rule",
        key=f"delete_rule_{sequence}",
        disabled=dirty,
        on_click=_open_delete,
        args=(selected,),
    )
    if dirty:
        st.caption(DELETE_BLOCKED)

    rule_id = st.session_state.delete_rule_id
    if not st.session_state.ui_rule_delete_open or rule_id not in labels:
        return

    st.markdown(f"**Delete '{labels[rule_id]}'?**")
    st.caption("This removes the rule. It cannot be undone.")
    cancel_column, delete_column = st.columns(2)
    cancel_column.button(
        "Cancel", key="cancel_rule_delete", on_click=_cancel_delete
    )
    delete_column.button(
        "Confirm delete",
        key="confirm_rule_delete",
        type="primary",
        on_click=_delete_rule,
        args=(store, rule_id),
    )


def _open_delete(selected: str | None) -> None:
    if selected is None or st.session_state.ui_rule_delete_open:
        return
    if rule_draft.is_dirty(
        st.session_state.rule_drafts, st.session_state.rules
    ):
        # The control is disabled while edits are unsaved; this guard keeps the
        # drafts safe even if the click arrives some other way.
        return
    st.session_state.ui_rule_delete_open = True
    st.session_state.delete_rule_id = selected


def _cancel_delete() -> None:
    st.session_state.ui_rule_delete_open = False


def _delete_rule(store: DictionaryStore, rule_id: str) -> None:
    try:
        store.delete_rule(rule_id)
    except AppError as exc:
        show_error(exc)
    dictionaries.refresh(store)
    reload_rules()

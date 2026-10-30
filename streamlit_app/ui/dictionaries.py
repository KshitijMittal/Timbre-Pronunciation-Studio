"""Sidebar dictionary selector, create, rename and delete (``App Flow`` §3, §6).

The selector is the only list: Rename and Delete are buttons underneath it and
act on the active dictionary. There is deliberately no per-item overflow menu and
no dialog shell — both are cut for Streamlit (``App Flow`` §3, ``UI-UX Brief``
§16.1). Deletion is confirmed in place by a second, explicit button.
"""

from __future__ import annotations

import streamlit as st

from app.core.dictionary_store import DictionaryStore
from app.errors import AppError
from app.models.schemas import Dictionary

from seed import SEED_LABEL, is_seed_dictionary
from state import show_error


def refresh(store: DictionaryStore) -> None:
    """Re-read dictionaries after any mutation and mirror the active rules.

    Never touches a widget key. Streamlit raises if a key is assigned in the
    same run that already instantiated the widget, so selector synchronisation
    is confined to the start of :func:`render`.
    """
    dictionaries, warnings = store.list_all()
    st.session_state.dictionaries = dictionaries
    st.session_state.store_warnings = warnings

    valid_ids = [dictionary.id for dictionary in dictionaries]
    if st.session_state.active_dictionary_id not in valid_ids:
        st.session_state.active_dictionary_id = valid_ids[0] if valid_ids else None

    load_rules(store)


def load_rules(store: DictionaryStore) -> None:
    """Put the active dictionary's rules into session state (``TRD`` §12.2).

    Called on selection, because Flow 6 swaps the rule set while the script
    stays. Without this the preview and rule table would show the previous
    dictionary's rules.
    """
    dictionary_id = st.session_state.active_dictionary_id
    if dictionary_id is None:
        st.session_state.rules = []
        return

    try:
        st.session_state.rules = list(store.get(dictionary_id).rules)
    except AppError as exc:
        st.session_state.rules = []
        show_error(exc)


def render(store: DictionaryStore) -> bool:
    """Draw the sidebar section. Returns whether any dictionary exists."""
    st.sidebar.subheader("Dictionaries")

    dictionaries: list[Dictionary] = st.session_state.dictionaries
    warnings = st.session_state.store_warnings
    if warnings:
        st.sidebar.warning(
            f"{len(warnings)} dictionary file"
            f"{'' if len(warnings) == 1 else 's'} could not be read."
        )
        for warning in warnings:
            st.sidebar.caption(f"{warning.file}: {warning.reason}")

    if not dictionaries:
        st.sidebar.caption("No dictionaries yet")
        st.sidebar.button("+ New", key="new_dictionary", on_click=_open_create)
        _render_create_form(store)
        return False

    _sync_selector()
    names = {dictionary.id: dictionary.name for dictionary in dictionaries}

    st.sidebar.selectbox(
        "Dictionary",
        options=[dictionary.id for dictionary in dictionaries],
        format_func=lambda dictionary_id: names[dictionary_id],
        key="dict_selector",
        label_visibility="collapsed",
        on_change=_on_select,
        args=(store,),
    )

    active = _active_dictionary()
    if active is not None:
        st.sidebar.caption(_count(len(active.rules)))
        if is_seed_dictionary(active):
            st.sidebar.caption(SEED_LABEL)

    st.sidebar.button("+ New", key="new_dictionary", on_click=_open_create)
    rename_column, delete_column = st.sidebar.columns(2)
    rename_column.button(
        "Rename", key="rename_dictionary", on_click=_open_rename
    )
    delete_column.button(
        "Delete", key="delete_dictionary", on_click=_open_delete
    )

    _render_create_form(store)
    _render_rename_form(store, active)
    _render_delete_confirm(store, active)
    return True


def render_empty_state() -> None:
    """The Empty state's main-column prompt (``App Flow`` §4, §6)."""
    st.subheader("No dictionaries yet")
    st.caption(
        "Create a dictionary to group the terms this studio should respell. "
        "The script and audio panels stay disabled until one exists."
    )
    st.button("Create a dictionary", key="empty_create", on_click=_open_create)


def _count(rules: int) -> str:
    return f"{rules} rule" if rules == 1 else f"{rules} rules"


def _active_dictionary() -> Dictionary | None:
    active_id = st.session_state.active_dictionary_id
    return next(
        (
            dictionary
            for dictionary in st.session_state.dictionaries
            if dictionary.id == active_id
        ),
        None,
    )


def _sync_selector() -> None:
    """Make the selector's session value agree with the active dictionary.

    Runs before the selectbox is instantiated, which is the only safe moment to
    assign a widget key. A mismatch means the selection changed programmatically
    (seed, create, delete), not by the user: user changes arrive through
    :func:`_on_select`, which has already set both values before this runs.
    """
    valid_ids = [dictionary.id for dictionary in st.session_state.dictionaries]
    active_id = st.session_state.active_dictionary_id
    target = active_id if active_id in valid_ids else valid_ids[0]
    if st.session_state.get("dict_selector") != target:
        st.session_state.dict_selector = target


def _on_select(store: DictionaryStore) -> None:
    """Selector callback: swap the rule set, keep the script (Flow 6)."""
    st.session_state.active_dictionary_id = st.session_state.dict_selector
    st.session_state.ui_rename_open = False
    st.session_state.ui_delete_open = False
    st.session_state.form_error = None
    load_rules(store)


def _open_create() -> None:
    st.session_state.ui_new_seq += 1
    st.session_state.ui_new_open = True
    st.session_state.ui_rename_open = False
    st.session_state.ui_delete_open = False
    st.session_state.form_error = None


def _open_rename() -> None:
    st.session_state.ui_rename_seq += 1
    st.session_state.ui_rename_open = True
    st.session_state.ui_new_open = False
    st.session_state.ui_delete_open = False
    st.session_state.form_error = None


def _open_delete() -> None:
    st.session_state.ui_delete_open = True
    st.session_state.ui_new_open = False
    st.session_state.ui_rename_open = False
    st.session_state.form_error = None


def _cancel_form() -> None:
    st.session_state.ui_new_open = False
    st.session_state.ui_rename_open = False
    st.session_state.form_error = None


def _cancel_delete() -> None:
    st.session_state.ui_delete_open = False


def _delete_active(store: DictionaryStore) -> None:
    dictionary_id = st.session_state.active_dictionary_id
    if dictionary_id is None:
        return
    try:
        store.delete(dictionary_id)
    except AppError as exc:
        show_error(exc)
    st.session_state.ui_delete_open = False
    # Force refresh() to fall through to the first remaining dictionary; if
    # there is none, it lands on the Empty state (Flow 2, guardrail 8).
    st.session_state.active_dictionary_id = None
    refresh(store)


def _form_error() -> None:
    if st.session_state.form_error:
        # Inline, small, error-coloured (UI-UX §8.2), not a page banner: a bad
        # name is a field problem and the form stays open.
        st.sidebar.caption(f":red[{st.session_state.form_error}]")


def _submit_create(store: DictionaryStore, name_key: str) -> None:
    """Form-submit callback: runs before the page renders, so no ``st.rerun``.

    Handling the submit inline and then calling ``st.rerun()`` aborts the run
    before the editor and preview are drawn, which makes Streamlit discard the
    ``script`` widget's state. Doing the mutation in a callback keeps the run
    whole and the typed script intact.
    """
    try:
        created = store.create(st.session_state.get(name_key, ""))
    except AppError as exc:
        st.session_state.form_error = exc.message
        return

    st.session_state.form_error = None
    st.session_state.ui_new_open = False
    # A new dictionary is selected immediately (Flow 2) and starts empty.
    st.session_state.active_dictionary_id = created.id
    refresh(store)


def _submit_rename(store: DictionaryStore, name_key: str) -> None:
    dictionary_id = st.session_state.active_dictionary_id
    if dictionary_id is None:
        return

    try:
        store.rename(dictionary_id, st.session_state.get(name_key, ""))
    except AppError as exc:
        st.session_state.form_error = exc.message
        return

    st.session_state.form_error = None
    st.session_state.ui_rename_open = False
    refresh(store)


def _render_create_form(store: DictionaryStore) -> None:
    if not st.session_state.ui_new_open:
        return

    sequence = st.session_state.ui_new_seq
    name_key = f"create_name_{sequence}"
    with st.sidebar.form(f"create_dictionary_{sequence}"):
        st.text_input("Name", key=name_key, placeholder="Dictionary name")
        st.form_submit_button(
            "Save", on_click=_submit_create, args=(store, name_key)
        )

    st.sidebar.button(
        "Cancel", key=f"cancel_create_{sequence}", on_click=_cancel_form
    )
    _form_error()


def _render_rename_form(store: DictionaryStore, active: Dictionary | None) -> None:
    if not st.session_state.ui_rename_open or active is None:
        return

    sequence = st.session_state.ui_rename_seq
    name_key = f"rename_name_{sequence}"
    with st.sidebar.form(f"rename_dictionary_{sequence}"):
        st.text_input("Name", value=active.name, key=name_key)
        st.form_submit_button(
            "Save", on_click=_submit_rename, args=(store, name_key)
        )

    st.sidebar.button(
        "Cancel", key=f"cancel_rename_{sequence}", on_click=_cancel_form
    )
    _form_error()


def _render_delete_confirm(store: DictionaryStore, active: Dictionary | None) -> None:
    if not st.session_state.ui_delete_open or active is None:
        return

    # Names the object, then states the consequence (UI-UX §8.11).
    st.sidebar.markdown(f"**Delete '{active.name}'?**")
    st.sidebar.caption(
        f"This removes {_count(len(active.rules))}. It cannot be undone."
    )
    cancel_column, delete_column = st.sidebar.columns(2)
    cancel_column.button("Cancel", key="cancel_delete", on_click=_cancel_delete)
    delete_column.button(
        "Delete",
        key="confirm_delete",
        type="primary",
        on_click=_delete_active,
        args=(store,),
    )

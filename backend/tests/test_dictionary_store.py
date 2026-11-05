from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.core import dictionary_store as store_module
from app.core.dictionary_store import DictionaryStore
from app.errors import Conflict, InternalError, LimitExceeded, NotFound, ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def store(tmp_path: Path) -> DictionaryStore:
    return DictionaryStore(tmp_path)


def test_create_persists_and_survives_restart(store, tmp_path):
    created = store.create("Gnani Demo")

    assert (tmp_path / "dictionaries" / f"{created.id}.json").is_file()

    reloaded, warnings = DictionaryStore(tmp_path).list_all()
    assert warnings == []
    assert [item.name for item in reloaded] == ["Gnani Demo"]


def test_duplicate_name_is_rejected_case_insensitively(store):
    store.create("Gnani Demo")

    with pytest.raises(Conflict) as excinfo:
        store.create("gnani demo")
    assert excinfo.value.message == 'A dictionary named "Gnani Demo" already exists.'


def test_empty_and_long_names_are_rejected(store):
    with pytest.raises(ValidationError, match="cannot be empty"):
        store.create("   ")

    with pytest.raises(ValidationError, match="80 characters or fewer"):
        store.create("x" * 81)


def test_rename_keeps_the_filename(store, tmp_path):
    created = store.create("Old Name")
    renamed = store.rename(created.id, "New Name")

    assert renamed.name == "New Name"
    assert renamed.id == created.id
    assert (tmp_path / "dictionaries" / f"{created.id}.json").is_file()

    with pytest.raises(Conflict):
        other = store.create("Other")
        store.rename(other.id, "new name")


def test_delete_removes_the_file_and_second_delete_is_not_found(store):
    created = store.create("Temp")
    store.delete(created.id)

    with pytest.raises(NotFound):
        store.delete(created.id)


def test_unknown_or_malformed_ids_never_touch_the_filesystem(store):
    with pytest.raises(NotFound):
        store.get("../../etc/passwd")
    with pytest.raises(NotFound):
        store.delete("dict_not-a-uuid")


def test_rules_are_added_updated_and_deleted(store):
    dictionary = store.create("Demo")
    _, rule = store.add_rule(
        dictionary.id, source="Timbre", replacement="Tamber"
    )

    assert rule.type == "alias"

    updated_dictionary, updated_rule = store.update_rule(
        rule.id, replacement="Tam-ber"
    )
    assert updated_rule.replacement == "Tam-ber"
    assert updated_dictionary.updated_at >= updated_dictionary.created_at

    after_delete = store.delete_rule(rule.id)
    assert after_delete.rules == []


def test_set_rules_updates_and_adds_in_one_write(store, tmp_path, monkeypatch):
    dictionary = store.create("Demo")
    _, first = store.add_rule(dictionary.id, source="Timbre", replacement="Tamber")
    writes = []
    original_write = store._write

    def counted_write(item):
        writes.append(item)
        original_write(item)

    monkeypatch.setattr(store, "_write", counted_write)

    updated = store.set_rules(
        dictionary.id,
        [(first.id, "Timbre", "Tim-ber"), (None, " Zentara ", " Zen Taara ")],
    )

    assert len(writes) == 1, "Save must not rewrite the file once per row"
    assert [(rule.id, rule.source, rule.replacement) for rule in updated.rules] == [
        (first.id, "Timbre", "Tim-ber"),
        (updated.rules[1].id, "Zentara", "Zen Taara"),
    ]
    assert updated.rules[0].created_at == first.created_at
    assert updated.rules[1].id.startswith("rule_")

    reloaded = DictionaryStore(tmp_path).get(dictionary.id)
    assert [rule.replacement for rule in reloaded.rules] == ["Tim-ber", "Zen Taara"]


def test_set_rules_rejects_duplicate_sources(store):
    dictionary = store.create("Demo")

    with pytest.raises(ValidationError, match="already has a rule"):
        store.set_rules(
            dictionary.id, [(None, "Timbre", "A"), (None, " timbre ", "B")]
        )

    assert store.get(dictionary.id).rules == []


def test_set_rules_rejects_an_unknown_existing_rule_id(store):
    dictionary = store.create("Demo")

    with pytest.raises(NotFound):
        store.set_rules(
            dictionary.id,
            [("rule_00000000-0000-4000-8000-000000000000", "A", "B")],
        )


def test_duplicate_source_is_rejected_case_insensitively(store):
    dictionary = store.create("Demo")
    store.add_rule(dictionary.id, source="Timbre", replacement="Tamber")

    with pytest.raises(ValidationError) as excinfo:
        store.add_rule(dictionary.id, source="TIMBRE", replacement="Tamberr")
    assert excinfo.value.message == 'This dictionary already has a rule for "Timbre".'


def test_rule_update_cannot_collide_with_another_rule(store):
    dictionary = store.create("Demo")
    _, first = store.add_rule(dictionary.id, source="Timbre", replacement="Tamber")
    store.add_rule(dictionary.id, source="Gnani", replacement="Gyaanee")

    with pytest.raises(ValidationError):
        store.update_rule(first.id, source="gnani")


def test_phoneme_rule_type_is_rejected(store):
    dictionary = store.create("Demo")

    with pytest.raises(ValidationError, match="not supported"):
        store.add_rule(
            dictionary.id,
            source="A",
            replacement="B",
            rule_type="phoneme",
        )


def test_rule_limit_is_enforced(store, monkeypatch):
    monkeypatch.setattr(store_module, "MAX_RULES", 1)
    dictionary = store.create("Demo")
    store.add_rule(dictionary.id, source="Timbre", replacement="Tamber")

    with pytest.raises(LimitExceeded, match="maximum for this release"):
        store.add_rule(dictionary.id, source="Gnani", replacement="Gyaanee")


def test_writes_leave_no_temp_files_behind(store, tmp_path):
    created = store.create("Demo")
    store.add_rule(created.id, source="Timbre", replacement="Tamber")

    leftovers = list((tmp_path / "dictionaries").glob("*.tmp"))
    assert leftovers == []


def test_corrupt_future_and_duplicate_source_files_are_skipped(tmp_path):
    dictionary_dir = tmp_path / "dictionaries"
    dictionary_dir.mkdir(parents=True)
    for name in (
        "dict_eeeeeeee-5555-4555-8555-555555555555.json",
        "dict_dddddddd-4444-4444-b444-444444444444.json",
        "dict_cccccccc-3333-4333-a333-333333333333.json",
        "dict_aaaaaaaa-1111-4111-8111-111111111111.json",
    ):
        shutil.copy(FIXTURES / name, dictionary_dir / name)

    dictionaries, warnings = DictionaryStore(tmp_path).list_all()

    assert [item.name for item in dictionaries] == ["Minimal"]
    reasons = {warning.file: warning.reason for warning in warnings}
    assert reasons["dict_eeeeeeee-5555-4555-8555-555555555555.json"] == "invalid JSON"
    assert (
        reasons["dict_dddddddd-4444-4444-b444-444444444444.json"]
        == "created by a newer version"
    )
    assert (
        reasons["dict_cccccccc-3333-4333-a333-333333333333.json"]
        == "duplicate rule source"
    )


def test_reading_a_corrupt_dictionary_by_id_is_an_internal_error(tmp_path):
    dictionary_dir = tmp_path / "dictionaries"
    dictionary_dir.mkdir(parents=True)
    name = "dict_eeeeeeee-5555-4555-8555-555555555555.json"
    shutil.copy(FIXTURES / name, dictionary_dir / name)

    store = DictionaryStore(tmp_path)
    with pytest.raises(InternalError, match="Could not read the dictionary file"):
        store.get("dict_eeeeeeee-5555-4555-8555-555555555555")


def test_seed_fixture_loads_with_three_rules(tmp_path):
    dictionary_dir = tmp_path / "dictionaries"
    dictionary_dir.mkdir(parents=True)
    shutil.copy(
        FIXTURES / "dict_bbbbbbbb-2222-4222-9222-222222222222.json",
        dictionary_dir / "dict_bbbbbbbb-2222-4222-9222-222222222222.json",
    )

    dictionaries, warnings = DictionaryStore(tmp_path).list_all()

    assert warnings == []
    assert len(dictionaries[0].rules) == 3

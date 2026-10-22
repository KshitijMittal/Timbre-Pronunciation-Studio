from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

from app.core.atomic import atomic_write_bytes
from app.errors import Conflict, InternalError, LimitExceeded, NotFound, ValidationError
from app.models.schemas import (
    MAX_NAME_LENGTH,
    MAX_REPLACEMENT_LENGTH,
    MAX_RULES,
    MAX_SOURCE_LENGTH,
    Dictionary,
    Rule,
)

SCHEMA_VERSION = 1
DICTIONARY_ID_PATTERN = re.compile(
    r"^dict_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


@dataclass(frozen=True, slots=True)
class StoreWarning:
    file: str
    reason: str


class _InvalidFile(Exception):
    pass


class DictionaryStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "dictionaries"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def list_all(self) -> tuple[list[Dictionary], list[StoreWarning]]:
        dictionaries: list[Dictionary] = []
        warnings: list[StoreWarning] = []
        seen_names: set[str] = set()

        for path in sorted(self._dir.glob("dict_*.json")):
            try:
                dictionary = self._read_file(path)
            except _InvalidFile as exc:
                warnings.append(StoreWarning(path.name, str(exc)))
                continue

            key = dictionary.name.casefold()
            if key in seen_names:
                warnings.append(StoreWarning(path.name, "duplicate dictionary name"))
                continue

            seen_names.add(key)
            dictionaries.append(dictionary)

        dictionaries.sort(key=lambda item: item.name.casefold())
        return dictionaries, warnings

    def get(self, dictionary_id: str) -> Dictionary:
        path = self._path(dictionary_id)
        if not path.is_file():
            raise NotFound("Dictionary not found.")
        try:
            return self._read_file(path)
        except _InvalidFile as exc:
            raise InternalError(f"Could not read the dictionary file: {exc}.") from exc

    def create(self, name: str) -> Dictionary:
        with self._lock:
            clean_name = _clean_name(name)
            self._assert_name_available(clean_name)
            now = _now()
            dictionary = Dictionary(
                id=f"dict_{uuid4()}",
                name=clean_name,
                created_at=now,
                updated_at=now,
                rules=[],
            )
            self._write(dictionary)
            return dictionary

    def rename(self, dictionary_id: str, name: str) -> Dictionary:
        with self._lock:
            dictionary = self.get(dictionary_id)
            clean_name = _clean_name(name)
            self._assert_name_available(clean_name, exclude_id=dictionary_id)
            updated = dictionary.model_copy(
                update={"name": clean_name, "updated_at": _now()}
            )
            self._write(updated)
            return updated

    def delete(self, dictionary_id: str) -> None:
        with self._lock:
            path = self._path(dictionary_id)
            if not path.is_file():
                raise NotFound("Dictionary not found.")
            path.unlink()

    def add_rule(
        self,
        dictionary_id: str,
        *,
        source: str,
        replacement: str,
        rule_type: str = "alias",
    ) -> tuple[Dictionary, Rule]:
        with self._lock:
            dictionary = self.get(dictionary_id)
            _assert_alias(rule_type)
            clean_source = _clean_source(source)
            clean_replacement = _clean_replacement(replacement)
            self._assert_source_available(dictionary, clean_source)

            if len(dictionary.rules) >= MAX_RULES:
                raise LimitExceeded(
                    f"This dictionary has {MAX_RULES} rules, the maximum for this release."
                )

            now = _now()
            rule = Rule(
                id=f"rule_{uuid4()}",
                source=clean_source,
                replacement=clean_replacement,
                type="alias",
                created_at=now,
                updated_at=now,
            )
            updated = dictionary.model_copy(
                update={"rules": [*dictionary.rules, rule], "updated_at": now}
            )
            self._write(updated)
            return updated, rule

    def update_rule(
        self,
        rule_id: str,
        *,
        source: str | None = None,
        replacement: str | None = None,
        rule_type: str | None = None,
    ) -> tuple[Dictionary, Rule]:
        with self._lock:
            dictionary, rule = self.find_rule(rule_id)

            if rule_type is not None:
                _assert_alias(rule_type)

            clean_source = _clean_source(source) if source is not None else rule.source
            clean_replacement = (
                _clean_replacement(replacement)
                if replacement is not None
                else rule.replacement
            )
            self._assert_source_available(dictionary, clean_source, exclude_rule_id=rule_id)

            now = _now()
            updated_rule = rule.model_copy(
                update={
                    "source": clean_source,
                    "replacement": clean_replacement,
                    "updated_at": now,
                }
            )
            rules = [
                updated_rule if item.id == rule_id else item for item in dictionary.rules
            ]
            updated = dictionary.model_copy(update={"rules": rules, "updated_at": now})
            self._write(updated)
            return updated, updated_rule

    def delete_rule(self, rule_id: str) -> Dictionary:
        with self._lock:
            dictionary, rule = self.find_rule(rule_id)
            now = _now()
            updated = dictionary.model_copy(
                update={
                    "rules": [item for item in dictionary.rules if item.id != rule.id],
                    "updated_at": now,
                }
            )
            self._write(updated)
            return updated

    def find_rule(self, rule_id: str) -> tuple[Dictionary, Rule]:
        dictionaries, _ = self.list_all()
        for dictionary in dictionaries:
            for rule in dictionary.rules:
                if rule.id == rule_id:
                    return dictionary, rule
        raise NotFound("Rule not found.")

    def _path(self, dictionary_id: str) -> Path:
        # The ID is user-supplied via the URL, so it never reaches the filesystem
        # until it matches the generated shape (Backend Schema §3.3, §3.4).
        if not DICTIONARY_ID_PATTERN.fullmatch(dictionary_id):
            raise NotFound("Dictionary not found.")
        return self._dir / f"{dictionary_id}.json"

    def _read_file(self, path: Path) -> Dictionary:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _InvalidFile("invalid JSON") from exc

        if not isinstance(raw, dict):
            raise _InvalidFile("not a JSON object")

        version = raw.get("schema_version")
        if version != SCHEMA_VERSION:
            if isinstance(version, int) and version > SCHEMA_VERSION:
                raise _InvalidFile("created by a newer version")
            raise _InvalidFile("missing or invalid schema_version")

        try:
            dictionary = Dictionary.model_validate(raw)
        except PydanticValidationError as exc:
            raise _InvalidFile("failed validation") from exc

        if dictionary.id != path.stem:
            raise _InvalidFile("id does not match filename")

        _check_invariants(dictionary)
        return dictionary

    def _write(self, dictionary: Dictionary) -> None:
        try:
            _check_invariants(dictionary)
        except _InvalidFile as exc:
            raise InternalError(
                "Refusing to write an invalid dictionary file. " + str(exc) + "."
            ) from exc

        payload = json.dumps(
            dictionary.model_dump(mode="json"), indent=2, ensure_ascii=False
        ).encode("utf-8")
        try:
            atomic_write_bytes(self._path(dictionary.id), payload)
        except OSError as exc:
            raise InternalError(
                "Could not save the dictionary. Check that the data folder is writable."
            ) from exc

    def _assert_name_available(self, name: str, exclude_id: str | None = None) -> None:
        dictionaries, _ = self.list_all()
        for dictionary in dictionaries:
            if dictionary.id != exclude_id and dictionary.name.casefold() == name.casefold():
                raise Conflict(f'A dictionary named "{dictionary.name}" already exists.')

    @staticmethod
    def _assert_source_available(
        dictionary: Dictionary, source: str, exclude_rule_id: str | None = None
    ) -> None:
        for rule in dictionary.rules:
            if rule.id != exclude_rule_id and rule.source.casefold() == source.casefold():
                raise ValidationError(
                    f'This dictionary already has a rule for "{rule.source}".'
                )


def _check_invariants(dictionary: Dictionary) -> None:
    if not DICTIONARY_ID_PATTERN.fullmatch(dictionary.id):
        raise _InvalidFile("invalid dictionary id")
    if dictionary.updated_at < dictionary.created_at:
        raise _InvalidFile("updated_at is before created_at")

    rule_ids: set[str] = set()
    sources: set[str] = set()
    for rule in dictionary.rules:
        if rule.id in rule_ids:
            raise _InvalidFile("duplicate rule id")
        rule_ids.add(rule.id)

        key = rule.source.casefold()
        if key in sources:
            raise _InvalidFile("duplicate rule source")
        sources.add(key)

        if rule.updated_at < rule.created_at:
            raise _InvalidFile("rule updated_at is before created_at")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean_name(name: str) -> str:
    clean = name.strip()
    if not clean:
        raise ValidationError("Dictionary name cannot be empty.")
    if len(clean) > MAX_NAME_LENGTH:
        raise ValidationError(
            f"Dictionary name must be {MAX_NAME_LENGTH} characters or fewer."
        )
    return clean


def _clean_source(source: str) -> str:
    clean = source.strip()
    if not clean:
        raise ValidationError("Source term cannot be empty.")
    if len(clean) > MAX_SOURCE_LENGTH:
        raise ValidationError(
            f"Source term must be {MAX_SOURCE_LENGTH} characters or fewer."
        )
    return clean


def _clean_replacement(replacement: str) -> str:
    clean = replacement.strip()
    if not clean:
        raise ValidationError("Replacement cannot be empty.")
    if len(clean) > MAX_REPLACEMENT_LENGTH:
        raise ValidationError(
            f"Replacement must be {MAX_REPLACEMENT_LENGTH} characters or fewer."
        )
    return clean


def _assert_alias(rule_type: str) -> None:
    if rule_type != "alias":
        raise ValidationError(
            f"Rule type '{rule_type}' is not supported. Only 'alias' rules are available in this release."
        )

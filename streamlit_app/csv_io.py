"""CSV import/export for dictionaries.

Pure Python on purpose: no Streamlit and no ``app.*`` imports, so it can be
tested on its own and cannot touch the network. The caller passes the schema
limits in, which keeps this file from drifting from ``app.models.schemas``.

Import is forgiving in one direction only: a bad row is reported and skipped,
never silently rewritten. The caller shows the errors before it writes anything.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

# Header names people actually write. Matching is case-insensitive and trimmed.
_TERM = ("term", "word", "source", "original")
_SAYS = ("says", "replacement", "pronunciation", "respelling", "adjusted")

MAX_REPORTED_ERRORS = 12


@dataclass(frozen=True, slots=True)
class Row:
    source: str
    replacement: str


def parse(
    data: bytes, *, max_source: int, max_replacement: int
) -> tuple[list[Row], list[str]]:
    """Return the usable rows and every problem found, in file order."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["File is not UTF-8 text. Re-save it as CSV UTF-8 and try again."]

    if not text.strip():
        return [], ["File is empty."]

    reader = csv.reader(io.StringIO(text, newline=""))
    numbered: list[tuple[int, list[str]]] = []
    try:
        for row in reader:
            # ``line_num`` is where the row ended, so a quoted field spanning
            # several lines still reports a line the user can find.
            numbered.append((reader.line_num, row))
    except csv.Error as exc:
        return [], [f"Could not read the CSV: {exc}."]

    header_line, header = next(
        ((line, row) for line, row in numbered if any(cell.strip() for cell in row)),
        (0, []),
    )
    if not header:
        return [], ["File is empty."]

    term_at = _find(header, _TERM)
    says_at = _find(header, _SAYS)
    if term_at is None or says_at is None:
        return [], [
            "The first row must be a header with a term column and a says column "
            "(for example: term,says)."
        ]

    found: list[Row] = []
    errors: list[str] = []
    seen: dict[str, int] = {}

    for line, row in numbered:
        if line <= header_line:
            continue
        if not any(cell.strip() for cell in row):
            continue  # blank line between blocks

        if len(row) <= max(term_at, says_at):
            errors.append(f"Line {line}: missing a column.")
            continue

        source = row[term_at].strip()
        replacement = row[says_at].strip()

        if not source:
            errors.append(f"Line {line}: the term is empty.")
            continue
        if not replacement:
            errors.append(f"Line {line}: the pronunciation is empty for '{source}'.")
            continue
        if len(source) > max_source:
            errors.append(
                f"Line {line}: '{source[:20]}…' is longer than {max_source} characters."
            )
            continue
        if len(replacement) > max_replacement:
            errors.append(
                f"Line {line}: the pronunciation for '{source}' is longer than "
                f"{max_replacement} characters."
            )
            continue

        key = source.casefold()
        if key in seen:
            errors.append(
                f"Line {line}: duplicate term '{source}' (first seen on line {seen[key]})."
            )
            continue

        seen[key] = line
        found.append(Row(source=source, replacement=replacement))

    if not found and not errors:
        errors.append("No rows found under the header.")

    if len(errors) > MAX_REPORTED_ERRORS:
        rest = len(errors) - MAX_REPORTED_ERRORS
        errors = errors[:MAX_REPORTED_ERRORS] + [f"… and {rest} more problem(s)."]

    return found, errors


def to_csv(rows: list[Row] | list[tuple[str, str]]) -> bytes:
    """One header row, then every term and its pronunciation.

    UTF-8 with a BOM: Excel opens the file correctly without an import wizard.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["term", "says"])
    for row in rows:
        source, replacement = (row.source, row.replacement) if isinstance(row, Row) else row
        writer.writerow([source, replacement])
    return buffer.getvalue().encode("utf-8-sig")


def _find(header: list[str], aliases: tuple[str, ...]) -> int | None:
    for index, cell in enumerate(header):
        if cell.strip().casefold() in aliases:
            return index
    return None

"""CSV import/export: forgiving on input, exact on output, never silent.

Pure module, no Streamlit, no network.
"""

from __future__ import annotations

from csv_io import Row, parse, to_csv

LIMITS = {"max_source": 120, "max_replacement": 200}


def test_reads_a_plain_header_and_bom():
    data = "\ufeffterm,says\r\nCoimbatore,Ko-yam-ba-tore\r\n".encode("utf-8")
    rows, errors = parse(data, **LIMITS)

    assert errors == []
    assert rows == [Row("Coimbatore", "Ko-yam-ba-tore")]


def test_accepts_header_aliases_and_any_column_order():
    data = b"pronunciation,word\nKo-yam-ba-tore,Coimbatore\n"
    rows, errors = parse(data, **LIMITS)

    assert errors == []
    assert rows == [Row("Coimbatore", "Ko-yam-ba-tore")]


def test_skips_blank_lines_between_blocks():
    data = b"term,says\n\nTimbre,Tim-ber\n\n\nGnani,Gyaa-nee\n"
    rows, errors = parse(data, **LIMITS)

    assert errors == []
    assert [row.source for row in rows] == ["Timbre", "Gnani"]


def test_reports_duplicates_case_insensitively_with_their_line():
    data = b"term,says\nTimbre,Tim-ber\n\ntimbre,Tim-ber-two\n"
    rows, errors = parse(data, **LIMITS)

    assert [row.source for row in rows] == ["Timbre"]
    assert len(errors) == 1
    assert "duplicate" in errors[0]
    assert "Line 4" in errors[0]


def test_reports_empty_and_over_long_cells_without_dropping_the_rest():
    data = (
        b"term,says\n"
        b",nope\n"
        b"Timbre,\n"
        b"Long," + b"x" * 201 + b"\n"
        b"Gnani,Gyaa-nee\n"
    )
    rows, errors = parse(data, **LIMITS)

    assert [row.source for row in rows] == ["Gnani"]
    assert len(errors) == 3
    assert any("term is empty" in error for error in errors)
    assert any("pronunciation is empty" in error for error in errors)
    assert any("longer than 200" in error for error in errors)


def test_rejects_a_file_without_a_term_and_says_header():
    rows, errors = parse(b"a,b\n1,2\n", **LIMITS)

    assert rows == []
    assert "header" in errors[0]


def test_rejects_non_utf8_and_empty_files():
    assert "UTF-8" in parse(b"\xff\xfe\x00", **LIMITS)[1][0]
    assert parse(b"   \n", **LIMITS) == ([], ["File is empty."])


def test_caps_the_error_report_instead_of_dumping_the_file():
    body = b"term,says\n" + b"".join(b",bad\n" for _ in range(20))
    rows, errors = parse(body, **LIMITS)

    assert rows == []
    assert len(errors) == 13
    assert errors[-1] == "\u2026 and 8 more problem(s)."


def test_export_is_excel_friendly_and_round_trips():
    exported = to_csv([Row("Timbre", "Tim-ber"), ("Gnani", "Gyaa-nee")])

    assert exported.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in exported
    assert parse(exported, **LIMITS)[0] == [
        Row("Timbre", "Tim-ber"),
        Row("Gnani", "Gyaa-nee"),
    ]

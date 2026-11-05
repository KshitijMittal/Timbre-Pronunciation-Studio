import time

import pytest

from app.core.pronunciation_rules import Rule, apply_rules


def rule(source: str, replacement: str, rule_id: str = "r1", created_at: str = "") -> Rule:
    return Rule(source=source, replacement=replacement, rule_id=rule_id, created_at=created_at)


def test_simple_whole_word_replacement():
    result = apply_rules("Gnani AI makes voices.", [rule("Gnani", "Gyaanee")])
    assert result.transformed_text == "Gyaanee AI makes voices."
    assert result.changed is True
    assert result.matches[0].count == 1


def test_plural_is_not_matched():
    result = apply_rules("The Gnanis are here.", [rule("Gnani", "Gyaanee")])
    assert result.transformed_text == "The Gnanis are here."
    assert result.changed is False
    assert result.matches[0].count == 0


def test_apostrophe_is_a_boundary():
    result = apply_rules("Gnani's demo", [rule("Gnani", "Gyaanee")])
    assert result.transformed_text == "Gyaanee's demo"


@pytest.mark.parametrize("text", ["(Gnani) said", "Gnani, said", "said Gnani.", "Gnani"])
def test_punctuation_boundaries(text):
    result = apply_rules(text, [rule("Gnani", "Gyaanee")])
    assert "Gyaanee" in result.transformed_text
    assert "Gnani" not in result.transformed_text


def test_longest_source_wins():
    result = apply_rules("Gnani AI", [rule("Gnani", "Gyaanee"), rule("Gnani AI", "Gyaanee A I", "r2")])
    assert result.transformed_text == "Gyaanee A I"


def test_matching_is_case_insensitive():
    result = apply_rules("Timbre, timbre, TIMBRE", [rule("Timbre", "Tamber")])
    assert result.transformed_text == "Tamber, Tamber, Tamber"


def test_replacement_case_is_preserved_verbatim():
    result = apply_rules("TIMBRE", [rule("Timbre", "TamBer")])
    assert result.transformed_text == "TamBer"


def test_no_substring_matching():
    result = apply_rules("Ramachandran and Program", [rule("Ram", "Raam")])
    assert result.transformed_text == "Ramachandran and Program"


def test_empty_rule_list_returns_input_unchanged():
    result = apply_rules("Nothing to do", [])
    assert result.transformed_text == "Nothing to do"
    assert result.changed is False
    assert result.matches == ()


def test_zero_match_rule_is_reported():
    result = apply_rules("Only Gnani here", [rule("Gnani", "Gyaanee", "r1"), rule("Timbre", "Tamber", "r2")])
    counts = {match.rule_id: match.count for match in result.matches}
    assert counts == {"r1": 1, "r2": 0}


def test_replacement_is_not_rescanned():
    result = apply_rules("Gnani", [rule("Gnani", "Timbre", "r1"), rule("Timbre", "Tamber", "r2")])
    assert result.transformed_text == "Timbre"


def test_chained_rules_are_detected():
    result = apply_rules("Gnani", [rule("Gnani", "Timbre", "r1"), rule("Timbre", "Tamber", "r2")])
    assert "r1" in result.chained_rule_ids
    assert "r2" not in result.chained_rule_ids


def test_a_source_inside_a_longer_word_is_not_a_chain():
    result = apply_rules(
        "Gyaanee",
        [rule("Gyaanee", "X", "r1"), rule("yaan", "Y", "r2")],
    )

    assert result.chained_rule_ids == ()


def test_markup_replacement_is_passed_through():
    result = apply_rules("Gnani", [rule("Gnani", "<phoneme>x</phoneme>")])
    assert result.transformed_text == "<phoneme>x</phoneme>"


def test_unicode_source_matches():
    result = apply_rules("ज्ञानी बोलता है", [rule("ज्ञानी", "Gyaanee")])
    assert result.transformed_text == "Gyaanee बोलता है"


def test_empty_text_returns_zero_counts():
    result = apply_rules("", [rule("Gnani", "Gyaanee")])
    assert result.transformed_text == ""
    assert result.matches[0].count == 0


def test_determinism_across_runs():
    rules = [rule("Gnani", "Gyaanee", "r1"), rule("Gnani AI", "Gyaanee A I", "r2", "2026-01-01T00:00:00Z")]
    first = apply_rules("Gnani AI and Gnani", rules)
    second = apply_rules("Gnani AI and Gnani", rules)
    assert first.transformed_text == second.transformed_text
    assert first.matches == second.matches


def test_fifty_rules_on_long_text_stay_fast():
    rules = [rule(f"term{i:02d}", f"repl{i:02d}", f"r{i}") for i in range(50)]
    text = ("term00 term01 term49 lorem ipsum dolor sit amet " * 45)[:2000]
    started = time.perf_counter()
    result = apply_rules(text, rules)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert "term00" not in result.transformed_text
    assert elapsed_ms < 50

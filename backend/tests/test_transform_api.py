from __future__ import annotations

UNKNOWN_DICT = "dict_00000000-0000-4000-8000-000000000000"


def make_dictionary(client, name="Demo") -> str:
    response = client.post("/api/dictionaries", json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def add_rule(client, dictionary_id, source, replacement) -> dict:
    response = client.post(
        f"/api/dictionaries/{dictionary_id}/rules",
        json={"source": source, "replacement": replacement},
    )
    assert response.status_code == 201
    return response.json()


def test_worked_example_keeps_original_and_transforms_copy(client):
    dictionary_id = make_dictionary(client)
    add_rule(client, dictionary_id, "Gnani", "Gyaanee")

    response = client.post(
        "/api/transform",
        json={"text": "Gnani AI makes voices.", "dictionary_id": dictionary_id},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["original_text"] == "Gnani AI makes voices."
    assert body["transformed_text"] == "Gyaanee AI makes voices."
    assert body["changed"] is True
    assert body["char_count"] == 22
    assert body["limit"] == {"warn_at": 800, "block_at": 2000, "status": "ok"}
    assert body["matches"][0]["count"] == 1


def test_whole_word_examples_from_the_prd(client):
    dictionary_id = make_dictionary(client)
    add_rule(client, dictionary_id, "Ram", "Raam")

    response = client.post(
        "/api/transform",
        json={"text": "Ramachandran and Ram", "dictionary_id": dictionary_id},
    )

    assert response.json()["transformed_text"] == "Ramachandran and Raam"


def test_zero_match_rules_are_reported_with_a_warning(client):
    dictionary_id = make_dictionary(client)
    add_rule(client, dictionary_id, "Timbre", "Tamber")
    add_rule(client, dictionary_id, "Bengaluru", "Bengalooru")

    response = client.post(
        "/api/transform",
        json={"text": "Timbre speaks clearly.", "dictionary_id": dictionary_id},
    )

    body = response.json()
    counts = {match["source"]: match["count"] for match in body["matches"]}
    assert counts == {"Timbre": 1, "Bengaluru": 0}
    assert [w["code"] for w in body["warnings"]] == ["RULE_NOT_FOUND_IN_TEXT"]


def test_markup_replacement_produces_a_warning_but_is_applied(client):
    dictionary_id = make_dictionary(client)
    add_rule(client, dictionary_id, "Gnani", "<phoneme>Gyaanee</phoneme>")

    response = client.post(
        "/api/transform",
        json={"text": "Gnani", "dictionary_id": dictionary_id},
    )

    body = response.json()
    assert body["transformed_text"] == "<phoneme>Gyaanee</phoneme>"
    assert "REPLACEMENT_CONTAINS_MARKUP" in [w["code"] for w in body["warnings"]]


def test_chained_rules_are_detected(client):
    dictionary_id = make_dictionary(client)
    add_rule(client, dictionary_id, "Gnani", "Timbre")
    add_rule(client, dictionary_id, "Timbre", "Tamber")

    response = client.post(
        "/api/transform",
        json={"text": "Gnani", "dictionary_id": dictionary_id},
    )

    body = response.json()
    assert body["transformed_text"] == "Timbre"
    assert "RULE_CHAIN_DETECTED" in [w["code"] for w in body["warnings"]]


def test_inline_rules_take_precedence_over_the_dictionary(client):
    dictionary_id = make_dictionary(client)
    add_rule(client, dictionary_id, "Timbre", "FromDictionary")

    response = client.post(
        "/api/transform",
        json={
            "text": "Timbre and Gnani",
            "dictionary_id": dictionary_id,
            "rules": [{"source": "Gnani", "replacement": "Gyaanee"}],
        },
    )

    assert response.json()["transformed_text"] == "Timbre and Gyaanee"


def test_inline_duplicate_sources_are_rejected(client):
    response = client.post(
        "/api/transform",
        json={
            "text": "Timbre",
            "rules": [
                {"source": "Timbre", "replacement": "A"},
                {"source": "TIMBRE", "replacement": "B"},
            ],
        },
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "VALIDATION_ERROR"
    assert error["message"] == 'This dictionary already has a rule for "TIMBRE".'


def test_blank_inline_source_is_rejected(client):
    response = client.post(
        "/api/transform",
        json={"text": "Gnani", "rules": [{"source": "  ", "replacement": "X"}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Source term cannot be empty."


def test_blank_inline_replacement_is_rejected_instead_of_deleting_the_word(client):
    response = client.post(
        "/api/transform",
        json={"text": "Gnani AI", "rules": [{"source": "Gnani", "replacement": " "}]},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Replacement cannot be empty."


def test_script_over_the_block_limit_is_rejected_with_the_canonical_message(client):
    response = client.post(
        "/api/transform",
        json={"text": "a" * 2001, "rules": []},
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "LIMIT_EXCEEDED"
    assert error["message"] == "Script is 2,001 characters. The limit is 2,000."


def test_trailing_whitespace_does_not_count_toward_the_block_limit(client):
    response = client.post(
        "/api/transform",
        json={"text": "a" * 2000 + " ", "rules": []},
    )

    assert response.status_code == 200
    assert response.json()["char_count"] == 2001


def test_long_script_warns_without_blocking(client):
    response = client.post(
        "/api/transform",
        json={"text": "a" * 801, "rules": []},
    )

    assert response.status_code == 200
    assert response.json()["limit"]["status"] == "warn"


def test_empty_text_returns_an_empty_unchanged_result(client):
    response = client.post("/api/transform", json={"text": ""})

    assert response.status_code == 200
    body = response.json()
    assert body["transformed_text"] == ""
    assert body["changed"] is False
    assert body["matches"] == []


def test_unknown_dictionary_returns_the_not_found_envelope(client):
    response = client.post(
        "/api/transform",
        json={"text": "Gnani", "dictionary_id": UNKNOWN_DICT},
    )

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["type"] == "NOT_FOUND"
    assert error["message"] == "Dictionary not found."

from __future__ import annotations

from fastapi.testclient import TestClient

from app import main as app_main

UNKNOWN_RULE = "rule_00000000-0000-4000-8000-000000000000"


def test_duplicate_dictionary_name_returns_conflict(client):
    assert client.post("/api/dictionaries", json={"name": "Gnani Demo"}).status_code == 201

    response = client.post("/api/dictionaries", json={"name": "GNANI DEMO"})

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "error": {
            "type": "CONFLICT",
            "message": 'A dictionary named "Gnani Demo" already exists.',
        },
    }


def test_unsupported_rule_type_returns_validation_error(client):
    dictionary = client.post("/api/dictionaries", json={"name": "Demo"}).json()

    response = client.post(
        f"/api/dictionaries/{dictionary['id']}/rules",
        json={"source": "A", "replacement": "B", "type": "phoneme"},
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["type"] == "VALIDATION_ERROR"
    assert (
        error["message"]
        == "Rule type 'phoneme' is not supported. Only 'alias' rules are available in this release."
    )


def test_unknown_rule_returns_not_found(client):
    response = client.patch(f"/api/rules/{UNKNOWN_RULE}", json={"replacement": "X"})

    assert response.status_code == 404
    assert response.json()["error"] == {
        "type": "NOT_FOUND",
        "message": "Rule not found.",
    }


def test_unknown_route_uses_the_error_envelope(client):
    response = client.get("/api/not-a-route")

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "NOT_FOUND"


def test_unknown_api_route_still_404s_when_the_ui_is_built(settings, monkeypatch, tmp_path):
    """The SPA catch-all must not answer an unknown API path with index.html."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "assets" / "app.js").write_text("// js", encoding="utf-8")
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(app_main, "FRONTEND_DIST", dist)
    client = TestClient(app_main.create_app(settings))

    assert client.get("/").status_code == 200
    assert client.get("/dictionaries/new").status_code == 200

    response = client.get("/api/not-a-route")

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "NOT_FOUND"


def test_body_validation_uses_the_error_envelope(client):
    response = client.post("/api/dictionaries", json={"name": ""})

    # Schema-level rejections are 422 (TRD §7.4); the canonical 400 messages in
    # Backend Schema §11.3 apply once a value reaches domain validation, e.g. a
    # whitespace-only name.
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["type"] == "VALIDATION_ERROR"
    assert body["error"]["details"] == [{"field": "name", "issue": "string_too_short"}]


def test_unexpected_errors_use_the_error_envelope(app):
    def boom() -> None:
        raise RuntimeError("kaboom")

    app.add_api_route("/api/boom", boom, methods=["GET"])
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/boom")

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "error": {
            "type": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
        },
    }

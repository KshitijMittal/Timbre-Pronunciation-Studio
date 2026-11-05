from __future__ import annotations

import pytest

from app.errors import UpstreamTimeoutError


def synth_payload(**overrides) -> dict:
    payload = {
        "text": "Gyaanee A I makes voices.",
        "model": "timbre-v3.0",
        "voice": "Lakshmi",
    }
    payload.update(overrides)
    return payload


def test_synthesis_returns_playable_audio_and_echoes_settings(client, fake_tts):
    response = client.post("/api/synthesize", json=synth_payload())

    assert response.status_code == 200
    body = response.json()
    assert len(body["cache_key"]) == 64
    assert body["audio_url"] == f"/api/audio/{body['cache_key']}.wav"
    assert body["cached"] is False
    assert body["bytes"] > 0
    assert body["settings"] == {
        "model": "timbre-v3.0",
        "voice": "Lakshmi",
        "language": "en-IN",
        "speed": 1.0,
        "sample_rate": 48000,
        "num_channels": 1,
        "sample_width": 2,
        "container": "wav",
    }
    assert fake_tts.calls[0]["text"] == "Gyaanee A I makes voices."


def test_second_identical_request_is_served_from_cache(client, fake_tts):
    first = client.post("/api/synthesize", json=synth_payload())
    second = client.post("/api/synthesize", json=synth_payload())

    assert first.json()["cache_key"] == second.json()["cache_key"]
    assert second.json()["cached"] is True
    assert len(fake_tts.calls) == 1


def test_changing_voice_changes_the_cache_key(client, fake_tts):
    first = client.post("/api/synthesize", json=synth_payload())
    second = client.post("/api/synthesize", json=synth_payload(voice="Shivani"))

    assert first.json()["cache_key"] != second.json()["cache_key"]
    assert len(fake_tts.calls) == 2


def test_audio_url_serves_wav_bytes(client, fake_tts):
    body = client.post("/api/synthesize", json=synth_payload()).json()

    response = client.get(body["audio_url"])

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "private, max-age=3600"
    assert len(response.content) == body["bytes"]


def test_unknown_audio_key_returns_not_found(client):
    response = client.get("/api/audio/" + "0" * 64 + ".wav")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Audio not found."


def test_malformed_audio_key_returns_not_found(client):
    response = client.get("/api/audio/not-a-key.wav")

    assert response.status_code == 404
    assert response.json()["error"] == {"type": "NOT_FOUND", "message": "Audio not found."}


def test_voice_must_belong_to_the_model(client, fake_tts):
    response = client.post("/api/synthesize", json=synth_payload(voice="Nalini"))

    assert response.status_code == 400
    assert (
        response.json()["error"]["message"]
        == 'Voice "Nalini" is not available for model "timbre-v3.0".'
    )
    assert fake_tts.calls == []


def test_unknown_model_is_rejected(client, fake_tts):
    response = client.post("/api/synthesize", json=synth_payload(model="timbre-v9.9"))

    assert response.status_code == 400
    assert response.json()["error"]["message"] == 'Model "timbre-v9.9" is not available.'


def test_only_english_is_accepted(client, fake_tts):
    response = client.post("/api/synthesize", json=synth_payload(language="hi-IN"))

    assert response.status_code == 400
    assert (
        response.json()["error"]["message"]
        == "Only English (en-IN) is supported in this release."
    )


@pytest.mark.parametrize("speed", [0.5, 1.2])
def test_speed_must_stay_within_the_api_range(client, fake_tts, speed):
    response = client.post("/api/synthesize", json=synth_payload(speed=speed))

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Speed must be between 0.85 and 1.15."


def test_script_over_the_block_limit_is_rejected(client, fake_tts):
    response = client.post("/api/synthesize", json=synth_payload(text="a" * 2001))

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "LIMIT_EXCEEDED"
    assert fake_tts.calls == []


def test_whitespace_only_text_is_rejected(client, fake_tts):
    response = client.post("/api/synthesize", json=synth_payload(text="   "))

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "Script cannot be empty."


def test_upstream_timeout_is_surfaced_as_504(app, client):
    class TimeoutTimbre:
        def synthesize(self, **kwargs):
            raise UpstreamTimeoutError(
                "The request timed out. Shorten the script or try again."
            )

    app.state.tts = TimeoutTimbre()
    response = client.post("/api/synthesize", json=synth_payload())

    assert response.status_code == 504
    error = response.json()["error"]
    assert error["type"] == "UPSTREAM_TIMEOUT"
    assert error["message"] == "The request timed out. Shorten the script or try again."


def test_a_cache_write_failure_still_returns_the_paid_audio(app, client, fake_tts):
    def fail(*_args, **_kwargs):
        raise OSError("disk full")

    app.state.cache.store = fail

    response = client.post("/api/synthesize", json=synth_payload())

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert response.json()["bytes"] > 0
    assert len(fake_tts.calls) == 1

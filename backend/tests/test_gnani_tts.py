from __future__ import annotations

import json

import pytest
import requests

from app.core.gnani_tts import TimbreClient
from app.errors import (
    UpstreamAuthError,
    UpstreamBadRequestError,
    UpstreamError,
    UpstreamForbiddenError,
    UpstreamRateLimitError,
    UpstreamTimeoutError,
    UpstreamUnreachableError,
)


def make_response(status: int, payload: dict | None = None, content: bytes = b""):
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode("utf-8") if payload else content
    return response


class FakeSession:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[tuple[str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def make_client(session: FakeSession) -> TimbreClient:
    return TimbreClient(
        api_key="secret-key",
        base_url="https://api.example.test/",
        timeout_seconds=12,
        session=session,
    )


def call(client: TimbreClient):
    return client.synthesize(
        text="Gnani AI",
        model="timbre-v3.0",
        voice="Lakshmi",
        language="en-IN",
        speed=1.0,
    )


def test_request_matches_the_documented_shape():
    session = FakeSession(make_response(200, content=b"RIFFdata"))
    outcome = call(make_client(session))

    url, kwargs = session.calls[0]
    assert url == "https://api.example.test/api/v1/tts/inference"
    assert kwargs["headers"] == {
        "Content-Type": "application/json",
        "X-API-Key-ID": "secret-key",
    }
    assert kwargs["timeout"] == 12
    assert kwargs["json"] == {
        "text": "Gnani AI",
        "model": "timbre-v3.0",
        "voice": "Lakshmi",
        "language": "en-IN",
        "speed": 1.0,
        "audio_config": {
            "sample_rate": 48000,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "wav",
        },
    }
    assert outcome.audio == b"RIFFdata"
    assert outcome.status == 200


def test_empty_audio_body_is_an_upstream_error():
    session = FakeSession(make_response(200, content=b""))

    with pytest.raises(UpstreamError, match="empty audio response"):
        call(make_client(session))


def test_bad_request_passes_upstream_detail_through():
    session = FakeSession(
        make_response(
            400,
            {
                "error": {
                    "type": "INVALID_REQUEST_ERROR",
                    "message": "Invalid text or audio configuration.",
                }
            },
        )
    )

    with pytest.raises(UpstreamBadRequestError) as excinfo:
        call(make_client(session))

    assert excinfo.value.message == "Invalid text or audio configuration."
    assert excinfo.value.details == [
        {
            "field": "upstream",
            "issue": "INVALID_REQUEST_ERROR",
            "message": "Invalid text or audio configuration.",
        }
    ]


def test_flat_upstream_error_body_is_parsed():
    # Live shape observed 20 Oct 2026: no error object, message at the top level.
    session = FakeSession(
        make_response(
            400,
            {
                "success": False,
                "status_code": 400,
                "message": "Invalid request: Voice 'Nalini' is not supported.",
            },
        )
    )

    with pytest.raises(UpstreamBadRequestError) as excinfo:
        call(make_client(session))

    assert excinfo.value.message == "Invalid request: Voice 'Nalini' is not supported."
    assert excinfo.value.details == [
        {
            "field": "upstream",
            "issue": "HTTP_400",
            "message": "Invalid request: Voice 'Nalini' is not supported.",
        }
    ]


@pytest.mark.parametrize(
    ("status", "error_class", "message"),
    [
        (401, UpstreamAuthError, "Timbre rejected the API key. Check the key in backend/.env."),
        (
            403,
            UpstreamForbiddenError,
            "Timbre refused the request. Check permissions and remaining credits.",
        ),
        (429, UpstreamRateLimitError, "Too many requests. Wait a moment, then try again."),
        (500, UpstreamError, "Timbre is temporarily unavailable. Try again shortly."),
        (503, UpstreamError, "Timbre is temporarily unavailable. Try again shortly."),
    ],
)
def test_status_mapping(status, error_class, message):
    session = FakeSession(make_response(status))

    with pytest.raises(error_class) as excinfo:
        call(make_client(session))

    assert excinfo.value.message == message


def test_timeout_and_unreachable_are_typed():
    with pytest.raises(UpstreamTimeoutError):
        call(make_client(FakeSession(error=requests.Timeout())))

    with pytest.raises(UpstreamUnreachableError):
        call(make_client(FakeSession(error=requests.ConnectionError())))

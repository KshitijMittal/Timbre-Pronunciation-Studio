from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from app.errors import (
    UpstreamAuthError,
    UpstreamBadRequestError,
    UpstreamError,
    UpstreamForbiddenError,
    UpstreamRateLimitError,
    UpstreamTimeoutError,
    UpstreamUnreachableError,
)

logger = logging.getLogger(__name__)

DEFAULT_AUDIO_CONFIG: dict[str, Any] = {
    "sample_rate": 48000,
    "num_channels": 1,
    "sample_width": 2,
    "encoding": "linear_pcm",
    "container": "wav",
}


@dataclass(frozen=True, slots=True)
class SynthesisOutcome:
    audio: bytes
    status: int
    elapsed_ms: int


class TimbreClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    def synthesize(
        self,
        *,
        text: str,
        model: str,
        voice: str,
        language: str,
        speed: float,
        audio_config: dict[str, Any] | None = None,
    ) -> SynthesisOutcome:
        payload = {
            "text": text,
            "model": model,
            "voice": voice,
            "language": language,
            "speed": speed,
            "audio_config": audio_config or DEFAULT_AUDIO_CONFIG,
        }

        started = time.perf_counter()
        try:
            response = self._session.post(
                f"{self._base_url}/api/v1/tts/inference",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key-ID": self._api_key,
                },
                json=payload,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            logger.warning("timbre timeout model=%s chars=%d", model, len(text))
            raise UpstreamTimeoutError(
                "The request timed out. Shorten the script or try again."
            ) from exc
        except requests.ConnectionError as exc:
            logger.warning("timbre unreachable model=%s", model)
            raise UpstreamUnreachableError(
                "Cannot reach the Timbre API. Check your connection."
            ) from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "timbre status=%d model=%s voice=%s chars=%d elapsed_ms=%d",
            response.status_code,
            model,
            voice,
            len(text),
            elapsed_ms,
        )

        if response.status_code == 200:
            if not response.content:
                raise UpstreamError("Timbre returned an empty audio response.")
            return SynthesisOutcome(response.content, 200, elapsed_ms)

        raise _map_failure(response)


def _map_failure(response: requests.Response) -> Exception:
    upstream_type, upstream_message = _read_error_body(response)
    details = (
        [
            {
                "field": "upstream",
                "issue": upstream_type or f"HTTP_{response.status_code}",
                "message": upstream_message or "",
            }
        ]
        if upstream_type or upstream_message
        else None
    )

    match response.status_code:
        case 400:
            return UpstreamBadRequestError(
                upstream_message or "Timbre rejected the request.", details
            )
        case 401:
            return UpstreamAuthError(
                "Timbre rejected the API key. Check the key in backend/.env.", details
            )
        case 403:
            return UpstreamForbiddenError(
                "Timbre refused the request. Check permissions and remaining credits.",
                details,
            )
        case 429:
            return UpstreamRateLimitError(
                "Too many requests. Wait a moment, then try again.", details
            )
        case _:
            return UpstreamError(
                "Timbre is temporarily unavailable. Try again shortly.", details
            )


def _read_error_body(response: requests.Response) -> tuple[str | None, str | None]:
    """Return (upstream issue, upstream message) from either documented shape.

    Observed live on 20 Oct 2026, a 400 is:
        {"success": false, "status_code": 400, "message": "Invalid request: ..."}
    while the Backend Schema originally assumed {"error": {"type", "message"}}.
    Both are accepted so a documentation change cannot silently hide the cause.
    """
    try:
        body = response.json()
    except ValueError:
        return None, None

    if not isinstance(body, dict):
        return None, None

    error = body.get("error")
    if isinstance(error, dict):
        error_type = error.get("type")
        message = error.get("message")
        return (
            error_type if isinstance(error_type, str) else None,
            message if isinstance(message, str) else None,
        )

    upstream_status = body.get("status_code")
    issue = (
        f"HTTP_{upstream_status}"
        if isinstance(upstream_status, (int, str))
        else None
    )
    message = body.get("message")
    return issue, message if isinstance(message, str) else None

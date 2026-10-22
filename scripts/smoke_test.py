"""Milestone 2 - prove Timbre access with the real key.

Standalone on purpose: this file needs only `requests` and `python-dotenv`, so it
runs even if FastAPI is not installed (TRD section 5.1).

Usage (from the project root):
    .venv/Scripts/python.exe scripts/smoke_test.py
    .venv/Scripts/python.exe scripts/smoke_test.py --skip-latency

Exit codes:
    0  at least one model returned audio
    1  no model returned audio (Gate A has not passed)
    2  GNANI_API_KEY is missing
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
AUDIO_DIR = PROJECT_ROOT / "data" / "audio"

AUDIO_CONFIG = {
    "sample_rate": 48000,
    "num_channels": 1,
    "sample_width": 2,
    "encoding": "linear_pcm",
    "container": "wav",
}

SENTENCE = "Timbre speaks Indian languages clearly and naturally."
LONG_TEXT = (
    "Timbre speaks Indian languages clearly and naturally. "
    "The studio keeps the original script untouched while sending the "
    "transformed script to the engine, so the words on screen never change. "
) * 7


def load_api_key() -> str:
    load_dotenv(BACKEND_DIR / ".env")
    key = os.getenv("GNANI_API_KEY", "").strip()
    if not key:
        print("GNANI_API_KEY is not set. Add it to backend/.env and rerun.")
        raise SystemExit(2)
    return key


def call(
    *,
    api_key: str,
    base_url: str,
    text: str,
    model: str,
    voice: str,
    timeout: float = 90.0,
) -> tuple[int, bytes, int, dict | None]:
    url = f"{base_url.rstrip('/')}/api/v1/tts/inference"
    payload = {
        "text": text,
        "model": model,
        "voice": voice,
        "language": "en-IN",
        "speed": 1.0,
        "audio_config": AUDIO_CONFIG,
    }

    started = time.perf_counter()
    try:
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "X-API-Key-ID": api_key,
            },
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, b"", elapsed_ms, {"type": "timeout", "message": "request timed out"}
    except requests.ConnectionError:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return 0, b"", elapsed_ms, {"type": "unreachable", "message": "cannot reach host"}

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code == 200 and response.content:
        return response.status_code, response.content, elapsed_ms, None

    return response.status_code, b"", elapsed_ms, _error_body(response)


def _error_body(response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {"type": f"HTTP_{response.status_code}", "message": response.text[:200]}

    if not isinstance(body, dict):
        return {"type": f"HTTP_{response.status_code}", "message": str(body)[:200]}

    error = body.get("error")
    if isinstance(error, dict):
        return {
            "type": error.get("type", "unknown"),
            "message": error.get("message", ""),
        }

    # Live shape (20 Oct 2026): {success, status_code, message} with no error object.
    return {
        "type": f"HTTP_{body.get('status_code', response.status_code)}",
        "message": body.get("message") or str(body)[:200],
    }


def report(label: str, status: int, audio: bytes, elapsed_ms: int, error: dict | None):
    if audio:
        print(f"  {label}: HTTP {status}, {len(audio):,} bytes, {elapsed_ms} ms, audio OK")
    else:
        print(f"  {label}: HTTP {status}, {elapsed_ms} ms, NO AUDIO")
        print(f"    error.type    = {error and error.get('type')}")
        print(f"    error.message = {error and error.get('message')}")


def save(name: str, audio: bytes) -> Path:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    path = AUDIO_DIR / name
    path.write_bytes(audio)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Timbre live API smoke test")
    parser.add_argument("--skip-latency", action="store_true", help="skip the 800-char probe")
    args = parser.parse_args()

    api_key = load_api_key()
    base_url = os.getenv("GNANI_BASE_URL", "https://api.vachana.ai")
    successes = 0

    print(f"Base URL: {base_url}")
    print("Running Milestone 2 checks (credentials are never printed).\n")

    print("1) timbre-v2.5 / Kaveri")
    status, audio, elapsed, error = call(
        api_key=api_key,
        base_url=base_url,
        text=SENTENCE,
        model="timbre-v2.5",
        voice="Kaveri",
    )
    report("v2.5", status, audio, elapsed, error)
    if audio:
        successes += 1
        print(f"    saved: {save('smoke_v25.wav', audio)}")
        print("    listen: does Kaveri say the sentence intelligibly?")

    print("\n2) timbre-v3.0 / Lakshmi")
    status, audio, elapsed, error = call(
        api_key=api_key,
        base_url=base_url,
        text=SENTENCE,
        model="timbre-v3.0",
        voice="Lakshmi",
    )
    report("v3.0", status, audio, elapsed, error)
    if audio:
        successes += 1
        print(f"    saved: {save('smoke_v30.wav', audio)}")
        print("    listen: is the speech intelligible and natural?")

    print("\n3) Error-path probe (invalid voice, resolves Backend Schema B1)")
    status, _, elapsed, error = call(
        api_key=api_key,
        base_url=base_url,
        text=SENTENCE,
        model="timbre-v3.0",
        voice="ThisVoiceDoesNotExist",
    )
    report("invalid voice", status, b"", elapsed, error)
    print("    confirm the upstream body carried error.type and error.message")

    if not args.skip_latency:
        print(f"\n4) Latency probe ({len(LONG_TEXT)} characters, resolves TQ4)")
        status, audio, elapsed, error = call(
            api_key=api_key,
            base_url=base_url,
            text=LONG_TEXT,
            model="timbre-v3.0",
            voice="Lakshmi",
            timeout=120.0,
        )
        report("long script", status, audio, elapsed, error)
        if audio:
            print(f"    saved: {save('smoke_long.wav', audio)}")

    print("\nSummary")
    print(f"  models returning audio: {successes} of 2")
    print("  check the credit balance in the Gnani dashboard before and after.")
    print("  record status, bytes, elapsed ms and the SSML probe in Implementation Plan section 8.1.")

    return 0 if successes else 1


if __name__ == "__main__":
    sys.exit(main())

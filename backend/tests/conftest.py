from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.gnani_tts import SynthesisOutcome
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="test-key",
        base_url="https://api.test.invalid",
        default_model="timbre-v3.0",
        default_voice="Lakshmi",
        language="en-IN",
        speed=1.0,
        timeout_seconds=1.0,
        script_warn_chars=800,
        script_block_chars=2000,
        data_dir=tmp_path,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def make_wav():
    def _make(seconds: float = 0.1, rate: int = 48000) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(b"\x00\x00" * int(rate * seconds))
        return buffer.getvalue()

    return _make


class FakeTimbre:
    """Stands in for TimbreClient; records calls and never spends credits."""

    def __init__(self, audio: bytes) -> None:
        self.audio = audio
        self.calls: list[dict] = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return SynthesisOutcome(self.audio, 200, 42)


@pytest.fixture
def fake_tts(app, make_wav) -> FakeTimbre:
    fake = FakeTimbre(make_wav())
    app.state.tts = fake
    return fake

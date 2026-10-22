from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.atomic import atomic_write_bytes

logger = logging.getLogger(__name__)

CACHE_KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")
SIDECAR_SCHEMA_VERSION = 1


class AudioCache:
    def __init__(self, audio_dir: Path) -> None:
        self._dir = audio_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, bytes] = {}

    @staticmethod
    def key(
        *,
        text: str,
        model: str,
        voice: str,
        language: str,
        speed: float,
        audio_config: dict[str, Any],
    ) -> str:
        parts = [
            text,
            model,
            voice,
            language,
            repr(float(speed)),
            json.dumps(audio_config, sort_keys=True, separators=(",", ":")),
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    @staticmethod
    def is_valid_key(key: str) -> bool:
        return bool(CACHE_KEY_PATTERN.fullmatch(key))

    def path(self, key: str) -> Path:
        return self._dir / f"{key}.wav"

    def get(self, key: str) -> bytes | None:
        cached = self._memory.get(key)
        if cached is not None:
            return cached

        path = self.path(key)
        if not path.is_file():
            return None

        audio = path.read_bytes()
        self._memory[key] = audio
        return audio

    def store(
        self,
        key: str,
        audio: bytes,
        *,
        text: str,
        settings: dict[str, Any],
        upstream_status: int,
        elapsed_ms: int,
    ) -> None:
        atomic_write_bytes(self.path(key), audio)
        self._memory[key] = audio
        self._write_sidecar(
            key,
            audio,
            text=text,
            settings=settings,
            upstream_status=upstream_status,
            elapsed_ms=elapsed_ms,
        )

    def _write_sidecar(
        self,
        key: str,
        audio: bytes,
        *,
        text: str,
        settings: dict[str, Any],
        upstream_status: int,
        elapsed_ms: int,
    ) -> None:
        sidecar = {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "cache_key": key,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "text": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "char_count": len(text),
            "settings": settings,
            "audio": {
                "file": f"{key}.wav",
                "bytes": len(audio),
                "duration_seconds": _duration_seconds(audio),
            },
            "upstream": {"status": upstream_status, "elapsed_ms": elapsed_ms},
        }
        payload = json.dumps(sidecar, indent=2, ensure_ascii=False).encode("utf-8")

        try:
            atomic_write_bytes(self._dir / f"{key}.json", payload)
        except OSError:
            logger.warning("could not write audio sidecar key=%s", key)


def _duration_seconds(audio: bytes) -> float | None:
    payload = _pcm_payload_size(audio)
    if payload is None:
        return None

    try:
        with wave.open(io.BytesIO(audio), "rb") as handle:
            rate = handle.getframerate()
            frame_size = handle.getnchannels() * handle.getsampwidth()
    except (wave.Error, EOFError):
        return None

    if not rate or not frame_size:
        return None
    return round(payload / (rate * frame_size), 3)


def _pcm_payload_size(audio: bytes) -> int | None:
    """Return the real size of the `data` chunk.

    Timbre returns WAVs whose RIFF and `data` sizes are 0xFFFFFFFF streaming
    placeholders (verified 20 Oct 2026). `wave` then reports 2,147,483,647
    frames, i.e. ~44,739 seconds for every file, so the declared frame count
    must not be trusted. The actual payload length is authoritative.
    """
    if len(audio) < 12 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        return None

    position = 12
    while position + 8 <= len(audio):
        chunk_id = audio[position : position + 4]
        declared = int.from_bytes(audio[position + 4 : position + 8], "little")
        body = position + 8

        if chunk_id == b"data":
            available = len(audio) - body
            if declared in (0, 0xFFFFFFFF) or declared > available:
                return available
            return declared

        position = body + declared + (declared & 1)

    return None

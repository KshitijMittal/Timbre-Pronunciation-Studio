from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.audio_cache import AudioCache
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG

BASE = {
    "text": "Gyaanee speaks.",
    "model": "timbre-v3.0",
    "voice": "Lakshmi",
    "language": "en-IN",
    "speed": 1.0,
    "audio_config": DEFAULT_AUDIO_CONFIG,
}


@pytest.mark.parametrize(
    "field, value",
    [
        ("text", "Gyaanee speaks again."),
        ("model", "timbre-v2.5"),
        ("voice", "Shivani"),
        ("language", "hi-IN"),
        ("speed", 1.1),
        ("audio_config", {**DEFAULT_AUDIO_CONFIG, "sample_rate": 24000}),
    ],
)
def test_each_of_the_six_inputs_changes_the_key(field, value):
    assert AudioCache.key(**BASE) != AudioCache.key(**{**BASE, field: value})


def test_key_is_64_lowercase_hex_characters():
    key = AudioCache.key(**BASE)

    assert len(key) == 64
    assert AudioCache.is_valid_key(key)
    assert not AudioCache.is_valid_key("not-a-key")


def test_audio_is_written_to_disk_and_reloaded(tmp_path: Path, make_wav):
    cache = AudioCache(tmp_path)
    audio = make_wav()
    key = AudioCache.key(**BASE)

    cache.store(
        key,
        audio,
        text=BASE["text"],
        settings={"model": "timbre-v3.0"},
        upstream_status=200,
        elapsed_ms=1234,
    )

    assert (tmp_path / f"{key}.wav").is_file()
    assert AudioCache(tmp_path).get(key) == audio


def test_sidecar_records_provenance(tmp_path: Path, make_wav):
    cache = AudioCache(tmp_path)
    audio = make_wav()
    key = AudioCache.key(**BASE)

    cache.store(
        key,
        audio,
        text=BASE["text"],
        settings={"model": "timbre-v3.0", "voice": "Lakshmi"},
        upstream_status=200,
        elapsed_ms=1234,
    )

    sidecar = json.loads((tmp_path / f"{key}.json").read_text(encoding="utf-8"))
    assert sidecar["text"] == BASE["text"]
    assert sidecar["char_count"] == len(BASE["text"])
    assert sidecar["settings"]["voice"] == "Lakshmi"
    assert sidecar["audio"]["bytes"] == len(audio)
    assert sidecar["audio"]["duration_seconds"] == pytest.approx(0.1, abs=0.01)
    assert sidecar["upstream"] == {"status": 200, "elapsed_ms": 1234}


def test_cache_miss_returns_none(tmp_path: Path):
    assert AudioCache(tmp_path).get("0" * 64) is None


def test_placeholder_chunk_sizes_do_not_break_the_duration(tmp_path: Path, make_wav):
    # Timbre writes 0xFFFFFFFF streaming placeholders for the RIFF and data sizes.
    audio = bytearray(make_wav(0.25))
    audio[4:8] = b"\xff\xff\xff\xff"
    data_index = bytes(audio).find(b"data")
    assert data_index > 0
    audio[data_index + 4 : data_index + 8] = b"\xff\xff\xff\xff"

    cache = AudioCache(tmp_path)
    key = AudioCache.key(**BASE)
    cache.store(
        key,
        bytes(audio),
        text=BASE["text"],
        settings={"model": "timbre-v3.0"},
        upstream_status=200,
        elapsed_ms=1,
    )

    sidecar = json.loads((tmp_path / f"{key}.json").read_text(encoding="utf-8"))
    assert sidecar["audio"]["duration_seconds"] == pytest.approx(0.25, abs=0.01)

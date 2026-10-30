"""Unit tests for the audio panel's pure logic (``App Flow`` §9, task 7c.6-7c.8).

No test here can spend a credit: ``generate_pair`` is driven with a fake client
and a real ``AudioCache`` in a temporary folder. The widget paths (Generate,
the two players, the settings-changed reset) are verified with ``AppTest`` runs
that never click Generate against a real key.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.audio_cache import AudioCache
from app.core.gnani_tts import SynthesisOutcome
from app.core.pronunciation_rules import TransformResult
from app.errors import UpstreamForbiddenError, UpstreamTimeoutError
from ui import audio
from ui.audio import Snapshot

SNAPSHOT = Snapshot(
    model="timbre-v3.0",
    voice="Lakshmi",
    language="en-IN",
    speed=1.0,
)


class FakeClient:
    """Records every synthesise call; fails for texts named in ``failures``."""

    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.failures = failures or {}

    def synthesize(self, **kwargs: object) -> SynthesisOutcome:
        self.calls.append(kwargs)
        text = str(kwargs["text"])
        failure = self.failures.get(text)
        if failure is not None:
            raise failure
        return SynthesisOutcome(audio=f"AUDIO:{text}".encode("utf-8"), status=200, elapsed_ms=7)


def result(original: str, transformed: str) -> TransformResult:
    return TransformResult(
        original_text=original,
        transformed_text=transformed,
        matches=(),
        chained_rule_ids=(),
    )


def settings(block: int = 2000) -> SimpleNamespace:
    return SimpleNamespace(script_block_chars=block)


def test_preflight_blocks_empty_script_and_names_the_reason():
    ready, reason = audio.preflight(settings(), None, "empty")

    assert ready is False
    assert reason == audio.EMPTY_PREVIEW


def test_preflight_blocks_over_limit_with_the_limit_in_the_reason():
    ready, reason = audio.preflight(settings(2000), None, "limit")

    assert ready is False
    assert reason == "Script is over the 2,000 character limit"


def test_preflight_blocks_an_unchanged_transform():
    ready, reason = audio.preflight(settings(), result("Timbre", "Timbre"), None)

    assert ready is False
    assert reason == audio.NO_MATCH


def test_preflight_allows_a_changed_transform():
    ready, reason = audio.preflight(settings(), result("Timbre", "Tim-ber"), None)

    assert ready is True
    assert reason is None


def test_echo_is_the_documented_single_line():
    assert audio.echo(SNAPSHOT) == "timbre-v3.0 · Lakshmi · en-IN · 1.0×"


@pytest.mark.parametrize(
    "speed,expected",
    [(1.0, "1.0×"), (0.85, "0.85×"), (1.15, "1.15×")],
)
def test_echo_keeps_a_real_fraction(speed, expected):
    snapshot = Snapshot("timbre-v3.0", "Lakshmi", "en-IN", speed)

    assert audio.echo(snapshot).endswith(expected)


def test_generate_pair_calls_original_then_transformed_with_frozen_settings(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient()

    outcome = audio.generate_pair(
        cache, client, (" Timbre speaks. ", " Tim-ber speaks. "), SNAPSHOT
    )

    assert outcome.error is None
    assert outcome.failed_step is None
    assert outcome.original == b"AUDIO:Timbre speaks."
    assert outcome.adjusted == b"AUDIO:Tim-ber speaks."
    assert [call["text"] for call in client.calls] == [
        "Timbre speaks.",
        "Tim-ber speaks.",
    ]
    for call in client.calls:
        assert call["model"] == "timbre-v3.0"
        assert call["voice"] == "Lakshmi"
        assert call["language"] == "en-IN"
        assert call["speed"] == 1.0


def test_generate_pair_writes_both_clips_to_the_cache(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient()

    audio.generate_pair(cache, client, ("Timbre", "Tim-ber"), SNAPSHOT)

    for text in ("Timbre", "Tim-ber"):
        key = cache.key(
            text=text,
            model=SNAPSHOT.model,
            voice=SNAPSHOT.voice,
            language=SNAPSHOT.language,
            speed=SNAPSHOT.speed,
            audio_config=audio.DEFAULT_AUDIO_CONFIG,
        )
        assert cache.path(key).is_file()
        assert (tmp_path / f"{key}.json").is_file()


def test_a_second_identical_pair_costs_nothing_and_reuses_the_cache(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient()

    first = audio.generate_pair(cache, client, ("Timbre", "Tim-ber"), SNAPSHOT)
    second = audio.generate_pair(cache, client, ("Timbre", "Tim-ber"), SNAPSHOT)

    assert len(client.calls) == 2  # unchanged by the second pair
    assert second.original == first.original
    assert second.adjusted == first.adjusted


def test_first_failure_aborts_before_the_second_call(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient({"Timbre": UpstreamTimeoutError("timed out")})

    outcome = audio.generate_pair(cache, client, ("Timbre", "Tim-ber"), SNAPSHOT)

    assert outcome.error is not None
    assert outcome.failed_step == "original"
    assert outcome.original is None
    assert outcome.adjusted is None
    assert len(client.calls) == 1


def test_second_failure_keeps_the_original(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient({"Tim-ber": UpstreamForbiddenError("no credits")})

    outcome = audio.generate_pair(cache, client, ("Timbre", "Tim-ber"), SNAPSHOT)

    assert outcome.error is not None
    assert outcome.failed_step == "adjusted"
    assert outcome.original == b"AUDIO:Timbre"
    assert outcome.adjusted is None
    assert len(client.calls) == 2


def test_on_step_reports_original_then_adjusted(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient()
    steps: list[str] = []

    audio.generate_pair(
        cache, client, ("Timbre", "Tim-ber"), SNAPSHOT, on_step=steps.append
    )

    assert steps == ["original", "adjusted"]


def test_on_original_fires_after_the_first_call_and_before_the_second(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient()
    events: list[tuple[str, object, int]] = []

    def on_step(step: str) -> None:
        events.append(("step", step, len(client.calls)))

    def on_original(clip: bytes) -> None:
        events.append(("original", clip, len(client.calls)))

    audio.generate_pair(
        cache,
        client,
        ("Timbre", "Tim-ber"),
        SNAPSHOT,
        on_step=on_step,
        on_original=on_original,
    )

    assert events == [
        ("step", "original", 0),
        ("original", b"AUDIO:Timbre", 1),
        ("step", "adjusted", 1),
    ]


def test_on_original_is_not_called_when_the_first_call_fails(tmp_path):
    cache = AudioCache(tmp_path)
    client = FakeClient({"Timbre": UpstreamTimeoutError("timed out")})
    shown: list[bytes] = []

    audio.generate_pair(
        cache,
        client,
        ("Timbre", "Tim-ber"),
        SNAPSHOT,
        on_original=shown.append,
    )

    assert shown == []

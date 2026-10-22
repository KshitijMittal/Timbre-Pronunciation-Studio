"""Tests for the limit-measurement script (scripts/measure_limits.py).

The script is developer tooling, not shipped app code, but it decides two
documented open questions (TRD TQ4, TQ5) and it sends paid requests, so its
sample construction and its no-spend path are both covered here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "measure_limits.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_limits", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_limits"] = module
    spec.loader.exec_module(module)
    return module


script = load_script()


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Never read the real .env and never write into the real data directory."""
    settings = SimpleNamespace(
        api_key="test-key",
        base_url="https://example.invalid",
        timeout_seconds=1.0,
        data_dir=tmp_path,
    )
    monkeypatch.setattr(script, "load_settings", lambda: settings)
    monkeypatch.setattr(script, "RESULTS_JSON", tmp_path / "limits_results.json")
    return settings


def test_p95_samples_never_exceed_the_nfr_limit():
    """NFR-01 is about 800 characters or fewer, so no sample may exceed it."""
    for rotation in range(script.P95_SAMPLES):
        text = script.build_text(script.P95_TARGET_CHARS, rotation)
        assert 0 < len(text) <= script.P95_TARGET_CHARS


def test_p95_samples_are_distinct():
    """Identical text would be answered from the audio cache.

    A cached sample measures the cache, not the network, which would make the
    p95 meaningless. Distinctness is the whole point of the rotation.
    """
    texts = [
        script.build_text(script.P95_TARGET_CHARS, rotation)
        for rotation in range(script.P95_SAMPLES)
    ]
    assert len(set(texts)) == script.P95_SAMPLES


def test_texts_are_trimmed_and_do_not_end_mid_word():
    text = script.build_text(script.P95_TARGET_CHARS, 1)
    assert text == text.strip()
    assert not text.endswith(" ")


def test_ceiling_probes_straddle_the_app_block_limit():
    probes = {probe["label"]: probe for probe in script.planned_probes()}
    below = probes["ceiling-1900"]
    above = probes["ceiling-2100"]

    assert below["question"] == "TQ5"
    assert len(below["text"]) <= 1900
    assert 1900 - 40 <= len(below["text"]) <= 1900
    assert len(above["text"]) > 2000


def test_dry_run_makes_no_client_and_writes_no_result(monkeypatch, capsys):
    def forbidden_client(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("dry run must not construct a Timbre client")

    monkeypatch.setattr(script, "TimbreClient", forbidden_client)
    monkeypatch.setattr(sys, "argv", ["measure_limits.py", "--dry-run"])

    assert script.main() == 0

    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "paid call" in out
    assert not script.RESULTS_JSON.exists()


def test_probe_flag_limits_the_plan_to_one_label(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["measure_limits.py", "--dry-run", "--probe", "ceiling-2000"],
    )

    assert script.main() == 0

    out = capsys.readouterr().out
    assert "ceiling-2000" in out
    assert "p95-1" not in out


def test_probe_flag_rejects_an_unknown_label(monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["measure_limits.py", "--dry-run", "--probe", "ceiling-9999"]
    )

    assert script.main() == 2
    assert "Unknown probe label" in capsys.readouterr().err


def _planned_with(**fields) -> list[dict[str, Any]]:
    """Every probe from the plan, carrying whatever result fields are given."""
    probes = []
    for probe in script.planned_probes():
        probe = dict(probe)
        probe["char_count"] = len(probe["text"])
        probe.update(fields)
        probes.append(probe)
    return probes


def _write_earlier(report: dict) -> None:
    script.RESULTS_JSON.write_text(json.dumps(report), encoding="utf-8")


def test_partial_run_keeps_earlier_probe_results():
    """A --probe run must not erase the timings a previous full run measured."""
    earlier = {
        "settings": script.SETTINGS,
        "probes": [
            {
                "question": "TQ4",
                "label": "p95-1",
                "elapsed_ms": 6905,
                "error": "",
                "status": 200,
                "char_count": 798,
            }
        ],
    }
    _write_earlier(earlier)

    this_run = [
        probe
        for probe in script.planned_probes()
        if probe["label"] == "ceiling-2000"
    ]
    merged = script.merge_with_earlier(this_run, script.SETTINGS)

    labels = [probe["label"] for probe in merged]
    assert "p95-1" in labels
    assert "ceiling-2000" in labels
    assert labels.index("p95-1") < labels.index("ceiling-2000")


def test_cached_rerun_keeps_the_timings_already_on_file():
    """A free rerun must not blank the measurements the docs cite."""
    measured = _planned_with(status=200, elapsed_ms=6905, bytes=1000, error="")
    _write_earlier(script.summarise(measured, script.SETTINGS, 0))

    cached = _planned_with(status="cached", elapsed_ms=None, bytes=None, error="")
    report = script.summarise(
        script.merge_with_earlier(cached, script.SETTINGS), script.SETTINGS, 0
    )

    assert report["tq4"]["median_ms"] == 6905
    assert report["tq4"]["p95_ms"] == 6905
    assert report["tq4"]["within_target"] is True
    assert all(probe["elapsed_ms"] == 6905 for probe in report["probes"])


def test_merge_drops_records_made_under_other_settings():
    earlier = script.summarise(
        _planned_with(status=200, elapsed_ms=1, bytes=1, error=""),
        {**script.SETTINGS, "voice": "Amritha"},
        0,
    )
    _write_earlier(earlier)

    this_run = [
        probe
        for probe in _planned_with(status=200, elapsed_ms=9197, bytes=1, error="")
        if probe["label"] == "ceiling-2000"
    ]
    merged = script.merge_with_earlier(this_run, script.SETTINGS)

    assert [probe["label"] for probe in merged] == ["ceiling-2000"]


def test_merge_drops_labels_the_plan_no_longer_contains():
    _write_earlier(
        {
            "settings": script.SETTINGS,
            "probes": [
                {
                    "question": "TQ5",
                    "label": "ceiling-2500",
                    "char_count": 2500,
                    "status": 200,
                    "elapsed_ms": 1,
                    "error": "",
                }
            ],
        }
    )

    this_run = [
        probe
        for probe in _planned_with(status=200, elapsed_ms=9197, bytes=1, error="")
        if probe["label"] == "ceiling-2000"
    ]
    labels = [
        probe["label"] for probe in script.merge_with_earlier(this_run, script.SETTINGS)
    ]

    assert "ceiling-2500" not in labels


def test_char_counts_line_up_with_the_timings():
    """Cached samples have no timing, so they must not shift the printed pairs."""
    probes = []
    for probe in _planned_with():
        if probe["question"] != "TQ4":
            continue
        if probe["label"] in {"p95-1", "p95-2", "p95-3"}:
            probe.update(status="cached", elapsed_ms=None, bytes=None, error="")
        else:
            probe.update(status=200, elapsed_ms=9000, bytes=1, error="")
        probes.append(probe)

    report = script.summarise(probes, script.SETTINGS, 0)

    expected = [probe["char_count"] for probe in probes if probe["elapsed_ms"]]
    assert report["tq4"]["char_counts"] == expected
    assert len(report["tq4"]["elapsed_ms"]) == len(report["tq4"]["char_counts"]) == 2


def test_a_failed_cache_write_does_not_lose_a_paid_measurement(monkeypatch, tmp_path):
    class FakeCache:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def key(**kwargs):
            return "0" * 64

        def get(self, key):
            return None

        def store(self, *args, **kwargs):
            raise OSError("disk full")

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def synthesize(self, **kwargs):
            return SimpleNamespace(audio=b"RIFF0000WAVEdata", status=200, elapsed_ms=42)

    monkeypatch.setattr(script, "AudioCache", FakeCache)
    monkeypatch.setattr(script, "TimbreClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["measure_limits.py", "--confirm-spend"])

    assert script.main() == 0

    report = json.loads(script.RESULTS_JSON.read_text(encoding="utf-8"))
    assert report["tq4"]["median_ms"] == 42
    assert [probe["status"] for probe in report["tq5"]["probes"]] == [200, 200, 200]


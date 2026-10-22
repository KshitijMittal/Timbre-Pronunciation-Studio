"""Tests for the Gate B retry script (scripts/try_respelling.py).

The script is developer tooling, not shipped app code, but it holds the
POC's credit-saving logic and the listening-sheet generator, so both are
covered here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "try_respelling.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("try_respelling", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["try_respelling"] = module
    spec.loader.exec_module(module)
    return module


script = load_script()


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch):
    """A TimbreClient stand-in that counts calls and never spends credits."""

    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def synthesize(self, *, text, model, voice, language, speed, audio_config):
            self.calls.append(text)
            return type(
                "Outcome",
                (),
                {"status": 200, "audio": b"RIFF-fake-audio", "elapsed_ms": 7},
            )()

    client = FakeClient()
    monkeypatch.setattr(script, "build_client", lambda: client)
    return client


@pytest.fixture(autouse=True)
def isolated_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point the script at a temporary data directory."""
    audio_dir = tmp_path / "audio"
    monkeypatch.setattr(script, "AUDIO_DIR", audio_dir)
    monkeypatch.setattr(script, "TRY_DIR", audio_dir / "try")
    monkeypatch.setattr(script, "RESULTS_JSON", tmp_path / "try_results.json")
    monkeypatch.setattr(script, "POC_RESULTS_JSON", tmp_path / "poc_results.json")
    monkeypatch.setattr(script, "SHEET_HTML", audio_dir / "try" / "listen.html")
    return tmp_path


def test_parse_respellings_keeps_repeat_terms():
    pairs = script.parse_respellings(["Zentara=Zen Taara", "Zentara=Zan Taara"])
    assert pairs == [("Zentara", "Zen Taara"), ("Zentara", "Zan Taara")]


def test_parse_respellings_rejects_malformed_value():
    with pytest.raises(SystemExit):
        script.parse_respellings(["ZentaraZen Taara"])


def test_transform_uses_the_real_rule_engine():
    assert (
        script.transform("We shipped Zentara today.", "Zentara", "Zen Taara")
        == "We shipped Zen Taara today."
    )
    # Whole-word only: "Zentara" inside "Zentarax" must not match.
    assert (
        script.transform("Zentarax shipped today.", "Zentara", "Zen Taara")
        == "Zentarax shipped today."
    )


def test_same_respelling_is_generated_once(fake_client):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)

    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )

    entry = manifest["terms"]["Zentara"]
    assert len(entry["attempts"]) == 1
    assert entry["attempts"][0]["respelling"] == "Zen Taara"
    # One call for the original, one for the adjusted - never two for the
    # same respelling.
    assert len(fake_client.calls) == 2


def test_two_respellings_for_one_term_keep_separate_files(fake_client):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)

    script.cmd_adjusted(
        manifest,
        fake_client,
        settings,
        [("Zentara", "Zen Taara"), ("Zentara", "Zan Taara")],
        False,
        None,
    )

    attempts = manifest["terms"]["Zentara"]["attempts"]
    assert len(attempts) == 2
    files = {attempt["file"] for attempt in attempts}
    assert len(files) == 2, "each respelling must keep its own file"


def test_verdict_is_recorded_and_survives_a_rerun(fake_client):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)

    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )
    script.cmd_verdict(manifest, ["Zentara=closer|good"])
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )

    entry = manifest["terms"]["Zentara"]
    assert entry["verdict"] == "closer"
    assert entry["attempts"][0]["verdict"] == "closer"


def test_originals_are_reused_from_the_round_one_run(fake_client):
    """A round-1 original with the same sentence and settings costs nothing."""
    audio_dir = script.AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    poc_audio = audio_dir / "poc_01_zentara_original.wav"
    poc_audio.write_bytes(b"RIFF-round-one")

    settings = dict(script.SETTINGS)
    poc_payload = {
        "settings": settings,
        "terms": [
            {
                "sentence": script.TERMS[0]["sentence"],
                "original_file": poc_audio.name,
            }
        ],
    }
    script.POC_RESULTS_JSON.write_text(json.dumps(poc_payload), encoding="utf-8")

    manifest = script.load_manifest()
    reused = script.seed_from_poc(manifest, settings)

    assert reused == 1
    entry = manifest["terms"]["Zentara"]
    assert entry["original"]["reused_from"] == poc_audio.name
    assert (audio_dir / entry["original"]["file"]).read_bytes() == b"RIFF-round-one"


def test_originals_are_not_reused_when_settings_differ(fake_client):
    audio_dir = script.AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    poc_audio = audio_dir / "poc_01_zentara_original.wav"
    poc_audio.write_bytes(b"RIFF-round-one")

    other = dict(script.SETTINGS)
    other["voice"] = "Kaveri"
    poc_payload = {
        "settings": other,
        "terms": [
            {
                "sentence": script.TERMS[0]["sentence"],
                "original_file": poc_audio.name,
            }
        ],
    }
    script.POC_RESULTS_JSON.write_text(json.dumps(poc_payload), encoding="utf-8")

    manifest = script.load_manifest()
    assert script.seed_from_poc(manifest, dict(script.SETTINGS)) == 0


def test_sheet_only_references_files_that_exist(fake_client):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )
    script.cmd_sheet(manifest)

    html = script.SHEET_HTML.read_text(encoding="utf-8")
    import re

    sources = re.findall(r'src="([^"]+)"', html)
    assert sources, "the sheet must contain at least one player"
    for source in sources:
        assert (script.SHEET_HTML.parent / source).is_file()


def test_sheet_omits_missing_audio(fake_client):
    manifest = script.load_manifest()
    script.cmd_sheet(manifest)

    html = script.SHEET_HTML.read_text(encoding="utf-8")
    import re

    sources = re.findall(r'src="([^"]+)"', html)
    assert sources == []
    assert "not generated" in html


def test_interactive_skips_terms_that_already_have_a_verdict(
    fake_client, monkeypatch
):
    """Stopping midway and resuming must not redo the finished terms."""
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    script.cmd_verdict(manifest, ["Zentara=closer"])

    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    script.cmd_interactive(manifest, fake_client, settings)

    # Zentara was skipped, so no adjusted audio was generated for it.
    attempts = manifest["terms"]["Zentara"]["attempts"]
    assert attempts == []
    assert manifest["terms"]["Zentara"]["verdict"] == "closer"


def test_sheet_shows_the_respelling_and_how_to_record_a_verdict(fake_client):
    """The sheet is the judgement surface, so it must carry what is needed."""
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )
    script.cmd_sheet(manifest)

    html = script.SHEET_HTML.read_text(encoding="utf-8")
    assert "Zen Taara" in html, "the respelling being judged must be visible"
    assert "verdict" in html.lower(), "the sheet must say how to record a verdict"
    assert "placeholder" in html, "the header quirk must be explained"


def test_interactive_records_the_respelling_and_leaves_the_verdict_open(
    fake_client, monkeypatch
):
    """Judging happens in the browser, so the loop records the respelling only."""
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)

    answers = iter(["Zen Taara", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    script.cmd_interactive(manifest, fake_client, settings)

    entry = manifest["terms"]["Zentara"]
    assert entry["attempts"][0]["respelling"] == "Zen Taara"
    assert entry["attempts"][0]["file"]
    assert entry["attempts"][0]["verdict"] == "pending"
    assert entry["verdict"] == "pending"


def test_interactive_never_launches_an_external_player(fake_client, monkeypatch):
    """The loop must not hand audio to a media player - the sheet is the surface."""
    import os
    import subprocess

    def explode(*_args, **_kwargs):
        raise AssertionError("the script must not launch an external player")

    monkeypatch.setattr(os, "startfile", explode, raising=False)
    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(subprocess, "Popen", explode)

    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    answers = iter(["Zen Taara", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    script.cmd_interactive(manifest, fake_client, settings)

    assert manifest["terms"]["Zentara"]["attempts"]


def test_interactive_writes_a_sheet_whose_files_exist(fake_client, monkeypatch):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    answers = iter(["Zen Taara", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    script.cmd_interactive(manifest, fake_client, settings)

    html = script.SHEET_HTML.read_text(encoding="utf-8")
    import re

    sources = re.findall(r'src="([^"]+)"', html)
    assert sources, "the sheet must contain at least one player"
    for source in sources:
        assert (script.SHEET_HTML.parent / source).is_file()


def test_dry_run_never_rewrites_a_generated_record(fake_client):
    """A free run must not stamp dry_run/None over audio that was really generated."""
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )

    # Same command, but as a dry run against a fresh read of the manifest.
    script.cmd_adjusted(
        script.load_manifest(), None, settings, [("Zentara", "Zen Taara")], False, None
    )

    entry = script.load_manifest()["terms"]["Zentara"]
    assert entry["original"]["status"] == 200
    assert "dry_run" not in entry["original"]
    attempt = entry["attempts"][0]
    assert attempt["status"] == 200
    assert "dry_run" not in attempt
    assert attempt["bytes"] == len(b"RIFF-fake-audio")


def test_credit_guard_aborts_when_nothing_can_answer(monkeypatch, capsys):
    """A pipe or an agent gets EOF, and EOF must mean zero credits spent."""

    def no_stdin(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_stdin)

    with pytest.raises(SystemExit) as exc:
        script.confirm_credit_spend(8)

    assert "No credits were spent" in str(exc.value)
    assert "up to 8 paid Timbre call(s)" in capsys.readouterr().out


def test_credit_guard_does_not_ask_when_nothing_would_be_paid(monkeypatch):
    def must_not_prompt(_prompt: str) -> str:
        raise AssertionError("a free run must not ask for confirmation")

    monkeypatch.setattr("builtins.input", must_not_prompt)
    script.confirm_credit_spend(0)


def test_credit_guard_requires_the_word_spend(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
    with pytest.raises(SystemExit):
        script.confirm_credit_spend(8)

    monkeypatch.setattr("builtins.input", lambda _prompt: " SPEND ")
    script.confirm_credit_spend(8)  # returns without raising


def test_main_stops_before_any_call_without_confirmation(fake_client, monkeypatch):
    monkeypatch.setattr(script, "build_client", lambda: fake_client)
    monkeypatch.setattr(sys, "argv", ["try_respelling.py", "original"])

    def no_stdin(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_stdin)

    with pytest.raises(SystemExit):
        script.main()

    assert fake_client.calls == [], "the guard must run before the first paid call"


def test_main_runs_when_spend_is_confirmed_in_advance(fake_client, monkeypatch):
    monkeypatch.setattr(script, "build_client", lambda: fake_client)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "try_respelling.py",
            "--confirm-spend",
            "adjusted",
            "--respelling",
            "Zentara=Zen Taara",
        ],
    )

    assert script.main() == 0
    assert len(fake_client.calls) == 2  # one original, one adjusted


def test_estimate_counts_only_uncached_calls(fake_client):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )

    estimate, _ = script.estimate_calls(
        manifest, settings, "adjusted", [("Zentara", "Zen Taara")], False, None
    )
    assert estimate == 0, "already-generated audio must not be paid for again"

    estimate, _ = script.estimate_calls(
        manifest, settings, "adjusted", [("Zentara", "Zan Taara")], False, None
    )
    assert estimate == 1


def test_verdict_rejects_an_unknown_verdict(fake_client):
    """A typo must not become gate evidence."""
    manifest = script.load_manifest()

    with pytest.raises(SystemExit):
        script.cmd_verdict(manifest, ["Zentara=closr"])

    # Rejected before anything was written.
    assert "Zentara" not in manifest["terms"]


def test_verdict_refreshes_the_sheet(fake_client):
    manifest = script.load_manifest()
    settings = dict(script.SETTINGS)
    script.cmd_adjusted(
        manifest, fake_client, settings, [("Zentara", "Zen Taara")], False, None
    )

    script.cmd_verdict(manifest, ["Zentara=closer|good"])

    html = script.SHEET_HTML.read_text(encoding="utf-8")
    assert "closer" in html

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, load_settings
from app.errors import ConfigurationError


def _clear_env(monkeypatch, names):
    for name in names:
        monkeypatch.delenv(name, raising=False)


ENV_VARS = (
    "GNANI_API_KEY",
    "GNANI_BASE_URL",
    "GNANI_DEFAULT_MODEL",
    "GNANI_DEFAULT_VOICE",
    "GNANI_LANGUAGE",
    "GNANI_SPEED",
    "GNANI_TIMEOUT_SECONDS",
    "SCRIPT_WARN_CHARS",
    "SCRIPT_BLOCK_CHARS",
    "DATA_DIR",
)


def test_missing_key_raises_at_startup(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch, ENV_VARS)

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(tmp_path / "missing.env")
    assert (
        excinfo.value.message
        == "GNANI_API_KEY is not set. Add it to backend/.env and restart."
    )


def test_block_limit_must_exceed_warning_limit(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch, ENV_VARS)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("SCRIPT_WARN_CHARS", "2000")
    monkeypatch.setenv("SCRIPT_BLOCK_CHARS", "2000")

    with pytest.raises(ConfigurationError, match="greater than"):
        load_settings(tmp_path / "missing.env")


@pytest.mark.parametrize("speed", ["0.84", "1.16"])
def test_speed_must_stay_inside_the_api_range(monkeypatch, tmp_path: Path, speed):
    _clear_env(monkeypatch, ENV_VARS)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("GNANI_SPEED", speed)

    with pytest.raises(ConfigurationError, match="between 0.85 and 1.15"):
        load_settings(tmp_path / "missing.env")


@pytest.mark.parametrize("timeout", ["0", "-1"])
def test_timeout_must_be_positive(monkeypatch, tmp_path: Path, timeout):
    _clear_env(monkeypatch, ENV_VARS)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("GNANI_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ConfigurationError, match="greater than zero"):
        load_settings(tmp_path / "missing.env")


def test_defaults_are_applied(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch, ENV_VARS)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")

    settings = load_settings(tmp_path / "missing.env")

    assert settings.base_url == "https://api.vachana.ai"
    assert settings.default_model == "timbre-v3.0"
    assert settings.default_voice == "Lakshmi"
    assert settings.language == "en-IN"
    assert settings.speed == 1.0
    assert settings.timeout_seconds == 60.0
    assert settings.script_warn_chars == 800
    assert settings.script_block_chars == 2000
    assert settings.data_dir == PROJECT_ROOT / "data"


def test_relative_data_dir_resolves_under_the_project_root(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch, ENV_VARS)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("DATA_DIR", "local-data")

    settings = load_settings(tmp_path / "missing.env")

    assert settings.data_dir == (PROJECT_ROOT / "local-data").resolve()


def test_bad_numeric_values_are_reported(monkeypatch, tmp_path: Path):
    _clear_env(monkeypatch, ENV_VARS)
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("SCRIPT_WARN_CHARS", "not-a-number")

    with pytest.raises(ConfigurationError, match="SCRIPT_WARN_CHARS must be an integer"):
        load_settings(tmp_path / "missing.env")

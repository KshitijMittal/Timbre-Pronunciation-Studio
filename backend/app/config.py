from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.errors import ConfigurationError

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"

# The only speed range the Timbre API contract accepts (Backend Schema §10.4).
MIN_SPEED = 0.85
MAX_SPEED = 1.15


@dataclass(frozen=True, slots=True)
class Settings:
    api_key: str
    base_url: str
    default_model: str
    default_voice: str
    language: str
    speed: float
    timeout_seconds: float
    script_warn_chars: int
    script_block_chars: int
    data_dir: Path


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or BACKEND_DIR / ".env")

    api_key = os.getenv("GNANI_API_KEY", "").strip()
    if not api_key:
        raise ConfigurationError(
            "GNANI_API_KEY is not set. Add it to backend/.env and restart."
        )

    warn_chars = _read_int("SCRIPT_WARN_CHARS", 800)
    block_chars = _read_int("SCRIPT_BLOCK_CHARS", 2000)
    if block_chars <= warn_chars:
        raise ConfigurationError(
            "SCRIPT_BLOCK_CHARS must be greater than SCRIPT_WARN_CHARS."
        )

    speed = _read_float("GNANI_SPEED", 1.0)
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ConfigurationError(
            f"GNANI_SPEED must be between {MIN_SPEED} and {MAX_SPEED}."
        )

    timeout = _read_float("GNANI_TIMEOUT_SECONDS", 60.0)
    if timeout <= 0:
        raise ConfigurationError("GNANI_TIMEOUT_SECONDS must be greater than zero.")

    return Settings(
        api_key=api_key,
        base_url=os.getenv("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/"),
        default_model=os.getenv("GNANI_DEFAULT_MODEL", "timbre-v3.0"),
        default_voice=os.getenv("GNANI_DEFAULT_VOICE", "Lakshmi"),
        language=os.getenv("GNANI_LANGUAGE", "en-IN"),
        speed=speed,
        timeout_seconds=timeout,
        script_warn_chars=warn_chars,
        script_block_chars=block_chars,
        data_dir=_read_data_dir(),
    )


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc


def _read_data_dir() -> Path:
    raw = os.getenv("DATA_DIR", "").strip()
    if not raw:
        return DEFAULT_DATA_DIR
    path = Path(raw)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

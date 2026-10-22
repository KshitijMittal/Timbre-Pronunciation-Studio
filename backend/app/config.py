from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.errors import ConfigurationError

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


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
    cors_origins: tuple[str, ...]


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

    return Settings(
        api_key=api_key,
        base_url=os.getenv("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/"),
        default_model=os.getenv("GNANI_DEFAULT_MODEL", "timbre-v3.0"),
        default_voice=os.getenv("GNANI_DEFAULT_VOICE", "Lakshmi"),
        language=os.getenv("GNANI_LANGUAGE", "en-IN"),
        speed=_read_float("GNANI_SPEED", 1.0),
        timeout_seconds=_read_float("GNANI_TIMEOUT_SECONDS", 60.0),
        script_warn_chars=warn_chars,
        script_block_chars=block_chars,
        data_dir=_read_data_dir(),
        cors_origins=_read_cors_origins(),
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


def _read_cors_origins() -> tuple[str, ...]:
    raw = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.catalogue import find_model
from app.config import Settings
from app.core.audio_cache import AudioCache
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG, TimbreClient
from app.deps import get_cache, get_settings, get_tts
from app.errors import InternalError, LimitExceeded, ValidationError
from app.models.schemas import SettingsEcho, SynthesizeRequest, SynthesizeResponse

router = APIRouter(tags=["synthesize"])

MIN_SPEED = 0.85
MAX_SPEED = 1.15


@router.post("/synthesize", response_model=SynthesizeResponse)
def synthesize(
    payload: SynthesizeRequest,
    settings: Settings = Depends(get_settings),
    cache: AudioCache = Depends(get_cache),
    tts: TimbreClient = Depends(get_tts),
) -> SynthesizeResponse:
    text = payload.text.strip()
    if not text:
        raise ValidationError("Script cannot be empty.")

    if len(text) > settings.script_block_chars:
        raise LimitExceeded(
            f"Script is {len(text):,} characters. "
            f"The limit is {settings.script_block_chars:,}."
        )

    model = find_model(payload.model)
    if model is None:
        raise ValidationError(f'Model "{payload.model}" is not available.')

    if model.voice(payload.voice) is None:
        raise ValidationError(
            f'Voice "{payload.voice}" is not available for model "{model.id}".'
        )

    language = payload.language or settings.language
    if language != settings.language:
        raise ValidationError(
            f"Only English ({settings.language}) is supported in this release."
        )

    speed = settings.speed if payload.speed is None else payload.speed
    if not MIN_SPEED <= speed <= MAX_SPEED:
        raise ValidationError(
            f"Speed must be between {MIN_SPEED} and {MAX_SPEED}."
        )

    cache_key = cache.key(
        text=text,
        model=model.id,
        voice=payload.voice,
        language=language,
        speed=speed,
        audio_config=DEFAULT_AUDIO_CONFIG,
    )

    echo = SettingsEcho(
        model=model.id,
        voice=payload.voice,
        language=language,
        speed=speed,
        sample_rate=DEFAULT_AUDIO_CONFIG["sample_rate"],
        num_channels=DEFAULT_AUDIO_CONFIG["num_channels"],
        sample_width=DEFAULT_AUDIO_CONFIG["sample_width"],
        container=DEFAULT_AUDIO_CONFIG["container"],
    )

    cached_audio = cache.get(cache_key)
    if cached_audio is not None:
        return _response(cache_key, echo, cached_audio, cached=True)

    outcome = tts.synthesize(
        text=text,
        model=model.id,
        voice=payload.voice,
        language=language,
        speed=speed,
        audio_config=DEFAULT_AUDIO_CONFIG,
    )

    try:
        cache.store(
            cache_key,
            outcome.audio,
            text=text,
            settings=echo.model_dump(),
            upstream_status=outcome.status,
            elapsed_ms=outcome.elapsed_ms,
        )
    except OSError as exc:
        raise InternalError(
            "Could not save the generated audio. Check that the data folder is writable."
        ) from exc

    return _response(cache_key, echo, outcome.audio, cached=False)


def _response(
    cache_key: str, echo: SettingsEcho, audio: bytes, *, cached: bool
) -> SynthesizeResponse:
    return SynthesizeResponse(
        cache_key=cache_key,
        audio_url=f"/api/audio/{cache_key}.wav",
        cached=cached,
        bytes=len(audio),
        settings=echo,
    )

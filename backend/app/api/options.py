from __future__ import annotations

from fastapi import APIRouter, Depends

from app.catalogue import MODELS
from app.config import Settings
from app.core.gnani_tts import DEFAULT_AUDIO_CONFIG
from app.deps import get_settings
from app.models.schemas import LimitsOut, ModelOut, OptionsResponse, VoiceOut

router = APIRouter(tags=["options"])


@router.get("/options", response_model=OptionsResponse)
def options(settings: Settings = Depends(get_settings)) -> OptionsResponse:
    return OptionsResponse(
        models=[
            ModelOut(
                id=model.id,
                label=model.label,
                default_voice=model.default_voice,
                voices=[
                    VoiceOut(id=voice.id, gender=voice.gender, persona=voice.persona)
                    for voice in model.voices
                ],
            )
            for model in MODELS
        ],
        language=settings.language,
        speed=settings.speed,
        limits=LimitsOut(
            warn_at=settings.script_warn_chars, block_at=settings.script_block_chars
        ),
        audio_config=dict(DEFAULT_AUDIO_CONFIG),
    )

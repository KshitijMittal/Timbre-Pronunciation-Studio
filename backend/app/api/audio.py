from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.audio_cache import AudioCache
from app.deps import get_cache
from app.errors import NotFound

router = APIRouter(tags=["audio"])


@router.get("/audio/{cache_key}")
def get_audio(cache_key: str, cache: AudioCache = Depends(get_cache)) -> FileResponse:
    # The documented audio_url carries a .wav suffix; the key itself is 64 hex chars.
    key = cache_key[: -len(".wav")] if cache_key.endswith(".wav") else cache_key

    if not AudioCache.is_valid_key(key):
        raise NotFound("Audio not found.")

    path = cache.path(key)
    if not path.is_file():
        raise NotFound("Audio not found.")

    return FileResponse(
        path,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=3600",
        },
    )

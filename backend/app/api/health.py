from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.catalogue import MODELS
from app.config import Settings
from app.deps import get_settings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        key_configured=bool(settings.api_key),
        version=__version__,
        models_available=[model.id for model in MODELS],
    )

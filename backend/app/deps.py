from __future__ import annotations

from fastapi import Request

from app.config import Settings
from app.core.audio_cache import AudioCache
from app.core.dictionary_store import DictionaryStore
from app.core.gnani_tts import TimbreClient


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(request: Request) -> DictionaryStore:
    return request.app.state.store


def get_cache(request: Request) -> AudioCache:
    return request.app.state.cache


def get_tts(request: Request) -> TimbreClient:
    return request.app.state.tts

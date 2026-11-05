from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DICTIONARY_ID_PATTERN = (
    r"^dict_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
MAX_NAME_LENGTH = 80
MAX_SOURCE_LENGTH = 120
MAX_REPLACEMENT_LENGTH = 200
MAX_RULES = 200


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule(StrictModel):
    id: str
    source: str = Field(min_length=1, max_length=MAX_SOURCE_LENGTH)
    replacement: str = Field(min_length=1, max_length=MAX_REPLACEMENT_LENGTH)
    type: Literal["alias"] = "alias"
    created_at: str
    updated_at: str


class Dictionary(StrictModel):
    schema_version: int = 1
    id: str
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    created_at: str
    updated_at: str
    rules: list[Rule] = Field(default_factory=list)


class DictionaryCreate(StrictModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)


class DictionaryUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)


class RuleCreate(StrictModel):
    source: str = Field(min_length=1, max_length=MAX_SOURCE_LENGTH)
    replacement: str = Field(min_length=1, max_length=MAX_REPLACEMENT_LENGTH)
    type: str = "alias"


class RuleUpdate(StrictModel):
    source: str | None = Field(default=None, min_length=1, max_length=MAX_SOURCE_LENGTH)
    replacement: str | None = Field(
        default=None, min_length=1, max_length=MAX_REPLACEMENT_LENGTH
    )
    type: str | None = None


class InlineRule(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = Field(min_length=1, max_length=MAX_SOURCE_LENGTH)
    replacement: str = Field(min_length=1, max_length=MAX_REPLACEMENT_LENGTH)
    id: str | None = None
    created_at: str | None = None


class TransformRequest(StrictModel):
    text: str = ""
    dictionary_id: str | None = None
    rules: list[InlineRule] | None = None


class RuleMatchOut(BaseModel):
    rule_id: str
    source: str
    replacement: str
    count: int


class WarningOut(BaseModel):
    code: str
    rule_id: str | None = None
    message: str


class LimitOut(BaseModel):
    warn_at: int
    block_at: int
    status: str


class TransformResponse(BaseModel):
    original_text: str
    transformed_text: str
    changed: bool
    char_count: int
    limit: LimitOut
    matches: list[RuleMatchOut]
    warnings: list[WarningOut]


class SettingsEcho(BaseModel):
    model: str
    voice: str
    language: str
    speed: float
    sample_rate: int
    num_channels: int
    sample_width: int
    container: str


class SynthesizeRequest(StrictModel):
    text: str = Field(min_length=1)
    model: str
    voice: str
    language: str | None = None
    speed: float | None = None


class SynthesizeResponse(BaseModel):
    cache_key: str
    audio_url: str
    cached: bool
    bytes: int
    settings: SettingsEcho


class HealthResponse(BaseModel):
    status: str
    key_configured: bool
    version: str
    models_available: list[str]


class VoiceOut(BaseModel):
    id: str
    gender: str
    persona: str


class ModelOut(BaseModel):
    id: str
    label: str
    default_voice: str
    voices: list[VoiceOut]


class LimitsOut(BaseModel):
    warn_at: int
    block_at: int


class OptionsResponse(BaseModel):
    models: list[ModelOut]
    language: str
    speed: float
    limits: LimitsOut
    audio_config: dict[str, Any]


class DictionarySummary(BaseModel):
    id: str
    name: str
    rule_count: int
    created_at: str
    updated_at: str


class StoreWarningOut(BaseModel):
    file: str
    reason: str


class DictionaryListResponse(BaseModel):
    dictionaries: list[DictionarySummary]
    warnings: list[StoreWarningOut] = Field(default_factory=list)


class RuleListResponse(BaseModel):
    rules: list[Rule]

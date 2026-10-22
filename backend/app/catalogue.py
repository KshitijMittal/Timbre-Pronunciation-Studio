from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    id: str
    gender: str
    persona: str


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    label: str
    default_voice: str
    voices: tuple[VoiceInfo, ...]

    def voice(self, voice_id: str) -> VoiceInfo | None:
        return next((v for v in self.voices if v.id == voice_id), None)


MODELS: tuple[ModelInfo, ...] = (
    ModelInfo(
        id="timbre-v3.0",
        label="Timbre v3.0",
        default_voice="Lakshmi",
        voices=(
            VoiceInfo("Lakshmi", "female", "Expressive, energetic"),
            VoiceInfo("Shivani", "female", "Warm, empathetic"),
            VoiceInfo("Kalpana", "female", "Warm, empathetic"),
            VoiceInfo("Chetana", "female", "Warm, empathetic"),
            VoiceInfo("Vasudha", "female", "Expressive, energetic"),
            VoiceInfo("Riyaa", "female", "Confident, authoritative"),
            VoiceInfo("Tarika", "female", "Warm, empathetic"),
            VoiceInfo("Avinash", "male", "Professional"),
            VoiceInfo("Shubham", "male", "Expressive, energetic"),
            VoiceInfo("Prakash", "male", "Professional"),
            VoiceInfo("Devansh", "male", "Conversational"),
            VoiceInfo("Yashraj", "male", "Warm, empathetic"),
            VoiceInfo("Harshad", "male", "Professional"),
        ),
    ),
    ModelInfo(
        id="timbre-v2.5",
        label="Timbre v2.5",
        default_voice="Kaveri",
        voices=(
            VoiceInfo("Kaveri", "female", "Professional"),
            VoiceInfo("Trupti", "female", "Professional"),
            VoiceInfo("Devika", "female", "Professional"),
            VoiceInfo("Pranav", "male", "Friendly"),
            VoiceInfo("Shlok", "male", "Conversational"),
            VoiceInfo("Girish", "male", "Expressive, energetic"),
        ),
    ),
)


def find_model(model_id: str) -> ModelInfo | None:
    return next((model for model in MODELS if model.id == model_id), None)

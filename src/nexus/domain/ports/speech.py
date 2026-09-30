"""
Speech I/O ports (Phase 3, multi-modal).

Transcription (audio -> text) feeds the conscious loop's input; synthesis
(text -> audio) renders its responses. Adapters live in infrastructure and are
swapped here without touching the application layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SpeechToText(ABC):
    """Transcribes spoken audio into text."""

    @abstractmethod
    async def transcribe(self, audio: bytes, mime_type: str = "audio/mpeg") -> str: ...


class TextToSpeech(ABC):
    """Synthesizes audio from text."""

    @abstractmethod
    async def synthesize(self, text: str, voice: str = "alloy") -> bytes: ...

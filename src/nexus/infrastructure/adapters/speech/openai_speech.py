"""OpenAI speech adapters - Whisper transcription + TTS synthesis."""

from __future__ import annotations

from nexus.domain.exceptions import LLMUnavailableError
from nexus.domain.ports.speech import SpeechToText, TextToSpeech


class OpenAISpeechToText(SpeechToText):
    """Transcribes audio via OpenAI Whisper."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(self, audio: bytes, mime_type: str = "audio/mpeg") -> str:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            transcript = await client.audio.transcriptions.create(
                model=self._model,
                file=("input", audio, mime_type),
            )
            return transcript.text or ""
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc


class OpenAITextToSpeech(TextToSpeech):
    """Synthesizes speech via OpenAI TTS."""

    def __init__(self, api_key: str, model: str = "tts-1", default_voice: str = "alloy") -> None:
        self._api_key = api_key
        self._model = model
        self._default_voice = default_voice

    async def synthesize(self, text: str, voice: str = "alloy") -> bytes:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self._api_key)
            response = await client.audio.speech.create(
                model=self._model,
                voice=voice or self._default_voice,
                input=text,
            )
            return await response.aread()
        except Exception as exc:
            raise LLMUnavailableError(str(exc)) from exc

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from backend.core.config import get_settings
from backend.services.utils import (
    call_with_backoff,
    get_job_directory,
    maybe_sleep_for_rate_limit,
)


settings = get_settings()


class TranscriberService:
    def transcribe(self, *, job_id: str, audio_path: str | Path) -> dict[str, Any]:
        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Transcription cannot continue."
            )

        audio_file_path = Path(audio_path)
        subtitles_path = get_job_directory(job_id) / "dynamic_subs.ass"

        headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

        def _request() -> requests.Response:
            with audio_file_path.open("rb") as audio_file:
                files = {
                    "file": (
                        audio_file_path.name,
                        audio_file,
                        "application/octet-stream",
                    )
                }
                data = {
                    "model": settings.groq_whisper_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                }
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300,
                )
                response.raise_for_status()
                maybe_sleep_for_rate_limit(dict(response.headers))
                return response

        response = call_with_backoff(_request)
        payload = response.json()
        words = self._extract_words(payload)
        subtitles_path.write_text(self._build_ass_document(words), encoding="utf-8")
        return {
            "subtitle_path": str(subtitles_path),
            "transcript": payload,
            "words": words,
        }

    def _extract_words(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        words = payload.get("words") or []
        if words:
            return words

        segments = payload.get("segments") or []
        synthesized_words: list[dict[str, Any]] = []
        for segment in segments:
            text = str(segment.get("text", "")).strip()
            if not text:
                continue
            tokens = text.split()
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", start + max(len(tokens) * 0.25, 0.5)))
            step = max((end - start) / max(len(tokens), 1), 0.1)
            for index, token in enumerate(tokens):
                word_start = start + (step * index)
                word_end = min(word_start + step, end)
                synthesized_words.append(
                    {"word": token, "start": word_start, "end": word_end}
                )
        return synthesized_words

    def _build_ass_document(self, words: list[dict[str, Any]]) -> str:
        events = self._group_words(words)
        header = """[Script Info]
Title: Dynamic Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Caption,Montserrat,30,&H00FFFFFF,&H00FFFFFF,&H00181818,&H96000000,-1,0,0,0,100,100,0.4,0,1,2.2,2.8,2,60,60,150,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
        body = "\n".join(
            f"Dialogue: 0,{self._to_ass_time(event['start'])},{self._to_ass_time(event['end'])},Caption,,0,0,0,,{event['text']}"
            for event in events
        )
        return f"{header}{body}\n"

    def _group_words(self, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        chunk: list[str] = []
        start_time: float | None = None
        end_time: float | None = None

        for word in words:
            if start_time is None:
                start_time = float(word.get("start", 0.0))
            end_time = float(word.get("end", start_time + 0.4))
            chunk.append(str(word.get("word", "")).strip())
            if len(chunk) >= 3 or (end_time - start_time) >= 1.8:
                events.append(
                    {
                        "start": start_time,
                        "end": end_time,
                        "text": self._escape_ass_text(" ".join(chunk).upper()),
                    }
                )
                chunk = []
                start_time = None
                end_time = None

        if chunk and start_time is not None and end_time is not None:
            events.append(
                {
                    "start": start_time,
                    "end": end_time,
                    "text": self._escape_ass_text(" ".join(chunk).upper()),
                }
            )

        return events

    @staticmethod
    def _escape_ass_text(text: str) -> str:
        return text.replace("\n", r"\N").replace("{", "(").replace("}", ")")

    @staticmethod
    def _to_ass_time(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centiseconds = int(round((seconds - int(seconds)) * 100))
        return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from backend.core.config import get_settings
from backend.services.local_transcriber import LocalWhisperService
from backend.services.sarvam_transcriber import SarvamSTTService
from backend.services.subtitles import write_transcript_artifacts
from backend.services.utils import (
    call_with_backoff,
    ffprobe_duration,
    get_job_directory,
    maybe_sleep_for_rate_limit,
)

logger = logging.getLogger(__name__)


class GroqWhisperService:
    """Cloud Whisper service via Groq API (whisper-large-v3-turbo)."""

    def __init__(self, api_key: str | None = None) -> None:
        self.settings = get_settings()
        self.api_key = api_key or self.settings.groq_api_key

    def acquire_audio(self, *, job_id: str, video_url: str) -> Path:
        return LocalWhisperService().acquire_audio(job_id=job_id, video_url=video_url)

    def transcribe(
        self,
        *,
        job_id: str,
        audio_path: Path,
        language_code: str = "unknown",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        import requests

        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured. Cloud Groq transcription cannot continue."
            )

        job_dir = get_job_directory(job_id)
        if progress_callback:
            progress_callback(30, "Sending audio to Groq Whisper Cloud...")

        headers = {"Authorization": f"Bearer {self.api_key}"}

        def _request() -> requests.Response:
            with audio_path.open("rb") as audio_file:
                files = {
                    "file": (audio_path.name, audio_file, "application/octet-stream")
                }
                data: dict[str, Any] = {
                    "model": self.settings.groq_whisper_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                }
                if language_code and language_code != "unknown":
                    data["language"] = language_code.split("-")[0]

                resp = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300,
                )
                resp.raise_for_status()
                maybe_sleep_for_rate_limit(dict(resp.headers))
                return resp

        response = call_with_backoff(_request)
        payload = response.json()

        segments: list[dict[str, Any]] = []
        raw_segments = payload.get("segments") or []
        for s in raw_segments:
            segments.append(
                {
                    "start": round(float(s.get("start", 0.0)), 3),
                    "end": round(float(s.get("end", 0.0)), 3),
                    "text": str(s.get("text", "")).strip(),
                }
            )

        full_text = payload.get("text", "").strip() or "\n".join(
            s["text"] for s in segments
        )
        detected_lang = payload.get("language") or language_code

        artifact_paths = write_transcript_artifacts(
            job_dir=job_dir,
            transcript_text=full_text,
            segments=segments,
            metadata={
                "engine": "groq",
                "model": self.settings.groq_whisper_model,
                "language": detected_lang,
            },
        )

        return {
            "language": detected_lang,
            "segments": segments,
            "transcript_text": full_text,
            "artifact_paths": artifact_paths,
        }


class TranscriptionManager:
    """
    Unified manager routing transcription requests to the selected engine with
    automatic cascading fallback when an engine fails (e.g. rate limits, network, quotas).
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    def acquire_audio(self, *, engine_name: str, job_id: str, video_url: str) -> Path:
        if engine_name == "sarvam":
            try:
                return SarvamSTTService().acquire_audio(job_id=job_id, video_url=video_url)
            except Exception as e:
                logger.warning(
                    f"Sarvam audio acquire failed for job {job_id} ({e}), falling back to standard audio acquire."
                )
        # Both local_whisper and groq use MP3
        return LocalWhisperService().acquire_audio(job_id=job_id, video_url=video_url)

    def _get_engine_order(self, preferred_engine: str) -> list[str]:
        """Builds an ordered list of engines to try with preferred engine first."""
        preferred = (preferred_engine or "local_whisper").lower().strip()
        available: list[str] = []

        if preferred == "sarvam":
            available = ["sarvam"]
            if self.settings.groq_api_key:
                available.append("groq")
            available.append("local_whisper")
        elif preferred == "groq":
            available = ["groq"]
            available.append("local_whisper")
            if self.settings.sarvam_api_key:
                available.append("sarvam")
        else:
            available = ["local_whisper"]
            if self.settings.groq_api_key:
                available.append("groq")
            if self.settings.sarvam_api_key:
                available.append("sarvam")

        # Guarantee local_whisper is always present as ultimate failsafe
        if "local_whisper" not in available:
            available.append("local_whisper")

        return available

    def transcribe(
        self,
        *,
        engine_name: str,
        job_id: str,
        audio_path: Path,
        language_code: str = "unknown",
        mode: str = "transcribe",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        engine_chain = self._get_engine_order(engine_name)
        errors: list[str] = []

        for idx, current_engine in enumerate(engine_chain):
            try:
                if idx > 0 and progress_callback:
                    last_err = errors[-1] if errors else "Error"
                    short_err = last_err.split(":")[-1].strip()[:60]
                    progress_callback(
                        25,
                        f"Previous engine failed ({short_err}). Falling back to {current_engine.upper()}...",
                    )
                logger.info(
                    f"[Job {job_id}] Attempting transcription with engine: {current_engine} (attempt {idx + 1}/{len(engine_chain)})"
                )

                if current_engine == "sarvam":
                    service = SarvamSTTService()
                    res = service.transcribe(
                        job_id=job_id,
                        audio_path=audio_path,
                        language_code=language_code,
                        mode=mode,
                        progress_callback=progress_callback,
                    )
                    res["engine"] = "sarvam"
                    return res

                elif current_engine == "groq":
                    groq_service = GroqWhisperService()
                    res = groq_service.transcribe(
                        job_id=job_id,
                        audio_path=audio_path,
                        language_code=language_code,
                        progress_callback=progress_callback,
                    )
                    res["engine"] = "groq"
                    return res

                else:
                    whisper_service = LocalWhisperService()
                    res = whisper_service.transcribe(
                        job_id=job_id,
                        audio_path=audio_path,
                        language_code=language_code,
                        progress_callback=progress_callback,
                    )
                    res["engine"] = "local_whisper"
                    return res

            except Exception as exc:
                err_msg = f"{current_engine} error: {exc}"
                logger.warning(f"[Job {job_id}] {err_msg}")
                errors.append(err_msg)

        # If all engines in chain failed
        raise RuntimeError(
            f"All transcription engines failed. Attempts: {'; '.join(errors)}"
        )

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
    """Cloud Whisper service via Groq API (whisper-large-v3-turbo) with multi-key pool rotation."""

    def __init__(self, api_keys: list[str] | None = None) -> None:
        self.settings = get_settings()
        self.api_keys = api_keys or self.settings.get_groq_api_keys()

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

        if not self.api_keys:
            raise RuntimeError(
                "No GROQ_API_KEYS configured. Cloud Groq transcription cannot continue."
            )

        job_dir = get_job_directory(job_id)
        if progress_callback:
            progress_callback(30, "Sending audio to Groq Whisper Cloud...")

        # Groq has a 25 MB file limit. If audio exceeds 24MB, compress to 48k mono MP3
        upload_path = audio_path
        if audio_path.is_file() and audio_path.stat().st_size > 24 * 1024 * 1024:
            compressed_path = job_dir / "compressed_groq_source.mp3"
            if not compressed_path.is_file():
                import subprocess

                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(audio_path),
                        "-ac",
                        "1",
                        "-b:a",
                        "48k",
                        str(compressed_path),
                    ],
                    capture_output=True,
                    check=False,
                )
            if (
                compressed_path.is_file()
                and compressed_path.stat().st_size <= 25 * 1024 * 1024
            ):
                upload_path = compressed_path

        errors: list[str] = []
        for key_idx, key in enumerate(self.api_keys):
            headers = {"Authorization": f"Bearer {key}"}
            masked_key = f"{key[:4]}...{key[-4:]}"

            def _request() -> requests.Response:
                import mimetypes

                mime_type = mimetypes.guess_type(str(upload_path))[0] or "audio/mpeg"
                with upload_path.open("rb") as audio_file:
                    files = {
                        "file": (
                            upload_path.name,
                            audio_file,
                            mime_type,
                        )
                    }
                    data: dict[str, Any] = {
                        "model": self.settings.groq_whisper_model,
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": "word",
                    }
                    if language_code and language_code != "unknown":
                        clean_lang = language_code.split("-")[0].lower().strip()
                        if clean_lang:
                            data["language"] = clean_lang

                    resp = requests.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                        timeout=300,
                    )
                    if not resp.ok:
                        err_detail = resp.text[:400]
                        logger.warning(
                            f"Groq API HTTP {resp.status_code} on key {masked_key}: {err_detail}"
                        )
                        raise requests.HTTPError(
                            f"{resp.status_code} Client Error from Groq: {err_detail}",
                            response=resp,
                        )
                    maybe_sleep_for_rate_limit(dict(resp.headers))
                    return resp

            try:
                if key_idx > 0 and progress_callback:
                    progress_callback(
                        30, f"Groq key rotated to key #{key_idx + 1} ({masked_key})..."
                    )
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
            except Exception as e:
                err_msg = f"Key #{key_idx + 1} ({masked_key}) failed: {e}"
                logger.warning(f"[Job {job_id}] Groq {err_msg}")
                errors.append(err_msg)

        raise RuntimeError(
            f"All {len(self.api_keys)} Groq API keys exhausted: {'; '.join(errors)}"
        )


class TranscriptionManager:
    """
    Unified manager routing transcription requests to the selected engine with
    automatic fallback to Local GPU Whisper when cloud engines or keys are exhausted.
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
        # Default MP3 acquisition
        return LocalWhisperService().acquire_audio(job_id=job_id, video_url=video_url)

    def _get_engine_order(self, preferred_engine: str) -> list[str]:
        """Builds fallback chain. Falls back to local_whisper (Sarvam excluded from fallback)."""
        preferred = (preferred_engine or "local_whisper").lower().strip()

        if preferred == "groq":
            # Try Groq (rotates through all configured Groq keys), then fallback directly to Local Whisper
            return ["groq", "local_whisper"]
        elif preferred == "sarvam":
            # If user explicitly chose Sarvam, try Sarvam first, then fallback to Local Whisper
            return ["sarvam", "local_whisper"]
        else:
            # Local Whisper is primary
            return ["local_whisper"]

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

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from backend.core.config import get_settings
from backend.services.subtitles import write_transcript_artifacts
from backend.services.utils import ffprobe_duration, get_job_directory

# Process-level model cache to avoid reloading weights into GPU VRAM on every Celery task
_CACHED_WHISPER_MODEL: Any = None
_CACHED_MODEL_KEY: str | None = None


class LocalWhisperService:
    """Downloads authorised source audio and performs local GPU/CPU transcription using faster-whisper."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def acquire_audio(self, *, job_id: str, video_url: str) -> Path:
        job_dir = get_job_directory(job_id)
        output_template = str(job_dir / "source.%(ext)s")
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-progress",
            "--restrict-filenames",
            "--extractor-args",
            "youtube:player_client=android,web",
            "--no-check-certificates",
            "--geo-bypass",
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--output",
            output_template,
            video_url,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=1800, check=False
        )
        audio_path = job_dir / "source.mp3"
        if not audio_path.is_file():
            mp3_files = list(job_dir.glob("source*.mp3"))
            if mp3_files:
                audio_path = mp3_files[0]
            else:
                message = (
                    result.stderr or result.stdout or "yt-dlp did not create an audio file."
                ).strip()
                raise RuntimeError(f"Audio acquisition failed: {message[-900:]}")

        # Validate that the downloaded audio is not a corrupt/empty stub
        min_valid_size = 10_000  # 10 KB minimum for valid audio
        actual_size = audio_path.stat().st_size
        if actual_size < min_valid_size:
            audio_path.unlink(missing_ok=True)
            stderr_hint = (result.stderr or "")[-500:].strip()
            raise RuntimeError(
                f"Audio acquisition produced a corrupt file ({actual_size} bytes). "
                f"The video may be unavailable, age-restricted, or region-locked. "
                f"yt-dlp stderr: {stderr_hint or 'no output'}"
            )
        return audio_path

    def _get_or_create_model(self) -> Any:
        global _CACHED_WHISPER_MODEL, _CACHED_MODEL_KEY
        from faster_whisper import WhisperModel

        model_name = self.settings.whisper_model or "deepdml/faster-whisper-large-v3-turbo-ct2"
        compute_type = self.settings.whisper_compute_type or "int8_float16"
        device = self.settings.whisper_device if self.settings.whisper_device != "auto" else "cuda"

        # Prefer pre-cached local disk directory if available
        local_dir = Path("/root/.cache/whisper_models/faster-whisper-large-v3-turbo-ct2")
        if local_dir.is_dir() and (local_dir / "model.bin").is_file() and (local_dir / "model.bin").stat().st_size > 100_000_000:
            model_name = str(local_dir)

        model_key = f"{model_name}:{device}:{compute_type}"
        if _CACHED_WHISPER_MODEL is not None and _CACHED_MODEL_KEY == model_key:
            return _CACHED_WHISPER_MODEL

        try:
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                cpu_threads=4,
                num_workers=2,
            )
        except Exception:
            # Fallback to int8 on CPU if CUDA is unavailable
            model = WhisperModel(
                model_name,
                device="cpu",
                compute_type="int8",
                cpu_threads=4,
                num_workers=2,
            )

        _CACHED_WHISPER_MODEL = model
        _CACHED_MODEL_KEY = model_key
        return model

    def transcribe(
        self,
        *,
        job_id: str,
        audio_path: Path,
        language_code: str = "unknown",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        job_dir = get_job_directory(job_id)
        model = self._get_or_create_model()

        try:
            total_duration = ffprobe_duration(audio_path)
        except Exception:
            total_duration = 0.0

        lang_param = None if (not language_code or language_code == "unknown") else language_code

        segments_source, info = model.transcribe(
            str(audio_path),
            language=lang_param,
            beam_size=5,
            best_of=5,
            temperature=[0.0, 0.2, 0.4],
            condition_on_previous_text=False,  # CRITICAL: stops repetition hallucination on long horizon
            vad_filter=True,                   # CRITICAL: cuts silence loops
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=400,
            ),
            word_timestamps=True,
        )

        segments: list[dict[str, Any]] = []
        for segment in segments_source:
            seg_start = round(float(segment.start), 3)
            seg_end = round(float(segment.end), 3)
            seg_text = str(segment.text).strip()

            words_data = [
                {
                    "start": round(float(word.start), 3),
                    "end": round(float(word.end), 3),
                    "word": str(word.word),
                }
                for word in (segment.words or [])
            ]
            segments.append(
                {
                    "start": seg_start,
                    "end": seg_end,
                    "text": seg_text,
                    "words": words_data,
                }
            )

            if total_duration > 0 and progress_callback:
                pct = min(88, int(20 + (65 * (seg_end / total_duration))))
                progress_callback(pct, f"Transcribing with Faster-Whisper ({int(seg_end)}s / {int(total_duration)}s)")

        transcript_text = "\n".join(seg["text"] for seg in segments if seg["text"]).strip()
        detected_lang = str(info.language or "unknown")

        artifact_paths = write_transcript_artifacts(
            job_dir=job_dir,
            transcript_text=transcript_text,
            segments=segments,
            metadata={
                "engine": "local_whisper",
                "model": self.settings.whisper_model,
                "language": detected_lang,
                "duration_seconds": total_duration,
            },
        )

        return {
            "language": detected_lang,
            "segments": segments,
            "transcript_text": transcript_text,
            "artifact_paths": artifact_paths,
        }

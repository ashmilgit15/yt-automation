from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.services.utils import get_job_directory


class LocalWhisperService:
    """Downloads authorised source audio and writes portable transcript exports."""

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
            "--extract-audio",
            "--audio-format",
            "mp3",
            "--output",
            output_template,
            video_url,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800, check=False)
        audio_path = job_dir / "source.mp3"
        if result.returncode != 0 or not audio_path.is_file():
            message = (result.stderr or result.stdout or "yt-dlp did not create an audio file.").strip()
            raise RuntimeError(f"Audio acquisition failed: {message[-900:]}")
        return audio_path

    def transcribe(self, *, job_id: str, audio_path: Path) -> dict[str, Any]:
        from faster_whisper import WhisperModel

        model = self._load_model(WhisperModel)
        segments_source, info = model.transcribe(
            str(audio_path),
            vad_filter=True,
            beam_size=5,
            word_timestamps=True,
        )
        segments: list[dict[str, Any]] = []
        for segment in segments_source:
            segments.append(
                {
                    "start": round(float(segment.start), 3),
                    "end": round(float(segment.end), 3),
                    "text": str(segment.text).strip(),
                    "words": [
                        {"start": round(float(word.start), 3), "end": round(float(word.end), 3), "word": str(word.word)}
                        for word in (segment.words or [])
                    ],
                }
            )
        transcript_text = "\n".join(segment["text"] for segment in segments if segment["text"])
        paths = self._write_exports(job_id=job_id, transcript_text=transcript_text, segments=segments)
        return {"language": str(info.language or "unknown"), "segments": segments, "transcript_text": transcript_text, "artifact_paths": paths}

    def _load_model(self, whisper_model: Any) -> Any:
        if self.settings.whisper_device != "auto":
            return whisper_model(
                self.settings.whisper_model,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )
        try:
            return whisper_model(self.settings.whisper_model, device="cuda", compute_type=self.settings.whisper_compute_type)
        except Exception:
            return whisper_model(self.settings.whisper_model, device="cpu", compute_type="int8")

    def _write_exports(self, *, job_id: str, transcript_text: str, segments: list[dict[str, Any]]) -> dict[str, str]:
        job_dir = get_job_directory(job_id)
        paths = {
            "txt": job_dir / "transcript.txt",
            "srt": job_dir / "transcript.srt",
            "vtt": job_dir / "transcript.vtt",
            "json": job_dir / "transcript.json",
        }
        paths["txt"].write_text(transcript_text + "\n", encoding="utf-8")
        paths["srt"].write_text(self._subtitle_text(segments, "srt"), encoding="utf-8")
        paths["vtt"].write_text(self._subtitle_text(segments, "vtt"), encoding="utf-8")
        paths["json"].write_text(json.dumps({"text": transcript_text, "segments": segments}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {name: str(path) for name, path in paths.items()}

    @classmethod
    def _subtitle_text(cls, segments: list[dict[str, Any]], format_name: str) -> str:
        chunks = ["WEBVTT\n"] if format_name == "vtt" else []
        separator = "." if format_name == "vtt" else ","
        for index, segment in enumerate(segments, start=1):
            if format_name == "srt":
                chunks.append(str(index))
            chunks.append(f"{cls._timestamp(float(segment['start']), separator)} --> {cls._timestamp(float(segment['end']), separator)}")
            chunks.append(str(segment["text"]))
            chunks.append("")
        return "\n".join(chunks)

    @staticmethod
    def _timestamp(value: float, millisecond_separator: str) -> str:
        milliseconds = round((value - int(value)) * 1000)
        total = int(value)
        hours, remaining = divmod(total, 3600)
        minutes, seconds = divmod(remaining, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}{millisecond_separator}{milliseconds:03d}"

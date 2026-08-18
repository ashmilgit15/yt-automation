from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import requests

from backend.core.config import get_settings
from backend.services.subtitles import write_transcript_artifacts
from backend.services.utils import (
    call_with_backoff,
    ffprobe_duration,
    get_job_directory,
    maybe_sleep_for_rate_limit,
)

SARVAM_ENDPOINT = "https://api.sarvam.ai/speech-to-text"
CHUNK_DURATION_SECONDS = 25.0


class SarvamSTTService:
    """
    Speech-to-Text service using Sarvam AI's saaras:v3 model.
    Handles Indic languages, auto-detection, translation to English,
    and automatic audio chunking for long-form YouTube videos.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.settings = get_settings()
        self.api_key = api_key or self.settings.sarvam_api_key

    def _ensure_api_key(self) -> str:
        if not self.api_key or not self.api_key.strip():
            raise RuntimeError(
                "SARVAM_API_KEY is not configured in .env. Please provide a valid Sarvam AI API subscription key."
            )
        return self.api_key.strip()

    def acquire_audio(self, *, job_id: str, video_url: str) -> Path:
        """Downloads YouTube audio as 16kHz mono WAV for optimal STT accuracy."""
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
            "wav",
            "--postprocessor-args",
            "ExtractAudio:-ac 1 -ar 16000",
            "--output",
            output_template,
            video_url,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=1800, check=False
        )
        audio_path = job_dir / "source.wav"
        if not audio_path.is_file():
            # Fallback check if yt-dlp named it slightly differently
            wav_files = list(job_dir.glob("source*.wav"))
            if wav_files:
                audio_path = wav_files[0]
            else:
                message = (
                    result.stderr or result.stdout or "yt-dlp failed to acquire audio."
                ).strip()
                raise RuntimeError(f"Audio acquisition failed: {message[-800:]}")
        return audio_path

    def _slice_audio(
        self, source_path: Path, output_path: Path, start_sec: float, duration_sec: float
    ) -> None:
        """Slices an audio chunk using ffmpeg."""
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-t",
            f"{duration_sec:.3f}",
            "-i",
            str(source_path),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

    def _transcribe_single_clip(
        self,
        audio_path: Path,
        language_code: str,
        mode: str,
        time_offset: float = 0.0,
    ) -> dict[str, Any]:
        """Transcribes a single audio clip (<= 30s) via Sarvam REST API."""
        api_key = self._ensure_api_key()
        headers = {"api-subscription-key": api_key}

        def _do_post() -> requests.Response:
            with audio_path.open("rb") as f:
                files = {
                    "file": (audio_path.name, f, "audio/wav"),
                }
                data = {
                    "model": self.settings.sarvam_model or "saaras:v3",
                    "language_code": language_code or "unknown",
                    "mode": mode or "transcribe",
                    "with_timestamps": "true",
                }
                resp = requests.post(
                    SARVAM_ENDPOINT,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=60,
                )
                resp.raise_for_status()
                maybe_sleep_for_rate_limit(dict(resp.headers))
                return resp

        resp = call_with_backoff(_do_post, retries=6, initial_delay=2.0)
        payload = resp.json()

        transcript = str(payload.get("transcript", "")).strip()
        detected_lang = payload.get("language_code") or language_code

        # Extract timestamped segments
        segments: list[dict[str, Any]] = []
        timestamps = payload.get("timestamps") or {}
        words = timestamps.get("words") or []
        start_times = timestamps.get("start_time_seconds") or []
        end_times = timestamps.get("end_time_seconds") or []

        if words and len(words) == len(start_times) == len(end_times):
            for w, s, e in zip(words, start_times, end_times):
                seg_text = str(w).strip()
                if not seg_text:
                    continue
                segments.append(
                    {
                        "start": round(float(s) + time_offset, 3),
                        "end": round(float(e) + time_offset, 3),
                        "text": seg_text,
                    }
                )
        elif transcript:
            segments.append(
                {
                    "start": round(time_offset, 3),
                    "end": round(time_offset + (len(transcript.split()) * 0.4), 3),
                    "text": transcript,
                }
            )

        return {
            "transcript": transcript,
            "segments": segments,
            "language": detected_lang,
        }

    def transcribe(
        self,
        *,
        audio_path: str | Path,
        language_code: str = "unknown",
        mode: str = "transcribe",
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        """
        Transcribe an audio file using Sarvam AI STT API.
        For audio files longer than 30 seconds, automatically splits into chunks
        and joins the resulting transcripts and offset segments.
        """
        audio_path = Path(audio_path).resolve()
        if not audio_path.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        job_dir = audio_path.parent

        total_duration = self._get_audio_duration(audio_path)
        chunks_dir = audio_path.parent / "sarvam_chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        all_transcripts: list[str] = []
        all_segments: list[dict[str, Any]] = []
        detected_languages: list[str] = []

        if total_duration <= CHUNK_DURATION_SECONDS:
            if progress_callback:
                progress_callback(20, "Transcribing single audio file with Sarvam AI...")
            result = self._transcribe_single_clip(
                audio_path, language_code, mode, time_offset=0.0
            )
            if result["transcript"]:
                all_transcripts.append(result["transcript"])
            all_segments.extend(result["segments"])
            detected_languages.append(result["language"])
        else:
            # Long audio: slice into chunks
            chunk_infos: list[tuple[int, float, float, Path]] = []
            current_time = 0.0
            chunk_idx = 0
            while current_time < total_duration:
                dur = min(CHUNK_DURATION_SECONDS, total_duration - current_time)
                chunk_file = chunks_dir / f"chunk_{chunk_idx:04d}.wav"
                self._slice_audio(audio_path, chunk_file, current_time, dur)
                chunk_infos.append((chunk_idx, current_time, dur, chunk_file))
                current_time += dur
                chunk_idx += 1

            total_chunks = len(chunk_infos)
            if progress_callback:
                progress_callback(20, f"Split into {total_chunks} chunks. Transcribing with Sarvam AI...")

            results_by_index: dict[int, dict[str, Any]] = {}
            completed_count = 0

            # Process chunks with rate-limiting resilience (max 2 workers)
            max_workers = min(2, total_chunks)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {}
                for idx, start_time, _, chunk_path in chunk_infos:
                    f = executor.submit(
                        self._transcribe_single_clip,
                        chunk_path,
                        language_code,
                        mode,
                        start_time,
                    )
                    future_map[f] = idx
                    time.sleep(0.2)

                for future in as_completed(future_map):
                    idx = future_map[future]
                    res = future.result()
                    results_by_index[idx] = res
                    completed_count += 1

                    # Update progress between 20% and 85%
                    pct = int(20 + (65 * (completed_count / total_chunks)))
                    if progress_callback:
                        progress_callback(
                            pct,
                            f"Transcribed chunk {completed_count}/{total_chunks} with Sarvam AI",
                        )

            # Assemble results in chronological order
            for idx in range(total_chunks):
                chunk_res = results_by_index[idx]
                if chunk_res["transcript"]:
                    all_transcripts.append(chunk_res["transcript"])
                all_segments.extend(chunk_res["segments"])
                if chunk_res.get("language"):
                    detected_languages.append(chunk_res["language"])

        # Cleanup temporary chunk files to conserve disk space
        try:
            for f in chunks_dir.glob("*.wav"):
                f.unlink(missing_ok=True)
            chunks_dir.rmdir()
        except Exception:
            pass

        full_transcript_text = "\n".join(all_transcripts).strip()
        final_language = (
            max(set(detected_languages), key=detected_languages.count)
            if detected_languages
            else language_code
        )

        artifact_paths = write_transcript_artifacts(
            job_dir=job_dir,
            transcript_text=full_transcript_text,
            segments=all_segments,
            metadata={
                "engine": "sarvam",
                "model": self.settings.sarvam_model,
                "language": final_language,
                "mode": mode,
                "duration_seconds": total_duration,
            },
        )

        return {
            "language": final_language,
            "transcript_text": full_transcript_text,
            "segments": all_segments,
            "artifact_paths": artifact_paths,
        }

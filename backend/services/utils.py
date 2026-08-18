import json
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Callable, TypeVar

import requests

from backend.core.config import get_settings


settings = get_settings()
RetryCallable = TypeVar("RetryCallable", bound=Callable[[], Any])


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_job_directory(job_id: str) -> Path:
    return ensure_directory(settings.local_artifacts_root / job_id)


def write_json_file(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def stacktrace_from_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def maybe_sleep_for_rate_limit(headers: dict[str, Any]) -> None:
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after:
        try:
            time.sleep(max(float(retry_after), 0.0))
            return
        except ValueError:
            pass

    remaining_candidates = [
        headers.get("x-ratelimit-remaining"),
        headers.get("x-ratelimit-remaining-requests"),
        headers.get("x-ratelimit-remaining-tokens"),
    ]
    remaining = next(
        (value for value in remaining_candidates if value is not None), None
    )
    if remaining is not None:
        try:
            if int(float(remaining)) <= 0:
                time.sleep(2.0)
        except ValueError:
            return


import random


def call_with_backoff(
    operation: RetryCallable,
    *,
    retries: int = 5,
    initial_delay: float = 1.5,
    retriable_statuses: set[int] | None = None,
) -> Any:
    retriable = retriable_statuses or {408, 409, 425, 429, 500, 502, 503, 504}
    delay = initial_delay

    for attempt in range(1, retries + 1):
        try:
            result = operation()
            if isinstance(result, requests.Response):
                maybe_sleep_for_rate_limit(dict(result.headers))
            return result
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in retriable or attempt == retries:
                raise
            if status_code == 429:
                delay = max(delay, 2.5) * 1.5 + random.uniform(0.2, 0.8)
            if exc.response is not None:
                maybe_sleep_for_rate_limit(dict(exc.response.headers))
        except requests.RequestException:
            if attempt == retries:
                raise
        except Exception as exc:
            exc_str = str(exc).lower()
            if (
                "429" in exc_str
                or "quota" in exc_str
                or "resourceexhausted" in exc_str
                or "toomanyrequests" in exc_str
            ):
                if attempt == retries:
                    raise
                delay = max(delay, 16.0)
            else:
                if attempt == retries:
                    raise

        time.sleep(delay)
        delay = delay * 1.8 + random.uniform(0.1, 0.5)

    raise RuntimeError("Backoff loop exited unexpectedly")


def run_command(
    command: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
    )


def ffprobe_duration(media_path: Path) -> float:
    try:
        probe = run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ]
        )
        val = probe.stdout.strip()
        return float(val) if val else 0.0
    except Exception:
        return 0.0


def verify_audio_file(audio_path: Path, min_size: int = 10_000, min_duration: float = 0.5) -> tuple[bool, str]:
    """
    Validates that a downloaded audio file is physically intact, non-empty,
    contains a recognizable audio stream, and has non-zero duration.
    Returns (is_valid, error_reason).
    """
    if not audio_path.is_file():
        return False, "File does not exist on disk."

    size = audio_path.stat().st_size
    if size < min_size:
        return False, f"File size ({size} bytes) is below the minimum threshold ({min_size} bytes)."

    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name:format=duration",
                "-of",
                "json",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if probe.returncode != 0:
            return False, f"ffprobe failed to parse audio file (corrupt stream): {probe.stderr.strip()[:200]}"

        data = json.loads(probe.stdout)
        streams = data.get("streams", [])
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            return False, "No valid audio stream detected in downloaded media container."

        duration_val = (data.get("format") or {}).get("duration")
        if duration_val is not None:
            try:
                dur = float(duration_val)
                if dur < min_duration:
                    return False, f"Audio duration ({dur:.2f}s) is below required minimum ({min_duration}s)."
            except ValueError:
                pass

        return True, ""
    except Exception as e:
        return False, f"Audio validation error: {e}"


def extract_json_payload(raw_text: str) -> Any:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in model response: {raw_text}")
    return json.loads(cleaned[start : end + 1])

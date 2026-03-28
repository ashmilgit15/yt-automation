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


def call_with_backoff(
    operation: RetryCallable,
    *,
    retries: int = 4,
    initial_delay: float = 1.0,
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
                # Force a larger delay for rate limit hits if needed, Gemini often needs 15s
                delay = max(delay, 16.0)
            else:
                if attempt == retries:
                    raise

        time.sleep(delay)
        delay *= 2

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
    return float(probe.stdout.strip())


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

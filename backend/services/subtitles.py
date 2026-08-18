from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def format_timestamp(seconds_value: float | Any, separator: str = ",") -> str:
    """
    Format a floating-point seconds value into HH:MM:SS,mmm or HH:MM:SS.mmm.
    Guarantees millisecond is always 3 digits (000-999) with proper hour/minute roll-over.
    """
    try:
        seconds_value = float(seconds_value)
    except (ValueError, TypeError, OverflowError):
        seconds_value = 0.0

    if seconds_value < 0 or seconds_value != seconds_value or math.isinf(seconds_value):
        seconds_value = 0.0

    try:
        total_milliseconds = int(round(seconds_value * 1000))
    except (ValueError, TypeError, OverflowError):
        total_milliseconds = 0

    milliseconds = total_milliseconds % 1000
    total_seconds = total_milliseconds // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"


def build_srt(segments: list[dict[str, Any]]) -> str:
    """Generate RFC/SubRip compliant SRT subtitles."""
    lines: list[str] = []
    sub_idx = 1
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        start_val = segment.get("start")
        try:
            start_num = float(start_val) if start_val is not None else 0.0
            if start_num < 0 or math.isnan(start_num) or math.isinf(start_num):
                start_num = 0.0
        except (ValueError, TypeError, OverflowError):
            start_num = 0.0
        end_val = segment.get("end")
        try:
            end_num = float(end_val) if end_val is not None else start_num + 2.0
            if end_num < start_num or math.isnan(end_num) or math.isinf(end_num):
                end_num = start_num + 2.0
        except (ValueError, TypeError, OverflowError):
            end_num = start_num + 2.0

        start_str = format_timestamp(start_num, separator=",")
        end_str = format_timestamp(end_num, separator=",")

        lines.append(str(sub_idx))
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
        sub_idx += 1
    return "\n".join(lines)


def build_vtt(segments: list[dict[str, Any]]) -> str:
    """Generate standard WebVTT subtitles."""
    lines: list[str] = ["WEBVTT", ""]
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue

        start_val = segment.get("start")
        try:
            start_num = float(start_val) if start_val is not None else 0.0
            if start_num < 0 or math.isnan(start_num) or math.isinf(start_num):
                start_num = 0.0
        except (ValueError, TypeError, OverflowError):
            start_num = 0.0
        end_val = segment.get("end")
        try:
            end_num = float(end_val) if end_val is not None else start_num + 2.0
            if end_num < start_num or math.isnan(end_num) or math.isinf(end_num):
                end_num = start_num + 2.0
        except (ValueError, TypeError, OverflowError):
            end_num = start_num + 2.0

        start_str = format_timestamp(start_num, separator=".")
        end_str = format_timestamp(end_num, separator=".")

        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def write_transcript_artifacts(
    *,
    job_dir: Path,
    transcript_text: str,
    segments: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Writes all 4 standard artifact files (txt, srt, vtt, json) and returns their filepaths."""
    job_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "txt": job_dir / "transcript.txt",
        "srt": job_dir / "transcript.srt",
        "vtt": job_dir / "transcript.vtt",
        "json": job_dir / "transcript.json",
    }

    paths["txt"].write_text(transcript_text.strip() + "\n", encoding="utf-8")
    paths["srt"].write_text(build_srt(segments), encoding="utf-8")
    paths["vtt"].write_text(build_vtt(segments), encoding="utf-8")

    json_payload = {
        "text": transcript_text,
        "segments": segments,
        "metadata": metadata or {},
    }
    paths["json"].write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {name: str(path) for name, path in paths.items()}

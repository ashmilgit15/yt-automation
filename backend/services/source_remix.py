from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from backend.core.config import get_settings
from backend.services.llm import LLMService
from backend.services.utils import (
    call_with_backoff,
    ensure_directory,
    extract_json_payload,
    ffprobe_duration,
    get_job_directory,
    run_command,
    write_json_file,
)
from backend.services.ytdlp_classifier import YOUTUBE_PLAYER_CLIENTS_ARG


settings = get_settings()


class SourceRemixService:
    def __init__(self) -> None:
        self._llm = LLMService()

    def discover_source_video(
        self, *, topic: str, target_audience: str | None
    ) -> dict[str, Any]:
        candidates = self._search_firecrawl(topic)
        if not candidates:
            candidates = self._search_yt_dlp(topic)

        if not candidates:
            raise RuntimeError(
                "No suitable YouTube source video was found for this topic. Try a more specific topic."
            )

        ranked_candidates = [
            candidate
            for candidate in candidates
            if 480 <= int(candidate.get("duration_seconds", 0)) <= 14400
        ]
        if not ranked_candidates:
            ranked_candidates = candidates

        selected = self._select_best_candidate(
            topic=topic,
            target_audience=target_audience,
            candidates=ranked_candidates,
        )
        return selected

    def download_source_video(self, *, job_id: str, source_url: str) -> dict[str, Any]:
        source_dir = ensure_directory(get_job_directory(job_id) / "source")
        output_template = str((source_dir / "source_video.%(ext)s").resolve())

        def _request() -> str:
            result = run_command(
                [
                    "yt-dlp",
                    "--no-playlist",
                    "--no-progress",
                    "--extractor-args",
                    YOUTUBE_PLAYER_CLIENTS_ARG,
                    "--remote-components",
                    "ejs:github",
                    "--no-check-certificates",
                    "--geo-bypass",
                    "--merge-output-format",
                    "mp4",
                    "-f",
                    "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best",
                    "-o",
                    output_template,
                    "--print",
                    "after_move:filepath",
                    source_url,
                ]
            )
            lines = [
                line.strip() for line in result.stdout.splitlines() if line.strip()
            ]
            if not lines:
                raise RuntimeError("yt-dlp did not return a downloaded filepath.")
            return lines[-1]

        downloaded_path = Path(call_with_backoff(_request)).resolve()
        audio_path = (source_dir / "source_audio.mp3").resolve()
        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(downloaded_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "libmp3lame",
                str(audio_path),
            ]
        )
        return {
            "video_path": str(downloaded_path),
            "audio_path": str(audio_path),
            "video_duration_seconds": ffprobe_duration(downloaded_path),
        }

    def plan_remix_shots(
        self,
        *,
        job_id: str,
        topic: str,
        source_metadata: dict[str, Any],
        transcript_payload: dict[str, Any],
        shots_count: int,
        orientation: str,
        target_audience: str | None,
    ) -> dict[str, Any]:
        transcript_segments = self._compact_segments(transcript_payload)
        if not transcript_segments:
            raise RuntimeError(
                "The source video transcript did not contain usable segments."
            )

        max_total_duration = 59 if orientation == "portrait" else 150
        max_shot_duration = max(
            5.0, min(16.0, max_total_duration / max(shots_count, 1))
        )

        try:
            prompt = (
                "You are a viral short-form editor turning a long-form YouTube video into a fast-paced highlight remix. "
                "Return strict JSON with this exact shape: "
                '{"hook_text": "...", "title": "...", "description": "...", "tags": ["..."], "hashtags": ["#..."], '
                '"shots": [{"start_seconds": 0, "end_seconds": 0, "caption_text": "...", "transcript_excerpt": "...", "reason": "..."}]}. '
                f"Topic: {topic}. Source title: {source_metadata.get('title')}. Target audience: {target_audience or 'general audience'}. Orientation: {orientation}. "
                f"Create exactly {shots_count} shots. Total combined duration must stay under {max_total_duration} seconds. "
                f"Each shot should usually be 4 to {max_shot_duration:.0f} seconds. "
                "Pick the most emotionally charged, surprising, useful, or opinionated moments. "
                "Write short all-caps caption_text values that feel like viral captions. Transcript segments follow:\n"
                f"{json.dumps(transcript_segments[:80], ensure_ascii=True)}"
            )

            planned = self._llm.generate_json(prompt, temperature=0.7)
        except Exception:
            planned = {}

        sanitized_shots = self._sanitize_shots(
            shots=planned.get("shots") or [],
            transcript_segments=transcript_segments,
            shots_count=shots_count,
            max_total_duration=max_total_duration,
            max_shot_duration=max_shot_duration,
        )
        if not sanitized_shots:
            sanitized_shots = self._fallback_shots(
                transcript_segments=transcript_segments,
                shots_count=shots_count,
                max_total_duration=max_total_duration,
                max_shot_duration=max_shot_duration,
            )

        payload = {
            "hook_text": planned.get("hook_text") or f"{topic.upper()[:36]} RIGHT NOW",
            "title": planned.get("title") or f"{topic}: Best Moments Breakdown",
            "description": planned.get("description")
            or f"Fast remix of the best moments from {source_metadata.get('title')}.",
            "tags": planned.get("tags") or [topic, "viral clips", "youtube highlights"],
            "hashtags": planned.get("hashtags")
            or ["#Shorts", "#ViralClips", "#Trending"],
            "shots": sanitized_shots,
        }

        write_json_file(
            (get_job_directory(job_id) / "remix_plan.json").resolve(),
            payload,
        )
        return payload

    def compose_remix(
        self,
        *,
        job_id: str,
        source_video_path: str | Path,
        shots: list[dict[str, Any]],
        orientation: str,
        hook_text: str,
    ) -> dict[str, Any]:
        source_video = Path(source_video_path).resolve()
        job_dir = get_job_directory(job_id).resolve()
        remix_dir = ensure_directory(job_dir / "remix")
        dimensions = (1080, 1920) if orientation == "portrait" else (1920, 1080)
        caption_font_size = 50 if orientation == "portrait" else 34
        intro_font_size = 60 if orientation == "portrait" else 40

        segment_paths: list[Path] = []
        for index, shot in enumerate(shots, start=1):
            start_seconds = float(shot.get("start_seconds", 0.0))
            end_seconds = float(shot.get("end_seconds", start_seconds + 5.0))
            duration = max(end_seconds - start_seconds, 1.5)
            caption_path = (remix_dir / f"caption_{index:02d}.txt").resolve()
            caption_path.write_text(
                self._prepare_overlay_text(
                    str(
                        shot.get("caption_text") or shot.get("transcript_excerpt") or ""
                    ),
                    orientation=orientation,
                ),
                encoding="utf-8",
            )
            segment_path = (remix_dir / f"shot_{index:02d}.mp4").resolve()

            filter_graph = self._build_segment_filter(
                caption_path=caption_path,
                dimensions=dimensions,
                caption_font_size=caption_font_size,
            )
            run_command(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{start_seconds:.3f}",
                    "-i",
                    str(source_video),
                    "-t",
                    f"{duration:.3f}",
                    "-vf",
                    filter_graph,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    str(segment_path),
                ]
            )
            segment_paths.append(segment_path)

        concat_list_path = (remix_dir / "concat.txt").resolve()
        concat_list_path.write_text(
            "\n".join(f"file '{path.as_posix()}'" for path in segment_paths),
            encoding="utf-8",
        )
        stitched_path = (remix_dir / "stitched_remix.mp4").resolve()
        run_command(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                str(stitched_path),
            ]
        )

        final_path = (job_dir / "final_video.mp4").resolve()
        hook_text_path = (remix_dir / "hook_text.txt").resolve()
        hook_text_path.write_text(
            self._prepare_overlay_text(hook_text, orientation=orientation),
            encoding="utf-8",
        )
        run_command(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(stitched_path),
                "-vf",
                self._build_intro_filter(
                    text_path=hook_text_path,
                    dimensions=dimensions,
                    font_size=intro_font_size,
                ),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(final_path),
            ]
        )

        return {
            "final_video_path": str(final_path),
            "stitched_path": str(stitched_path),
        }

    def _search_firecrawl(self, topic: str) -> list[dict[str, Any]]:
        if not settings.firecrawl_api_key:
            return []

        headers = {
            "Authorization": f"Bearer {settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        query = f"site:youtube.com/watch {topic} podcast OR interview OR analysis OR full discussion"
        payload = {"query": query, "limit": 8}

        def _request() -> requests.Response:
            response = requests.post(
                f"{settings.firecrawl_base_url.rstrip('/')}/v1/search",
                headers=headers,
                data=json.dumps(payload),
                timeout=60,
            )
            response.raise_for_status()
            return response

        response = call_with_backoff(_request)
        discovered: list[dict[str, Any]] = []
        for item in response.json().get("data", []):
            normalized = self._normalize_youtube_url(item.get("url", ""))
            if not normalized:
                continue
            metadata = self._fetch_youtube_metadata(normalized)
            if metadata:
                discovered.append(metadata)
        return discovered

    def _search_yt_dlp(self, topic: str) -> list[dict[str, Any]]:
        search_query = f"ytsearch8:{topic} podcast interview analysis"

        def _request() -> list[dict[str, Any]]:
            result = run_command(
                [
                    "yt-dlp",
                    "--dump-single-json",
                    "--no-warnings",
                    "--extractor-args",
                    YOUTUBE_PLAYER_CLIENTS_ARG,
                    "--remote-components",
                    "ejs:github",
                    "--no-check-certificates",
                    "--geo-bypass",
                    search_query,
                ]
            )
            payload = json.loads(result.stdout)
            entries = payload.get("entries") or []
            discovered: list[dict[str, Any]] = []
            for entry in entries:
                webpage_url = self._normalize_youtube_url(
                    str(entry.get("webpage_url") or "")
                )
                if not webpage_url:
                    continue
                discovered.append(
                    {
                        "url": webpage_url,
                        "title": str(entry.get("title") or "Untitled"),
                        "channel": str(entry.get("channel") or "Unknown"),
                        "duration_seconds": int(entry.get("duration") or 0),
                        "description": str(entry.get("description") or "")[:500],
                    }
                )
            return discovered

        return call_with_backoff(_request)

    def _fetch_youtube_metadata(self, url: str) -> dict[str, Any] | None:
        def _request() -> dict[str, Any]:
            result = run_command(
                [
                    "yt-dlp",
                    "--dump-single-json",
                    "--no-warnings",
                    "--skip-download",
                    "--extractor-args",
                    YOUTUBE_PLAYER_CLIENTS_ARG,
                    "--remote-components",
                    "ejs:github",
                    "--no-check-certificates",
                    "--geo-bypass",
                    url,
                ]
            )
            payload = json.loads(result.stdout)
            return {
                "url": self._normalize_youtube_url(url) or url,
                "title": str(payload.get("title") or "Untitled"),
                "channel": str(
                    payload.get("channel") or payload.get("uploader") or "Unknown"
                ),
                "duration_seconds": int(payload.get("duration") or 0),
                "description": str(payload.get("description") or "")[:500],
            }

        try:
            return call_with_backoff(_request)
        except Exception:
            return None

    def _select_best_candidate(
        self,
        *,
        topic: str,
        target_audience: str | None,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            prompt = (
                "Choose the strongest long-form YouTube source for a remix editing pipeline. "
                "Return strict JSON like {'index': 0, 'reason': '...'}. "
                f"Topic: {topic}. Target audience: {target_audience or 'general audience'}. Candidates: {json.dumps(candidates[:6], ensure_ascii=True)}"
            )

            judged = self._llm.generate_json(prompt, temperature=0.2)
            index = int(judged.get("index", 0))
            if 0 <= index < len(candidates):
                selected = dict(candidates[index])
                selected["selection_reason"] = judged.get("reason")
                return selected
        except Exception:
            pass

        sorted_candidates = sorted(
            candidates,
            key=lambda item: (
                int(item.get("duration_seconds", 0)) >= 900,
                int(item.get("duration_seconds", 0)),
            ),
            reverse=True,
        )
        selected = dict(sorted_candidates[0])
        selected["selection_reason"] = "Selected by duration and availability fallback."
        return selected

    def _compact_segments(
        self, transcript_payload: dict[str, Any]
    ) -> list[dict[str, Any]]:
        segments = transcript_payload.get("segments") or []
        compacted: list[dict[str, Any]] = []
        for segment in segments:
            text = str(segment.get("text") or "").strip()
            if not text:
                continue
            compacted.append(
                {
                    "start_seconds": float(segment.get("start", 0.0)),
                    "end_seconds": float(segment.get("end", 0.0)),
                    "text": text,
                }
            )
        return compacted

    def _sanitize_shots(
        self,
        *,
        shots: list[dict[str, Any]],
        transcript_segments: list[dict[str, Any]],
        shots_count: int,
        max_total_duration: float,
        max_shot_duration: float,
    ) -> list[dict[str, Any]]:
        if not shots:
            return []

        max_end = max(float(segment["end_seconds"]) for segment in transcript_segments)
        sanitized: list[dict[str, Any]] = []
        total_duration = 0.0
        for shot in shots:
            start = max(float(shot.get("start_seconds", 0.0)), 0.0)
            end = min(float(shot.get("end_seconds", start + 5.0)), max_end)
            duration = max(min(end - start, max_shot_duration), 2.5)
            if total_duration + duration > max_total_duration:
                break
            matching_segments = [
                segment
                for segment in transcript_segments
                if float(segment["start_seconds"]) < end
                and float(segment["end_seconds"]) > start
            ]
            transcript_excerpt = " ".join(
                segment["text"] for segment in matching_segments
            )[:280]
            sanitized.append(
                {
                    "start_seconds": round(start, 3),
                    "end_seconds": round(start + duration, 3),
                    "caption_text": str(
                        shot.get("caption_text") or transcript_excerpt[:72]
                    ).strip(),
                    "transcript_excerpt": transcript_excerpt,
                    "reason": str(shot.get("reason") or "highlight moment").strip(),
                }
            )
            total_duration += duration
            if len(sanitized) >= shots_count:
                break
        return sanitized

    def _fallback_shots(
        self,
        *,
        transcript_segments: list[dict[str, Any]],
        shots_count: int,
        max_total_duration: float,
        max_shot_duration: float,
    ) -> list[dict[str, Any]]:
        usable_segments = [
            segment
            for segment in transcript_segments
            if len(segment["text"].split()) >= 6
        ]
        if not usable_segments:
            usable_segments = transcript_segments
        stride = max(len(usable_segments) // max(shots_count, 1), 1)
        chosen = usable_segments[::stride][:shots_count]
        fallback: list[dict[str, Any]] = []
        total_duration = 0.0
        for segment in chosen:
            start = float(segment["start_seconds"])
            end = min(float(segment["end_seconds"]), start + max_shot_duration)
            duration = max(min(end - start, max_shot_duration), 3.0)
            if total_duration + duration > max_total_duration:
                break
            text = segment["text"]
            fallback.append(
                {
                    "start_seconds": round(start, 3),
                    "end_seconds": round(start + duration, 3),
                    "caption_text": " ".join(text.upper().split())[:72],
                    "transcript_excerpt": text[:280],
                    "reason": "Selected from transcript fallback.",
                }
            )
            total_duration += duration
        return fallback

    @staticmethod
    def _normalize_youtube_url(url: str) -> str | None:
        if not url:
            return None
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.strip("/")
            return f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        if "youtube.com" in parsed.netloc:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
                return (
                    f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                )
            if parsed.path.startswith("/shorts/"):
                video_id = parsed.path.split("/shorts/")[-1].strip("/")
                return (
                    f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                )
        return None

    def _build_segment_filter(
        self,
        *,
        caption_path: Path,
        dimensions: tuple[int, int],
        caption_font_size: int,
    ) -> str:
        width, height = dimensions
        box_y = 110 if height >= 1500 else 64
        box_h = 210 if height >= 1500 else 140
        caption_file = self._escape_filter_path(caption_path)
        return (
            f"scale={int(width * 1.08)}:{int(height * 1.08)}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},eq=saturation=1.15:contrast=1.06:brightness=0.02,"
            "unsharp=5:5:0.45:5:5:0.0,"
            f"drawbox=x=70:y={box_y}:w=iw-140:h={box_h}:color=black@0.34:t=fill:enable='lt(t\\,5.8)',"
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"textfile='{caption_file}':reload=0:fontcolor=white:fontsize={caption_font_size}:line_spacing=10:"
            f"x=(w-text_w)/2:y={box_y + 34}:enable='lt(t\\,5.8)',"
            "fade=t=in:st=0:d=0.12"
        )

    def _build_intro_filter(
        self, *, text_path: Path, dimensions: tuple[int, int], font_size: int
    ) -> str:
        _, height = dimensions
        box_y = 96 if height >= 1500 else 56
        box_h = 210 if height >= 1500 else 150
        hook_file = self._escape_filter_path(text_path)
        return (
            f"drawbox=x=70:y={box_y}:w=iw-140:h={box_h}:color=black@0.38:t=fill:enable='lt(t\\,2.6)',"
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"textfile='{hook_file}':reload=0:fontcolor=white:fontsize={font_size}:line_spacing=10:"
            f"x=(w-text_w)/2:y={box_y + 38}:enable='lt(t\\,2.6)'"
        )

    @staticmethod
    def _prepare_overlay_text(text: str, *, orientation: str) -> str:
        cleaned = " ".join(text.upper().split())
        if not cleaned:
            return ""
        max_chars = 18 if orientation == "portrait" else 28
        words = cleaned.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= max_chars or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
            if len(lines) >= 2:
                break
        if current and len(lines) < 2:
            lines.append(current)
        return "\n".join(lines[:2])[: max_chars * 2 + 2]

    @staticmethod
    def _escape_filter_path(path: Path) -> str:
        return path.as_posix().replace("'", r"\'").replace(":", r"\:")

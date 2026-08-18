from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend.core.config import get_settings
from backend.services.ytdlp_classifier import YOUTUBE_PLAYER_CLIENTS_ARG


class YouTubePlaylistService:
    """Reads playlist or single video metadata locally through yt-dlp; no YouTube API key is used."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def analyse(self, playlist_url: str) -> dict[str, object]:
        playlist_id = self.extract_playlist_id(playlist_url)
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-warnings",
            "--flat-playlist",
            "--dump-single-json",
            "--extractor-args",
            YOUTUBE_PLAYER_CLIENTS_ARG,
            "--remote-components",
            "ejs:github",
            "--no-check-certificates",
            "--geo-bypass",
            "--playlist-end",
            str(self.settings.transcription_max_playlist_items),
            playlist_url,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "yt-dlp could not read this URL.").strip()
            raise ValueError(f"Analysis failed: {message[-700:]}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("yt-dlp returned an invalid response.") from exc

        videos: list[dict[str, object]] = []
        entries = payload.get("entries")

        if entries and isinstance(entries, list):
            for position, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                video_id = str(entry.get("id") or "").strip()
                if not video_id:
                    continue
                duration = entry.get("duration")
                videos.append(
                    {
                        "video_id": video_id,
                        "title": str(entry.get("title") or "Untitled video"),
                        "channel_title": entry.get("channel") or entry.get("uploader"),
                        "duration_seconds": int(duration) if isinstance(duration, (int, float)) else None,
                        "thumbnail_url": entry.get("thumbnail"),
                        "position": position,
                    }
                )
        else:
            # Single video payload
            video_id = str(payload.get("id") or "").strip() or playlist_id
            duration = payload.get("duration")
            videos.append(
                {
                    "video_id": video_id,
                    "title": str(payload.get("title") or "YouTube Video"),
                    "channel_title": payload.get("channel") or payload.get("uploader"),
                    "duration_seconds": int(duration) if isinstance(duration, (int, float)) else None,
                    "thumbnail_url": payload.get("thumbnail"),
                    "position": 0,
                }
            )

        if not videos:
            raise ValueError("No accessible videos were found at this URL.")
        return {
            "playlist_id": playlist_id,
            "playlist_url": playlist_url,
            "title": payload.get("title") or "YouTube Media",
            "videos": videos,
        }

    @staticmethod
    def extract_playlist_id(value: str) -> str:
        parsed = urlparse(value.strip())
        query = parse_qs(parsed.query)
        if "list" in query:
            return query["list"][0]
        if "watch" in parsed.path and "v" in query:
            return query["v"][0]
        if parsed.netloc in {"youtu.be", "www.youtu.be"}:
            path_part = parsed.path.lstrip("/").split("?")[0].split("&")[0]
            if path_part:
                return path_part
        path_segments = [seg for seg in parsed.path.split("/") if seg]
        if path_segments:
            return path_segments[-1]
        return "custom-batch"

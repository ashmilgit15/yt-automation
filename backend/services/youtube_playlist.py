from __future__ import annotations

import json
import subprocess
import sys
from typing import Any
from urllib.parse import parse_qs, urlparse

from backend.core.config import get_settings


class YouTubePlaylistService:
    """Reads playlist metadata locally through yt-dlp; no YouTube API key is used."""

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
            "--playlist-end",
            str(self.settings.transcription_max_playlist_items),
            playlist_url,
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "yt-dlp could not read this playlist.").strip()
            raise ValueError(f"Playlist analysis failed: {message[-700:]}")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError("yt-dlp returned an invalid playlist response.") from exc

        videos: list[dict[str, object]] = []
        for position, entry in enumerate(payload.get("entries") or []):
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

        if not videos:
            raise ValueError("No accessible videos were found in this playlist.")
        return {
            "playlist_id": playlist_id,
            "playlist_url": playlist_url,
            "title": payload.get("title"),
            "videos": videos,
        }

    @staticmethod
    def extract_playlist_id(value: str) -> str:
        parsed = urlparse(value.strip())
        playlist_id = parse_qs(parsed.query).get("list", [None])[0]
        if not playlist_id:
            raise ValueError("Enter a valid YouTube playlist URL containing a list parameter.")
        return playlist_id

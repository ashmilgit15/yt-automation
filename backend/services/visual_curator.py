from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import requests
from PIL import Image

from backend.core.config import get_settings
from backend.services.llm import LLMService
from backend.services.utils import (
    call_with_backoff,
    extract_json_payload,
    get_job_directory,
    maybe_sleep_for_rate_limit,
)


settings = get_settings()


class VisualCuratorService:
    def __init__(self) -> None:
        self._llm = LLMService()

    def curate(
        self, *, job_id: str, scenes: list[dict[str, Any]], orientation: str
    ) -> dict[str, Any]:
        if not settings.pexels_api_key:
            raise RuntimeError(
                "PEXELS_API_KEY is not configured. Visual curation cannot continue."
            )

        visuals_dir = get_job_directory(job_id) / "visuals"
        visuals_dir.mkdir(parents=True, exist_ok=True)

        manifest: list[dict[str, Any]] = []
        for index, scene in enumerate(scenes, start=1):
            candidates = self._search_pexels(
                query=scene.get("visual_keyword")
                or scene.get("sentence")
                or "abstract cinematic",
                orientation=orientation,
            )
            if not candidates:
                raise RuntimeError(f"No Pexels videos returned for scene {index}")

            scores = self._score_candidates(
                sentence=scene.get("sentence", ""), candidates=candidates
            )
            best_candidate = max(scores, key=lambda item: item["score"])
            candidate = candidates[best_candidate["index"]]

            local_path = visuals_dir / f"scene_{index:02d}.mp4"
            self._download_file(candidate["download_url"], local_path)

            manifest.append(
                {
                    "scene_index": index,
                    "sentence": scene.get("sentence"),
                    "visual_keyword": scene.get("visual_keyword"),
                    "pexels_video_id": candidate["id"],
                    "thumbnail_url": candidate["thumbnail_url"],
                    "download_url": candidate["download_url"],
                    "local_path": str(local_path),
                    "score": best_candidate["score"],
                    "reason": best_candidate.get("reason"),
                }
            )

        return {"assets": manifest}

    def _search_pexels(self, *, query: str, orientation: str) -> list[dict[str, Any]]:
        headers = {"Authorization": settings.pexels_api_key or ""}
        params = {
            "query": query,
            "per_page": 5,
            "orientation": orientation,
            "size": "medium",
        }

        def _request() -> requests.Response:
            response = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params=params,
                timeout=60,
            )
            response.raise_for_status()
            maybe_sleep_for_rate_limit(dict(response.headers))
            return response

        response = call_with_backoff(_request)
        videos = response.json().get("videos", [])
        candidates: list[dict[str, Any]] = []
        for video in videos[:5]:
            best_file = self._pick_best_file(video.get("video_files", []))
            if not best_file:
                continue
            candidates.append(
                {
                    "id": video.get("id"),
                    "thumbnail_url": video.get("image"),
                    "download_url": best_file.get("link"),
                    "width": best_file.get("width"),
                    "height": best_file.get("height"),
                    "duration": video.get("duration"),
                }
            )
        return candidates

    def _score_candidates(
        self, *, sentence: str, candidates: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        prompt = (
            "Act as a critical stock footage director. Review the numbered candidate thumbnails for the provided narration sentence. "
            "Return strict JSON with shape {'scores': [{'index': 0, 'score': 1-10, 'reason': '...'}]}. "
            f"Narration sentence: {sentence}. Favor clips that visually reinforce the sentence literally and emotionally."
        )

        images = []
        image_count = 0
        for index, candidate in enumerate(candidates):
            thumbnail_url = candidate.get("thumbnail_url")
            if not thumbnail_url:
                continue

            def _fetch() -> requests.Response:
                response = requests.get(thumbnail_url, timeout=60)
                response.raise_for_status()
                return response

            thumb_response = call_with_backoff(_fetch)
            prompt += f"\nCandidate {index} thumbnail below."
            images.append(Image.open(io.BytesIO(thumb_response.content)))
            image_count += 1

        if image_count == 0:
            return [
                {
                    "index": index,
                    "score": 5,
                    "reason": "No thumbnails were available for scoring.",
                }
                for index in range(len(candidates))
            ]

        try:
            scored = self._llm.generate_json(prompt, temperature=0.2, images=images)
            scores = scored.get("scores", [])
            if not scores:
                raise ValueError("No scores returned.")
            return scores
        except Exception:
            return [
                {
                    "index": index,
                    "score": 5,
                    "reason": "LLM scoring unavailable or failed; defaulted to first-pass ranking.",
                }
                for index in range(len(candidates))
            ]

    def _download_file(self, url: str, destination: Path) -> None:
        def _request() -> requests.Response:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            return response

        response = call_with_backoff(_request)
        destination.write_bytes(response.content)

    @staticmethod
    def _pick_best_file(video_files: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not video_files:
            return None
        sorted_files = sorted(
            video_files,
            key=lambda item: (
                item.get("width", 0) * item.get("height", 0),
                item.get("fps", 0),
            ),
            reverse=True,
        )
        return sorted_files[0]

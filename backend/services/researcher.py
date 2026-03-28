from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote_plus

import feedparser
import requests

from backend.core.config import get_settings
from backend.services.llm import LLMService
from backend.services.utils import call_with_backoff

settings = get_settings()


class ResearcherService:
    def __init__(self) -> None:
        self._llm = LLMService()

    def generate_narrative(
        self,
        *,
        topic: str,
        duration_seconds: int,
        orientation: str,
        target_audience: str | None,
    ) -> dict[str, Any]:
        context = self._collect_context(topic)

        prompt = (
            "You are a viral faceless video director creating a YouTube-ready short script. "
            "Use the supplied research context to write a tight, original, platform-safe script. "
            "Return strict JSON with this exact shape: "
            '{"script_text": "...", "scenes": [{"sentence": "...", "visual_keyword": "..."}], '
            '"title": "...", "description": "...", "tags": ["..."], "hashtags": ["#..."], "hook_text": "..."}. '
            f"Topic: {topic}. Duration target: {duration_seconds} seconds. Orientation: {orientation}. "
            f"Target audience: {target_audience or 'general audience'}. "
            "Rules: 5-8 scenes, every scene sentence must be concise and energetic, every visual_keyword must be literal and searchable on stock sites, "
            "the title must be curiosity-driven and scroll-stopping, the description must feel like trendy YouTube metadata with a short hook, a CTA, and 3-5 hashtags, "
            "the hashtags array must contain clean platform-style hashtags, hook_text must be a punchy all-caps opening caption under 12 words, "
            "no markdown, no commentary, no code fences. Context follows:\n"
            f"{context}"
        )

        payload = self._llm.generate_json(prompt, temperature=0.8)
        payload["context"] = context
        return payload

    def generate_subniche_plan(
        self,
        *,
        niche: str,
        target_audience: str | None,
        orientation: str,
        videos_count: int = 5,
    ) -> list[dict[str, Any]]:
        try:
            prompt = (
                "You are a YouTube niche strategist building a content batch for an automation pipeline. "
                "Return strict JSON with this shape: "
                '{"videos": [{"sub_niche": "...", "topic": "...", "angle": "...", "target_audience": "..."}]}. '
                f"Main niche: {niche}. Target audience: {target_audience or 'general audience'}. Orientation: {orientation}. "
                f"Create exactly {videos_count} distinct sub-niche video ideas. "
                "Rules: each topic must be specific, click-worthy, non-overlapping, easy to understand, and suitable for a viral faceless YouTube video. "
                "Avoid duplicates, avoid generic filler, and keep every topic under 120 characters."
            )
            payload = self._llm.generate_json(prompt, temperature=0.8)
            videos = payload.get("videos") or []
            if videos:
                return videos[:videos_count]
        except Exception:
            pass

        audience = target_audience or "Ambitious professionals"
        templates = [
            "Biggest shifts in {niche} this week",
            "What founders are missing about {niche}",
            "Best opportunities in {niche} right now",
            "Risks nobody sees in {niche}",
            "How {niche} is changing the next 12 months",
            "Unexpected winners in {niche}",
            "Tools redefining {niche} today",
            "Hidden trends driving {niche}",
        ]
        planned: list[dict[str, Any]] = []
        for index in range(videos_count):
            topic = templates[index % len(templates)].format(niche=niche).strip()
            planned.append(
                {
                    "sub_niche": topic,
                    "topic": topic,
                    "angle": "trend analysis",
                    "target_audience": audience,
                }
            )
        return planned

    def regenerate_metadata(
        self,
        *,
        topic: str,
        script_text: str,
        orientation: str,
        target_audience: str | None,
    ) -> dict[str, Any]:
        prompt = (
            "You are a senior viral YouTube metadata strategist. "
            "Given the topic and finished narration script, generate stronger metadata for the platform. "
            "Return strict JSON with exactly this shape: "
            '{"title": "...", "description": "...", "tags": ["..."], "hashtags": ["#..."], "hook_text": "..."}. '
            f"Topic: {topic}. Orientation: {orientation}. Target audience: {target_audience or 'general audience'}. "
            "Rules: make the title punchy and curiosity-driven without clickbait spam, keep the description trendy and natural, include 3-6 clean hashtags, include useful searchable tags, and write a bold opening hook under 12 words. "
            "Do not return markdown or commentary. Script follows:\n"
            f"{script_text}"
        )

        return self._llm.generate_json(prompt, temperature=0.8)

    def _collect_context(self, topic: str) -> str:
        context_blocks: list[str] = []

        rss_blocks = self._fetch_google_news_rss(topic)
        if rss_blocks:
            context_blocks.extend(rss_blocks)

        if settings.firecrawl_api_key and not context_blocks:
            context_blocks.extend(self._fetch_firecrawl_search_brief(topic))

        if not context_blocks:
            context_blocks.append(
                f"Topic briefing fallback: Generate a concise explainer on '{topic}' using up-to-date general knowledge."
            )

        return "\n\n".join(context_blocks[:12])

    def _fetch_google_news_rss(self, topic: str) -> list[str]:
        query = quote_plus(topic)
        feed_url = f"https://news.google.com/rss/search?q={query}"

        def _request() -> Any:
            parsed = feedparser.parse(feed_url)
            if getattr(parsed, "bozo", False) and not parsed.entries:
                raise RuntimeError(f"Failed to parse RSS feed for topic '{topic}'")
            return parsed

        parsed = call_with_backoff(_request, retries=3)
        blocks: list[str] = []
        for entry in parsed.entries[:8]:
            title = getattr(entry, "title", "Untitled")
            summary = getattr(entry, "summary", "")
            link = getattr(entry, "link", "")
            blocks.append(f"Source: {title}\nURL: {link}\nSummary: {summary}")
        return blocks

    def _fetch_firecrawl_search_brief(self, topic: str) -> list[str]:
        headers = {
            "Authorization": f"Bearer {settings.firecrawl_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{settings.firecrawl_base_url.rstrip('/')}/v1/search"
        payload = {
            "query": topic,
            "limit": 5,
            "scrapeOptions": {"formats": ["markdown"]},
        }

        def _request() -> requests.Response:
            response = requests.post(
                url, headers=headers, data=json.dumps(payload), timeout=60
            )
            response.raise_for_status()
            return response

        response = call_with_backoff(_request)
        data = response.json()
        documents = data.get("data", [])
        blocks: list[str] = []
        for item in documents[:5]:
            markdown = (
                item.get("markdown")
                or item.get("content")
                or item.get("rawContent")
                or ""
            )
            source_url = item.get("url", "")
            if markdown:
                blocks.append(f"URL: {source_url}\n{markdown[:4000]}")
        return blocks

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from backend.core.config import get_settings
from backend.services.utils import call_with_backoff, extract_json_payload

logger = logging.getLogger(__name__)


class TranscriptSummarizerService:
    """Autonomous AI Agent that generates executive summaries, key highlights,
    action items, and timestamped chapter breakdowns for videos and playlists."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def summarize_video(
        self,
        *,
        title: str,
        transcript_text: str,
        segments: list[dict[str, Any]] | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Generates structured summary JSON and a beautifully formatted Markdown report."""
        if not transcript_text or not transcript_text.strip():
            return {
                "summary_json": {},
                "summary_markdown": "# Summary\n\nNo transcript available to summarize.",
            }

        # Prepare segment preview for chapter extraction (first 100 segments with timestamps)
        segment_preview = ""
        if segments:
            preview_items = [
                f"[{int(s.get('start', 0)) // 60:02d}:{int(s.get('start', 0)) % 60:02d}] {s.get('text', '')}"
                for s in segments[:80]
            ]
            segment_preview = "\n".join(preview_items)

        prompt = f"""You are an elite Executive Summarizer and Video Content Analyst AI Agent.
Analyze the following transcript from the video titled "{title}".

Generate a comprehensive, high-value structured summary in JSON with the following exact keys:
1. "executive_summary": (string) A concise 2-3 paragraph executive overview explaining what was discussed, key arguments, and final conclusions.
2. "key_highlights": (list of strings) 5 to 8 clear, bulleted core insights and takeaways.
3. "action_items": (list of strings) 3 to 6 practical recommendations, tools mentioned, or action steps.
4. "chapters": (list of objects) Timed chapters representing major topic changes. Each object must have:
   - "start_seconds": (number)
   - "timestamp_label": (string, e.g. "01:23")
   - "title": (string)
   - "summary": (string, 1 sentence)
5. "key_quotes": (list of strings) 2 to 4 notable or impactful direct quotes from the speaker.
6. "sentiment_tone": (string, e.g. "Technical & Educational", "Inspiring & Motivational", etc.)

Language context: {language or 'English'}

TIMESTAMPED PREVIEW (for chapter timecodes):
{segment_preview or 'No timestamps provided'}

FULL TRANSCRIPT:
\"\"\"{transcript_text[:14000]}\"\"\"
"""
        summary_json: dict[str, Any] = {}
        try:
            summary_json = self._call_llm_json(prompt)
        except Exception as exc:
            logger.warning(f"AI Summarizer failed, using fallback: {exc}")
            summary_json = {
                "executive_summary": f"Summary for {title}: " + transcript_text[:400] + "...",
                "key_highlights": ["Key discussion points covered in video."],
                "action_items": [],
                "chapters": [],
                "key_quotes": [],
                "sentiment_tone": "Informative",
            }

        # Build clean Markdown document from JSON
        summary_markdown = self._format_summary_markdown(title=title, data=summary_json)

        return {
            "summary_json": summary_json,
            "summary_markdown": summary_markdown,
        }

    def summarize_playlist(
        self,
        *,
        playlist_title: str,
        video_summaries: list[dict[str, Any]],
    ) -> str:
        """Synthesizes multiple video summaries into a master playlist synopsis."""
        if not video_summaries:
            return f"# Playlist Summary: {playlist_title}\n\nNo video summaries available."

        summaries_text = "\n\n".join(
            [
                f"### Video: {v.get('title', 'Untitled')}\n{v.get('summary_markdown', '')[:1200]}"
                for v in video_summaries
            ]
        )

        prompt = f"""You are an AI Playlist Synthesis Agent.
Create a Master Playlist Summary for the collection "{playlist_title}" containing {len(video_summaries)} videos.

Include:
1. **Curriculum / Series Overview**: What is the grand scope of this playlist?
2. **Master Key Themes**: Across all videos, what are the primary concepts taught?
3. **Recommended Study / Viewing Order**: How should a viewer best consume this content?
4. **Comprehensive Index**: Quick 1-bullet breakdown per video.

Return your response in clean, professional GitHub Markdown.

VIDEOS SUMMARY DATA:
{summaries_text[:15000]}
"""
        try:
            # We can use text generation or JSON
            result = self._call_llm_text(prompt)
            if result and result.strip():
                return result.strip()
        except Exception as exc:
            logger.warning(f"Playlist master summary failed: {exc}")

        return f"# {playlist_title} - Master Summary\n\nThis playlist contains {len(video_summaries)} transcribed videos.\n\n" + summaries_text

    def _format_summary_markdown(self, *, title: str, data: dict[str, Any]) -> str:
        md = [f"# 📑 Executive Summary: {title}\n"]

        if data.get("sentiment_tone"):
            md.append(f"> **Tone & Style:** {data['sentiment_tone']}\n")

        if data.get("executive_summary"):
            md.append(f"## 📌 Overview\n{data['executive_summary']}\n")

        if data.get("key_highlights") and isinstance(data["key_highlights"], list):
            md.append("## 💡 Key Highlights\n")
            for item in data["key_highlights"]:
                md.append(f"- {item}")
            md.append("")

        if data.get("chapters") and isinstance(data["chapters"], list) and len(data["chapters"]) > 0:
            md.append("## ⏱️ Chapters & Topic Timeline\n")
            for ch in data["chapters"]:
                ts = ch.get("timestamp_label", "00:00")
                t_title = ch.get("title", "Chapter")
                t_desc = ch.get("summary", "")
                md.append(f"- **`{ts}`** - **{t_title}**: {t_desc}")
            md.append("")

        if data.get("action_items") and isinstance(data["action_items"], list) and len(data["action_items"]) > 0:
            md.append("## 🎯 Action Items & Takeaways\n")
            for item in data["action_items"]:
                md.append(f"- [ ] {item}")
            md.append("")

        if data.get("key_quotes") and isinstance(data["key_quotes"], list) and len(data["key_quotes"]) > 0:
            md.append("## 💬 Notable Quotes\n")
            for q in data["key_quotes"]:
                md.append(f"> \"{q}\"\n")

        return "\n".join(md)

    def _call_llm_json(self, prompt: str) -> dict[str, Any]:
        """Calls Gemini, Groq, or OpenRouter for structured JSON."""
        # 1. Gemini
        if self.settings.gemini_api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self.settings.gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")

                def _req():
                    resp = model.generate_content(
                        prompt,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": 0.3,
                        },
                    )
                    return extract_json_payload(resp.text)

                return call_with_backoff(_req)
            except Exception as e:
                logger.debug(f"Gemini summarizer attempt failed: {e}")

        # 2. Groq Chat
        if self.settings.groq_api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.settings.groq_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                }

                def _req_groq():
                    res = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60,
                    )
                    res.raise_for_status()
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return extract_json_payload(content)

                return call_with_backoff(_req_groq)
            except Exception as e:
                logger.debug(f"Groq summarizer attempt failed: {e}")

        # 3. OpenRouter
        if self.settings.openrouter_api_key:
            headers = {
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.settings.openrouter_model or "google/gemini-2.0-flash-exp:free",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            }

            def _req_or():
                res = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=90,
                )
                res.raise_for_status()
                data = res.json()
                content = data["choices"][0]["message"]["content"]
                return extract_json_payload(content)

            return call_with_backoff(_req_or)

        raise RuntimeError("No LLM API keys configured for AI Summarizer.")

    def _call_llm_text(self, prompt: str) -> str:
        """Calls Gemini, Groq, or OpenRouter for markdown text."""
        if self.settings.gemini_api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self.settings.gemini_api_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                resp = model.generate_content(prompt)
                if resp and resp.text:
                    return resp.text
            except Exception:
                pass

        if self.settings.groq_api_key:
            try:
                headers = {"Authorization": f"Bearer {self.settings.groq_api_key}", "Content-Type": "application/json"}
                res = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers,
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}]},
                    timeout=60,
                )
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except Exception:
                pass

        return ""

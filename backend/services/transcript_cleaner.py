from __future__ import annotations

import json
import logging
from typing import Any

import requests

from backend.core.config import get_settings
from backend.services.utils import call_with_backoff, extract_json_payload

logger = logging.getLogger(__name__)


class TranscriptCleanerService:
    """Autonomous AI Agent that eliminates audio filler words, speech disfluencies,
    stutters, and formatting errors while maintaining chronological timestamps."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def clean_transcript(
        self,
        *,
        raw_text: str,
        segments: list[dict[str, Any]] | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Cleans both the continuous transcript text and timestamped segments."""
        if not raw_text or not raw_text.strip():
            return {
                "clean_transcript_text": raw_text,
                "clean_segments": segments or [],
            }

        # 1. Clean full narrative text
        clean_text = self._clean_narrative_text(raw_text=raw_text, language=language)

        # 2. Clean segments if available
        clean_segments = []
        if segments and len(segments) > 0:
            clean_segments = self._clean_segments_batch(segments=segments, language=language)
        else:
            clean_segments = [{"start": 0.0, "end": 0.0, "text": clean_text}]

        return {
            "clean_transcript_text": clean_text,
            "clean_segments": clean_segments,
        }

    def _clean_narrative_text(self, *, raw_text: str, language: str | None) -> str:
        prompt = f"""You are an expert AI Audio Transcript Editor and Post-Processing Agent.
Your task is to take the following raw speech-to-text transcript and create a clean, professional, highly readable version.

Rules:
1. Remove speech disfluencies, filler words (e.g. "um", "uh", "you know", "like", "sort of", "ah"), stuttering repetitions, and phantom loop hallucinations (e.g. repeated "thank you" loops).
2. Fix sentence punctuation, capitalization, commas, periods, and question marks so the prose flows naturally.
3. Fix obvious speech-to-text misspellings while preserving technical terms, proper nouns, product names, and speaker intent.
4. Keep the original language and tone intact. Do NOT invent new facts or remove important domain content.
5. Return ONLY a valid JSON object with the key "cleaned_text".

Language hint: {language or 'auto-detect'}

RAW TRANSCRIPT:
\"\"\"{raw_text[:12000]}\"\"\"
"""
        try:
            result = self._call_llm_json(prompt)
            cleaned = result.get("cleaned_text")
            if isinstance(cleaned, str) and cleaned.strip():
                return cleaned.strip()
        except Exception as exc:
            logger.warning(f"AI Transcript Cleanup failed, falling back to basic cleanup: {exc}")

        return self._basic_fallback_clean(raw_text)

    def _clean_segments_batch(
        self,
        *,
        segments: list[dict[str, Any]],
        language: str | None,
    ) -> list[dict[str, Any]]:
        """Cleans segment text in batches while preserving start and end timestamps."""
        # For segments, clean in batches of up to 40 segments
        batch_size = 35
        cleaned_segments: list[dict[str, Any]] = []

        for i in range(0, len(segments), batch_size):
            chunk = segments[i : i + batch_size]
            items_payload = [
                {"index": idx, "start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": s.get("text", "")}
                for idx, s in enumerate(chunk)
            ]

            prompt = f"""You are an AI Subtitle & Segment Editor.
Given the following subtitle segments with their timecodes, clean each segment's text by:
1. Removing stutter and filler words ("um", "uh", "er", "you know").
2. Correcting punctuation and capitalization.
3. Preserving the exact index, start, and end timecodes.
4. Return a JSON object with key "segments" containing a list of {{"index": int, "start": float, "end": float, "text": str}}.

Language: {language or 'auto'}

INPUT SEGMENTS:
{json.dumps(items_payload, ensure_ascii=False)}
"""
            try:
                result = self._call_llm_json(prompt)
                returned_list = result.get("segments")
                if isinstance(returned_list, list) and len(returned_list) == len(chunk):
                    for item in returned_list:
                        cleaned_segments.append(
                            {
                                "start": float(item.get("start", 0.0)),
                                "end": float(item.get("end", 0.0)),
                                "text": str(item.get("text", "")).strip(),
                            }
                        )
                    continue
            except Exception as exc:
                logger.warning(f"Batch segment cleanup failed, using raw segment batch: {exc}")

            # Fallback for this chunk
            for s in chunk:
                cleaned_segments.append(
                    {
                        "start": float(s.get("start", 0.0)),
                        "end": float(s.get("end", 0.0)),
                        "text": self._basic_fallback_clean(str(s.get("text", ""))),
                    }
                )

        return cleaned_segments

    def _call_llm_json(self, prompt: str) -> dict[str, Any]:
        """Calls Hack Club AI (google/gemini-3.7-flash), Gemini, Groq, or OpenRouter with fallback."""
        # 1. Try Hack Club AI (google/gemini-3.7-flash)
        if self.settings.hackclub_api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.settings.hackclub_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.settings.hackclub_model or "google/gemini-3.7-flash",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                }

                def _req_hc():
                    url = f"{self.settings.hackclub_base_url.rstrip('/')}/chat/completions"
                    res = requests.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=90,
                    )
                    res.raise_for_status()
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return extract_json_payload(content)

                return call_with_backoff(_req_hc)
            except Exception as e:
                logger.warning(f"Hack Club AI cleaner attempt failed: {e}")

        # 2. Try Direct Gemini
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
                            "temperature": 0.2,
                        },
                    )
                    return extract_json_payload(resp.text)

                return call_with_backoff(_req)
            except Exception as e:
                logger.debug(f"Gemini cleaner attempt failed: {e}")

        # 2. Try Groq Chat (Llama-3.3-70b-versatile)
        if self.settings.groq_api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.settings.groq_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
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
                logger.debug(f"Groq cleaner attempt failed: {e}")

        # 3. Try OpenRouter
        if self.settings.openrouter_api_key:
            headers = {
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.settings.openrouter_model or "google/gemini-2.0-flash-exp:free",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
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

        raise RuntimeError("No LLM API keys configured (GEMINI_API_KEY, GROQ_API_KEY, or OPENROUTER_API_KEY).")

    @staticmethod
    def _basic_fallback_clean(text: str) -> str:
        """Lightweight regex/string cleanup if no LLM key is configured."""
        import re

        cleaned = text.strip()
        # Remove common speech filler words
        filler_pattern = r"\b(um|uh|erm|er|like,?\s*you\s*know)\b"
        cleaned = re.sub(filler_pattern, "", cleaned, flags=re.IGNORECASE)
        # Collapse multiple spaces and cleanup punctuation spacing
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = re.sub(r"\s+([.,!?;:])", r"\1", cleaned)
        return cleaned.strip()

import json
import requests
from typing import Any
from PIL import Image
import io
import base64

from backend.core.config import get_settings
from backend.services.utils import call_with_backoff, extract_json_payload

settings = get_settings()


class LLMService:
    def __init__(self):
        self._gemini_model = None
        if settings.gemini_api_key:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(settings.gemini_model)

    def generate_json(
        self, prompt: str, temperature: float = 0.8, images: list[Image.Image] = None
    ) -> dict[str, Any]:
        # Try Gemini first if available
        if self._gemini_model:
            try:

                def _request_gemini():
                    contents = [prompt]
                    if images:
                        contents.extend(images)
                    response = self._gemini_model.generate_content(
                        contents,
                        generation_config={
                            "response_mime_type": "application/json",
                            "temperature": temperature,
                        },
                    )
                    return extract_json_payload(response.text)

                return call_with_backoff(_request_gemini)
            except Exception as e:
                # Log the exception or let it pass through to fallback
                pass

        # Fallback to OpenRouter
        if not settings.openrouter_api_key:
            raise RuntimeError(
                "Neither GEMINI_API_KEY nor OPENROUTER_API_KEY is configured or both failed."
            )

        return self._generate_openrouter_json(prompt, temperature, images)

    def _generate_openrouter_json(
        self, prompt: str, temperature: float, images: list[Image.Image] = None
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if images:
            content_list = [{"type": "text", "text": prompt}]
            for img in images:
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                content_list.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_str}"},
                    }
                )
            messages.append({"role": "user", "content": content_list})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.openrouter_model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        def _request_openrouter():
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            try:
                content = data["choices"][0]["message"]["content"]
                return extract_json_payload(content)
            except (KeyError, IndexError, ValueError):
                raise RuntimeError(
                    f"Unexpected response format from OpenRouter: {data}"
                )

        return call_with_backoff(_request_openrouter)

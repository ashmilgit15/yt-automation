from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.security import decrypt_secret_maybe_legacy, encrypt_secret
from backend.models.db_models import VideoJob, YouTubeCredential
from backend.services.llm import LLMService
from backend.services.utils import call_with_backoff, extract_json_payload

settings = get_settings()


class PublisherService:
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    def __init__(self) -> None:
        self._llm = LLMService()

    def publish(
        self,
        *,
        db: Session,
        job: VideoJob,
        video_path: str | Path,
        channel_label: str,
        force: bool = False,
    ) -> dict[str, Any]:
        gate_result = self.evaluate_quality(job=job)
        if (
            gate_result["score"] < settings.quality_gate_threshold
            and not force
            and not job.manual_override
        ):
            return {
                "blocked": True,
                "quality_score": gate_result["score"],
                "critique": gate_result["critique"],
                "gate_payload": gate_result,
            }

        youtube = self._build_youtube_client(db, channel_label)
        metadata = self._build_metadata(job)
        is_shorts = bool(metadata.get("is_shorts"))
        body = {
            "snippet": {
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": metadata["tags"],
                "categoryId": settings.youtube_default_category_id,
            },
            "status": {
                "privacyStatus": metadata["privacy_status"],
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4"
        )
        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )

        def _execute() -> Any:
            return request.execute()

        response = call_with_backoff(_execute, retries=3)
        video_id = response["id"]
        return {
            "blocked": False,
            "quality_score": gate_result["score"],
            "critique": gate_result["critique"],
            "youtube_video_id": video_id,
            "youtube_url": self._build_video_url(video_id, is_shorts),
            "gate_payload": gate_result,
            "channel_label": channel_label,
        }

    def update_video_privacy(
        self, *, db: Session, job: VideoJob, privacy_status: str
    ) -> dict[str, Any]:
        if not job.youtube_video_id:
            raise RuntimeError("This job does not have an uploaded YouTube video yet.")

        if privacy_status not in {"public", "private", "unlisted"}:
            raise RuntimeError("Unsupported YouTube privacy status requested.")

        usage_metrics = dict(job.usage_metrics or {})
        channel_label = str(
            usage_metrics.get("uploaded_channel_label")
            or settings.youtube_channel_label
        )

        youtube = self._build_youtube_client(db, channel_label)
        request = youtube.videos().update(
            part="status",
            body={
                "id": job.youtube_video_id,
                "status": {
                    "privacyStatus": privacy_status,
                    "selfDeclaredMadeForKids": False,
                },
            },
        )

        def _execute() -> Any:
            return request.execute()

        call_with_backoff(_execute, retries=3)
        usage_metrics = dict(job.usage_metrics or {})
        is_shorts = self._is_shorts(job, usage_metrics)
        return {
            "youtube_video_id": job.youtube_video_id,
            "youtube_url": self._build_video_url(job.youtube_video_id, is_shorts),
            "privacy_status": privacy_status,
        }

    def update_video_metadata(self, *, db: Session, job: VideoJob) -> dict[str, Any]:
        if not job.youtube_video_id:
            raise RuntimeError("This job does not have an uploaded YouTube video yet.")

        usage_metrics = dict(job.usage_metrics or {})
        channel_label = str(
            usage_metrics.get("uploaded_channel_label")
            or settings.youtube_channel_label
        )

        youtube = self._build_youtube_client(db, channel_label)
        metadata = self._build_metadata(job)
        request = youtube.videos().update(
            part="snippet,status",
            body={
                "id": job.youtube_video_id,
                "snippet": {
                    "title": metadata["title"],
                    "description": metadata["description"],
                    "tags": metadata["tags"],
                    "categoryId": settings.youtube_default_category_id,
                },
                "status": {
                    "privacyStatus": metadata["privacy_status"],
                    "selfDeclaredMadeForKids": False,
                },
            },
        )

        def _execute() -> Any:
            return request.execute()

        call_with_backoff(_execute, retries=3)
        return {
            "youtube_video_id": job.youtube_video_id,
            "youtube_url": self._build_video_url(
                job.youtube_video_id, bool(metadata.get("is_shorts"))
            ),
        }

    def evaluate_quality(self, *, job: VideoJob) -> dict[str, Any]:
        metadata = self._build_metadata(job)
        prompt = (
            "You are auditing a draft YouTube upload for 2025/2026 inauthentic-content policy risk. "
            "Assess originality, structural value, commentary depth, pacing, and whether the metadata feels repetitive. "
            "Return strict JSON with shape {'score': 1-10, 'critique': '...', 'concerns': ['...']}. "
            f"Title: {metadata['title']}\n"
            f"Description: {metadata['description']}\n"
            f"Script: {job.script_text or ''}\n"
            f"Scenes: {json.dumps(job.scenes_json or [], ensure_ascii=True)}"
        )

        try:
            return self._llm.generate_json(prompt, temperature=0.2)
        except Exception:
            fallback_score = (
                7 if (job.script_text and len(job.script_text.split()) >= 80) else 5
            )
            critique = "LLM quality gate unavailable; used a heuristic score based on narrative depth."
            return {"score": fallback_score, "critique": critique, "concerns": []}

    def get_connection_status(
        self, *, db: Session, channel_label: str | None = None
    ) -> dict[str, Any]:
        resolved_label = channel_label or settings.youtube_channel_label
        credential = self._lookup_stored_credential(db, resolved_label)
        has_env_token = bool(settings.youtube_refresh_token)
        has_client_secrets = settings.youtube_client_secrets_path.exists()

        if credential is not None:
            connected = True
            credential_source = "database"
            scopes_json = credential.scopes_json
        elif has_env_token:
            connected = True
            credential_source = "environment"
            scopes_json = self.SCOPES
        else:
            connected = False
            credential_source = "none"
            scopes_json = None

        try:
            self._assert_oauth_ready_for_browser()
            authorization_ready = True
            message = "Ready to connect your YouTube channel from the dashboard."
        except Exception as exc:
            authorization_ready = False
            message = str(exc)

        return {
            "channel_label": resolved_label,
            "connected": connected,
            "credential_source": credential_source,
            "has_client_secrets": has_client_secrets,
            "authorization_ready": authorization_ready,
            "redirect_uri": self._youtube_oauth_redirect_uri(),
            "scopes_json": scopes_json,
            "message": message,
        }

    def build_dashboard_authorization_url(
        self, *, state: str, code_verifier: str
    ) -> str:
        self._assert_oauth_ready_for_browser()
        flow = self._build_web_flow(state=state, code_verifier=code_verifier)
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return authorization_url

    def complete_dashboard_authorization(
        self,
        *,
        db: Session,
        channel_label: str,
        state: str,
        code_verifier: str,
        code: str,
    ) -> dict[str, Any]:
        flow = self._build_web_flow(state=state, code_verifier=code_verifier)
        flow.fetch_token(code=code)

        credentials = flow.credentials
        record = self._lookup_stored_credential(db, channel_label)
        refresh_token = credentials.refresh_token
        if not refresh_token:
            if record is not None:
                refresh_token = decrypt_secret_maybe_legacy(record.refresh_token)
            elif settings.youtube_refresh_token:
                refresh_token = settings.youtube_refresh_token
            else:
                raise RuntimeError(
                    "Google did not return a refresh token. Remove this app from your Google account permissions and connect again."
                )

        encrypted_refresh_token = encrypt_secret(refresh_token)
        scopes = list(credentials.scopes or self.SCOPES)

        if record is None:
            record = YouTubeCredential(
                channel_label=channel_label,
                refresh_token=encrypted_refresh_token,
                token_uri=credentials.token_uri
                or "https://oauth2.googleapis.com/token",
                scopes_json=scopes,
            )
        else:
            record.refresh_token = encrypted_refresh_token
            record.token_uri = (
                credentials.token_uri or "https://oauth2.googleapis.com/token"
            )
            record.scopes_json = scopes

        db.add(record)
        db.commit()
        db.refresh(record)

        return {
            "channel_label": channel_label,
            "scopes_json": record.scopes_json,
            "status": "saved",
        }

    def build_frontend_callback_url(
        self,
        *,
        oauth_status: str,
        message: str | None = None,
        channel_label: str | None = None,
    ) -> str:
        query = {"youtube_oauth": oauth_status}
        if message:
            query["message"] = message
        if channel_label:
            query["channel_label"] = channel_label
        return f"{settings.frontend_origin.rstrip('/')}/?{urlencode(query)}"

    def _build_youtube_client(self, db: Session, channel_label: str | None = None):
        credentials = self._load_credentials(db, channel_label)
        credentials.refresh(Request())
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def _load_credentials(
        self, db: Session, channel_label: str | None = None
    ) -> Credentials:
        client_payload = self._load_client_payload()
        _, client_info = self._get_client_info(client_payload)

        resolved_label = channel_label or settings.youtube_channel_label
        refresh_token = settings.youtube_refresh_token
        stored_credential = self._lookup_stored_credential(db, resolved_label)
        if stored_credential is not None:
            refresh_token = decrypt_secret_maybe_legacy(stored_credential.refresh_token)

        if not refresh_token:
            raise RuntimeError(
                "No YouTube refresh token found. Connect the channel from the dashboard or set YOUTUBE_REFRESH_TOKEN."
            )

        return Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=client_info.get(
                "token_uri", "https://oauth2.googleapis.com/token"
            ),
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=self.SCOPES,
        )

    def _build_metadata(self, job: VideoJob) -> dict[str, Any]:
        usage_metrics = dict(job.usage_metrics or {})
        is_shorts = self._is_shorts(job, usage_metrics)
        hashtags = self._build_hashtags(job, usage_metrics, is_shorts)
        tags = self._build_tags(job, usage_metrics, hashtags, is_shorts)
        title = self._build_title(job, hashtags, is_shorts)
        description = self._build_description(job, usage_metrics, hashtags, is_shorts)
        privacy_status = str(
            usage_metrics.get("publish_privacy") or settings.youtube_privacy_status
        )
        if privacy_status not in {"public", "private", "unlisted"}:
            privacy_status = settings.youtube_privacy_status
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "privacy_status": privacy_status,
            "is_shorts": is_shorts,
        }

    def _build_title(self, job: VideoJob, hashtags: list[str], is_shorts: bool) -> str:
        base_title = (job.title or job.topic or "AI Update").strip()
        if is_shorts and "#shorts" not in base_title.lower():
            trimmed = base_title[:88].rstrip()
            base_title = f"{trimmed} #Shorts"
        return base_title[:100].strip()

    def _build_description(
        self,
        job: VideoJob,
        usage_metrics: dict[str, Any],
        hashtags: list[str],
        is_shorts: bool,
    ) -> str:
        hook_text = str(
            usage_metrics.get("hook_text") or job.title or job.topic
        ).strip()
        core_description = (job.description or "").strip()
        if not core_description:
            core_description = "Fast breakdown of the biggest shifts, opportunities, and risks shaping this topic right now."
        cta = (
            "Follow for sharper AI, startup, and automation updates."
            if is_shorts
            else "Subscribe for more AI, startup, and automation deep dives."
        )
        hashtag_line = " ".join(hashtags)
        description_parts = [hook_text, "", core_description, "", cta, "", hashtag_line]
        return "\n".join(
            part for part in description_parts if part is not None
        ).strip()[:5000]

    def _build_hashtags(
        self,
        job: VideoJob,
        usage_metrics: dict[str, Any],
        is_shorts: bool,
    ) -> list[str]:
        raw_hashtags = usage_metrics.get("metadata_hashtags") or []
        normalized: list[str] = []
        seen: set[str] = set()

        def add_hashtag(value: str) -> None:
            candidate = value.strip().replace(" ", "")
            if not candidate:
                return
            if not candidate.startswith("#"):
                candidate = f"#{candidate}"
            lowered = candidate.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            normalized.append(candidate)

        for hashtag in raw_hashtags:
            add_hashtag(str(hashtag))

        topic_lower = (job.topic or "").lower()
        defaults = ["#AI", "#Innovation", "#TechNews"]
        if "startup" in topic_lower or "founder" in topic_lower:
            defaults.append("#Startups")
        if "automation" in topic_lower:
            defaults.append("#Automation")
        if is_shorts:
            defaults.insert(0, "#Shorts")

        for hashtag in defaults:
            add_hashtag(hashtag)

        return normalized[:6]

    def _build_tags(
        self,
        job: VideoJob,
        usage_metrics: dict[str, Any],
        hashtags: list[str],
        is_shorts: bool,
    ) -> list[str]:
        base_tags = [
            str(tag).strip()
            for tag in (usage_metrics.get("metadata_tags") or [])
            if str(tag).strip()
        ]
        base_tags.extend(
            tag.strip() for tag in (job.topic or "").split() if tag.strip()
        )
        if is_shorts:
            base_tags.extend(["youtube shorts", "short form video", "viral shorts"])
        base_tags.extend(["ai news", "tech trends", "automation", "business strategy"])
        base_tags.extend(hashtag.lstrip("#") for hashtag in hashtags)

        deduped: list[str] = []
        seen: set[str] = set()
        for tag in base_tags:
            lowered = tag.lower()
            if lowered not in seen:
                seen.add(lowered)
                deduped.append(tag)
        return deduped[:15]

    @staticmethod
    def _is_shorts(job: VideoJob, usage_metrics: dict[str, Any]) -> bool:
        audio_duration = usage_metrics.get("audio_duration_seconds")
        if job.orientation != "portrait":
            return False
        if isinstance(audio_duration, (int, float)):
            return float(audio_duration) <= 59.5
        return job.duration_seconds <= 59

    @staticmethod
    def _build_video_url(video_id: str, is_shorts: bool) -> str:
        if is_shorts:
            return f"https://www.youtube.com/shorts/{video_id}"
        return f"https://www.youtube.com/watch?v={video_id}"

    def _build_web_flow(
        self, *, state: str | None = None, code_verifier: str | None = None
    ) -> Flow:
        client_payload = self._load_client_payload()
        flow = Flow.from_client_config(
            client_payload,
            scopes=self.SCOPES,
            state=state,
            code_verifier=code_verifier,
        )
        flow.redirect_uri = self._youtube_oauth_redirect_uri()
        return flow

    def _assert_oauth_ready_for_browser(self) -> None:
        client_payload = self._load_client_payload()
        client_type, client_info = self._get_client_info(client_payload)
        redirect_uri = self._youtube_oauth_redirect_uri()
        redirect_uris = client_info.get("redirect_uris") or []

        if client_type != "web":
            raise RuntimeError(
                "The dashboard OAuth bootstrap expects a Google OAuth Web application client. Replace client_secrets.json with a Web client that includes the backend callback URL."
            )

        if redirect_uris and redirect_uri not in redirect_uris:
            raise RuntimeError(
                f"Add this authorized redirect URI in Google Cloud: {redirect_uri}"
            )

    def _load_client_payload(self) -> dict[str, Any]:
        if not settings.youtube_client_secrets_path.exists():
            raise RuntimeError(
                f"Missing client secrets file at {settings.youtube_client_secrets_path}. Download it from Google Cloud and place it there."
            )

        client_payload = json.loads(
            settings.youtube_client_secrets_path.read_text(encoding="utf-8")
        )
        self._get_client_info(client_payload)
        return client_payload

    @staticmethod
    def _get_client_info(client_payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if client_payload.get("web"):
            return "web", client_payload["web"]
        if client_payload.get("installed"):
            return "installed", client_payload["installed"]
        raise RuntimeError(
            "client_secrets.json must contain either a 'web' or 'installed' OAuth client configuration."
        )

    def _youtube_oauth_redirect_uri(self) -> str:
        return f"{settings.backend_public_url.rstrip('/')}{settings.api_v1_prefix}/integrations/youtube/oauth/callback"

    @staticmethod
    def _lookup_stored_credential(
        db: Session, channel_label: str
    ) -> YouTubeCredential | None:
        return (
            db.query(YouTubeCredential)
            .filter(YouTubeCredential.channel_label == channel_label)
            .one_or_none()
        )

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.db_models import JobStatus


class ScenePayload(BaseModel):
    sentence: str
    visual_keyword: str
    start_seconds: float | None = None
    end_seconds: float | None = None


class VideoJobCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=255)
    target_audience: str | None = Field(default=None, max_length=255)
    duration_seconds: int = Field(default=60, ge=15, le=600)
    orientation: Literal["portrait", "landscape"] = "portrait"
    publish_privacy: Literal["public", "private", "unlisted"] = "public"


class BulkVideoJobCreate(BaseModel):
    niche: str = Field(min_length=3, max_length=255)
    target_audience: str | None = Field(default=None, max_length=255)
    duration_seconds: int = Field(default=60, ge=15, le=600)
    orientation: Literal["portrait", "landscape"] = "portrait"
    publish_privacy: Literal["public", "private", "unlisted"] = "public"
    videos_count: int = Field(default=5, ge=2, le=10)


class SourceRemixJobCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=255)
    target_audience: str | None = Field(default=None, max_length=255)
    duration_seconds: int = Field(default=59, ge=15, le=180)
    orientation: Literal["portrait", "landscape"] = "portrait"
    publish_privacy: Literal["public", "private", "unlisted"] = "public"
    shots_count: int = Field(default=5, ge=3, le=10)


class JobReviewDecision(BaseModel):
    approved: bool
    notes: str | None = Field(default=None, max_length=2000)


class YouTubeCredentialUpsert(BaseModel):
    channel_label: str = Field(default="default", min_length=1, max_length=255)
    refresh_token: str = Field(min_length=10)
    scopes_json: list[str] | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class AuthSessionRead(BaseModel):
    authenticated: bool
    username: str | None = None
    warning: str | None = None


class VideoJobSummaryRead(BaseModel):
    id: UUID
    topic: str
    target_audience: str | None
    duration_seconds: int
    orientation: str
    status: JobStatus
    quality_score: int | None
    publish_privacy: Literal["public", "private", "unlisted"] = "public"
    distribution_label: str = "Standard Video"
    batch_label: str | None = None
    batch_index: int | None = None
    youtube_url: str | None
    title: str | None
    critique_text: str | None
    manual_override: bool
    created_at: datetime
    updated_at: datetime
    scene_count: int = 0
    visual_asset_count: int = 0
    error_summary: str | None = None


class VideoJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic: str
    target_audience: str | None
    duration_seconds: int
    orientation: str
    status: JobStatus
    quality_score: int | None
    publish_privacy: Literal["public", "private", "unlisted"] = "public"
    distribution_label: str = "Standard Video"
    batch_label: str | None = None
    batch_index: int | None = None
    youtube_url: str | None
    youtube_video_id: str | None
    error_log: str | None
    title: str | None
    description: str | None
    script_text: str | None
    critique_text: str | None
    scenes_json: list[dict[str, Any]] | None
    visual_asset_manifest: list[dict[str, Any]] | None
    critique_json: dict[str, Any] | None
    artifact_paths: dict[str, Any] | None
    usage_metrics: dict[str, Any] | None
    manual_override: bool
    created_at: datetime
    updated_at: datetime


class VideoJobCollection(BaseModel):
    jobs: list[VideoJobSummaryRead]
    total_count: int
    page_size: int
    active_count: int
    blocked_count: int


class JobCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class JobActionResponse(BaseModel):
    job_id: UUID
    status: str
    message: str


class BulkQueuedJobRead(BaseModel):
    job_id: UUID
    topic: str
    target_audience: str | None
    status: JobStatus
    batch_index: int


class BulkJobCreateResponse(BaseModel):
    batch_id: str
    batch_label: str
    videos_count: int
    jobs: list[BulkQueuedJobRead]


class JobPublishRequest(BaseModel):
    channel_label: str = Field(min_length=1, max_length=255)


class BulkJobPublishRequest(BaseModel):
    job_ids: list[UUID]
    channel_label: str = Field(min_length=1, max_length=255)


class BulkJobActionResponse(BaseModel):
    jobs_processed: int
    status: str


class YouTubeChannelRead(BaseModel):
    id: int
    channel_label: str
    created_at: datetime
    updated_at: datetime


class YouTubeChannelList(BaseModel):
    channels: list[YouTubeChannelRead]


class CredentialResponse(BaseModel):
    channel_label: str
    status: str


class YouTubeConnectionStatus(BaseModel):
    channel_label: str
    connected: bool
    credential_source: Literal["database", "environment", "none"]
    has_client_secrets: bool
    authorization_ready: bool
    redirect_uri: str
    scopes_json: list[str] | None = None
    message: str

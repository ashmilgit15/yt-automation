import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RESEARCHING = "RESEARCHING"
    AUDIO = "AUDIO"
    VISUALS = "VISUALS"
    COMPOSING = "COMPOSING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    UPLOADING = "UPLOADING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED_BY_QUALITY_GATE = "BLOCKED_BY_QUALITY_GATE"
    CANCELLED = "CANCELLED"


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_audience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    orientation: Mapped[str] = mapped_column(
        String(32), nullable=False, default="portrait"
    )
    status: Mapped[JobStatus] = mapped_column(
        SqlEnum(JobStatus, name="video_job_status"),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )
    quality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    youtube_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    critique_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    scenes_json: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    visual_asset_manifest: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB, nullable=True
    )
    critique_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    artifact_paths: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    usage_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class YouTubeCredential(Base):
    __tablename__ = "youtube_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_label: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, default="default"
    )
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_uri: Mapped[str] = mapped_column(
        String(255), nullable=False, default="https://oauth2.googleapis.com/token"
    )
    scopes_json: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

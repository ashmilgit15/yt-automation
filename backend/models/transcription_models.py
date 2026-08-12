import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class PlaylistStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"


class TranscriptStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACQUIRING = "ACQUIRING"
    TRANSCRIBING = "TRANSCRIBING"
    EXPORTING = "EXPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PlaylistBatch(Base):
    __tablename__ = "playlist_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PlaylistStatus] = mapped_column(
        SqlEnum(PlaylistStatus, name="playlist_batch_status"),
        nullable=False,
        default=PlaylistStatus.QUEUED,
        index=True,
    )
    total_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class TranscriptJob(Base):
    __tablename__ = "transcript_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("playlist_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    video_url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[TranscriptStatus] = mapped_column(
        SqlEnum(TranscriptStatus, name="transcript_job_status"),
        nullable=False,
        default=TranscriptStatus.PENDING,
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language: Mapped[str | None] = mapped_column(String(24), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    artifact_paths: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

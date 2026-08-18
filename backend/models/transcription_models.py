import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base


class PlaylistStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


class TranscriptStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACQUIRING = "ACQUIRING"
    TRANSCRIBING = "TRANSCRIBING"
    CLEANING = "CLEANING"
    SUMMARIZING = "SUMMARIZING"
    EXPORTING = "EXPORTING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PlaylistBatch(Base):
    __tablename__ = "playlist_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="local_whisper")
    status: Mapped[PlaylistStatus] = mapped_column(
        SqlEnum(PlaylistStatus, name="playlist_batch_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PlaylistStatus.QUEUED,
        index=True,
    )
    total_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_videos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enable_ai_cleanup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_ai_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    batch_summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    @property
    def master_summary(self) -> str | None:
        return self.batch_summary_markdown

    @master_summary.setter
    def master_summary(self, value: str | None) -> None:
        self.batch_summary_markdown = value


class TranscriptJob(Base):
    __tablename__ = "transcript_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    playlist_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("playlist_batches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    video_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    video_url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="local_whisper")
    status: Mapped[TranscriptStatus] = mapped_column(
        SqlEnum(TranscriptStatus, name="transcript_job_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TranscriptStatus.PENDING,
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stage_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    language: Mapped[str | None] = mapped_column(String(24), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True, default="transcribe")
    enable_ai_cleanup: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_ai_summary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    clean_transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    clean_segments_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_paths: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

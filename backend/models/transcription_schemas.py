from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.models.transcription_models import PlaylistStatus, TranscriptStatus


class PlaylistAnalysisRequest(BaseModel):
    playlist_url: str = Field(min_length=20, max_length=500)


class PlaylistVideoRead(BaseModel):
    video_id: str
    title: str
    channel_title: str | None = None
    duration_seconds: int | None = None
    thumbnail_url: str | None = None
    position: int


class PlaylistAnalysisRead(BaseModel):
    playlist_id: str
    playlist_url: str
    title: str | None = None
    videos: list[PlaylistVideoRead]


class PlaylistCreateRequest(PlaylistAnalysisRequest):
    selected_video_ids: list[str] = Field(min_length=1, max_length=200)
    authorised_to_process: Literal[True]
    engine: str = Field(default="local_whisper")
    language_code: str = Field(default="unknown")
    mode: str = Field(default="transcribe")
    enable_ai_cleanup: bool = Field(default=False)
    enable_ai_summary: bool = Field(default=False)


class SingleVideoCreateRequest(BaseModel):
    video_url: str = Field(min_length=10, max_length=500)
    authorised_to_process: Literal[True]
    engine: str = Field(default="local_whisper")
    language_code: str = Field(default="unknown")
    mode: str = Field(default="transcribe")
    enable_ai_cleanup: bool = Field(default=False)
    enable_ai_summary: bool = Field(default=False)


class ChapterItem(BaseModel):
    start_seconds: float
    timestamp_label: str
    title: str
    summary: str


class TranscriptSummaryData(BaseModel):
    executive_summary: str | None = None
    key_highlights: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    chapters: list[ChapterItem] = Field(default_factory=list)
    key_quotes: list[str] = Field(default_factory=list)
    sentiment_tone: str | None = None


class TranscriptJobRead(PlaylistVideoRead):
    id: UUID
    playlist_batch_id: UUID | None = None
    engine: str = "local_whisper"
    status: TranscriptStatus
    progress: int
    stage_detail: str | None = None
    language: str | None = None
    mode: str | None = "transcribe"
    enable_ai_cleanup: bool = False
    enable_ai_summary: bool = False
    transcript_text: str | None = None
    segments: list[dict[str, Any]] | None = None
    clean_transcript_text: str | None = None
    clean_segments: list[dict[str, Any]] | None = None
    summary_json: dict[str, Any] | None = None
    summary_markdown: str | None = None
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class PlaylistBatchRead(BaseModel):
    id: UUID
    playlist_id: str
    source_url: str
    title: str | None = None
    engine: str = "local_whisper"
    status: PlaylistStatus
    total_videos: int
    completed_videos: int
    failed_videos: int
    enable_ai_cleanup: bool = False
    enable_ai_summary: bool = False
    batch_summary_markdown: str | None = None
    created_at: datetime
    updated_at: datetime
    jobs: list[TranscriptJobRead]


class PlaylistBatchSummaryRead(BaseModel):
    id: UUID
    playlist_id: str
    source_url: str
    title: str | None = None
    engine: str = "local_whisper"
    status: PlaylistStatus
    total_videos: int
    completed_videos: int
    failed_videos: int
    enable_ai_cleanup: bool = False
    enable_ai_summary: bool = False
    created_at: datetime
    updated_at: datetime

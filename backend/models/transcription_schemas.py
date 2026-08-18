from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl

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


class SingleVideoCreateRequest(BaseModel):
    video_url: str = Field(min_length=10, max_length=500)
    authorised_to_process: Literal[True]
    engine: str = Field(default="local_whisper")
    language_code: str = Field(default="unknown")
    mode: str = Field(default="transcribe")


class TranscriptJobRead(PlaylistVideoRead):
    id: UUID
    playlist_batch_id: UUID | None = None
    engine: str = "local_whisper"
    status: TranscriptStatus
    progress: int
    stage_detail: str | None = None
    language: str | None = None
    mode: str | None = "transcribe"
    transcript_text: str | None = None
    segments: list[dict[str, object]] | None = None
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
    created_at: datetime
    updated_at: datetime

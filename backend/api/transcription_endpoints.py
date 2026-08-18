from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.api.dependencies import rate_limit, require_operator
from backend.core.database import get_db
from backend.models.transcription_models import (
    PlaylistBatch,
    PlaylistStatus,
    TranscriptJob,
    TranscriptStatus,
)
from backend.models.transcription_schemas import (
    PlaylistAnalysisRead,
    PlaylistAnalysisRequest,
    PlaylistBatchRead,
    PlaylistBatchSummaryRead,
    PlaylistCreateRequest,
    PlaylistVideoRead,
    SingleVideoCreateRequest,
    TranscriptJobRead,
)
from backend.services.youtube_playlist import YouTubePlaylistService
from backend.worker.tasks import transcribe_playlist_item

router = APIRouter(tags=["bulk-transcription"])


def _job_read(job: TranscriptJob, *, include_transcript: bool = True) -> TranscriptJobRead:
    return TranscriptJobRead(
        id=job.id,
        playlist_batch_id=job.playlist_batch_id,
        video_id=job.video_id,
        title=job.title,
        channel_title=job.channel_title,
        duration_seconds=job.duration_seconds,
        thumbnail_url=job.thumbnail_url,
        position=job.position,
        engine=job.engine or "local_whisper",
        status=job.status,
        progress=job.progress,
        stage_detail=job.stage_detail,
        language=job.language,
        mode=job.mode or "transcribe",
        transcript_text=job.transcript_text if include_transcript else None,
        segments=job.segments_json if include_transcript else None,
        error_summary=(job.error_log or "")[-300:] or None,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _batch_read(batch: PlaylistBatch, jobs: list[TranscriptJob]) -> PlaylistBatchRead:
    return PlaylistBatchRead(
        id=batch.id,
        playlist_id=batch.playlist_id,
        source_url=batch.source_url,
        title=batch.title,
        engine=batch.engine or "local_whisper",
        status=batch.status,
        total_videos=batch.total_videos,
        completed_videos=batch.completed_videos,
        failed_videos=batch.failed_videos,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        jobs=[_job_read(job) for job in jobs],
    )


def _load_batch(db: Session, batch_id: UUID) -> tuple[PlaylistBatch, list[TranscriptJob]]:
    batch = db.get(PlaylistBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist batch not found.")
    jobs = list(
        db.scalars(
            select(TranscriptJob)
            .where(TranscriptJob.playlist_batch_id == batch.id)
            .order_by(TranscriptJob.position.asc())
        )
    )
    return batch, jobs


@router.get("/playlists", response_model=list[PlaylistBatchSummaryRead])
def list_playlist_batches(
    limit: int = 15,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("playlist-list", 60, 60)),
) -> list[PlaylistBatchSummaryRead]:
    """Lists recent playlist batches for history & active batch recovery."""
    batches = list(
        db.scalars(
            select(PlaylistBatch)
            .order_by(desc(PlaylistBatch.created_at))
            .limit(min(max(limit, 1), 50))
        )
    )
    return [
        PlaylistBatchSummaryRead(
            id=b.id,
            playlist_id=b.playlist_id,
            source_url=b.source_url,
            title=b.title,
            engine=b.engine or "local_whisper",
            status=b.status,
            total_videos=b.total_videos,
            completed_videos=b.completed_videos,
            failed_videos=b.failed_videos,
            created_at=b.created_at,
            updated_at=b.updated_at,
        )
        for b in batches
    ]


@router.post("/playlists/analyze", response_model=PlaylistAnalysisRead)
def analyse_playlist(
    payload: PlaylistAnalysisRequest,
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("playlist-analyse", 20, 60)),
) -> PlaylistAnalysisRead:
    try:
        analysis = YouTubePlaylistService().analyse(payload.playlist_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PlaylistAnalysisRead(
        playlist_id=str(analysis["playlist_id"]),
        playlist_url=str(analysis["playlist_url"]),
        title=analysis.get("title") if isinstance(analysis.get("title"), str) else None,
        videos=[PlaylistVideoRead(**item) for item in analysis["videos"]],
    )


@router.post("/playlists", response_model=PlaylistBatchRead, status_code=status.HTTP_202_ACCEPTED)
def create_playlist_batch(
    payload: PlaylistCreateRequest,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("playlist-create", 10, 60)),
) -> PlaylistBatchRead:
    try:
        analysis = YouTubePlaylistService().analyse(payload.playlist_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    selected_ids = set(payload.selected_video_ids)
    selected_videos = [video for video in analysis["videos"] if str(video["video_id"]) in selected_ids]
    if not selected_videos:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one video from the playlist preview.")

    engine_choice = payload.engine.strip() if payload.engine else "local_whisper"
    lang_choice = payload.language_code.strip() if payload.language_code else "unknown"
    mode_choice = payload.mode.strip() if payload.mode else "transcribe"

    batch = PlaylistBatch(
        playlist_id=str(analysis["playlist_id"]),
        source_url=payload.playlist_url,
        title=analysis.get("title") if isinstance(analysis.get("title"), str) else None,
        engine=engine_choice,
        status=PlaylistStatus.QUEUED,
        total_videos=len(selected_videos),
    )
    db.add(batch)
    db.flush()

    jobs: list[TranscriptJob] = []
    for video in selected_videos:
        job = TranscriptJob(
            playlist_batch_id=batch.id,
            video_id=str(video["video_id"]),
            video_url=f"https://www.youtube.com/watch?v={video['video_id']}",
            title=str(video["title"]),
            channel_title=str(video["channel_title"]) if video.get("channel_title") else None,
            duration_seconds=int(video["duration_seconds"]) if video.get("duration_seconds") is not None else None,
            thumbnail_url=str(video["thumbnail_url"]) if video.get("thumbnail_url") else None,
            position=int(video["position"]),
            engine=engine_choice,
            language=lang_choice,
            mode=mode_choice,
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)
        transcribe_playlist_item.delay(str(job.id))
    db.refresh(batch)
    return _batch_read(batch, jobs)


@router.post("/transcripts/single", response_model=TranscriptJobRead, status_code=status.HTTP_202_ACCEPTED)
def create_single_transcript(
    payload: SingleVideoCreateRequest,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("single-transcript-create", 20, 60)),
) -> TranscriptJobRead:
    """Directly transcribes a single YouTube video URL without requiring a playlist."""
    video_url = payload.video_url.strip()
    video_id = "video"
    if "watch?v=" in video_url:
        video_id = video_url.split("watch?v=")[1].split("&")[0]
    elif "youtu.be/" in video_url:
        video_id = video_url.split("youtu.be/")[1].split("?")[0]

    job = TranscriptJob(
        playlist_batch_id=None,
        video_id=video_id,
        video_url=video_url,
        title=f"YouTube Video ({video_id})",
        engine=payload.engine or "local_whisper",
        language=payload.language_code or "unknown",
        mode=payload.mode or "transcribe",
        status=TranscriptStatus.PENDING,
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    transcribe_playlist_item.delay(str(job.id))
    return _job_read(job)


@router.get("/playlists/{batch_id}", response_model=PlaylistBatchRead)
def read_playlist_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("playlist-read", 120, 60)),
) -> PlaylistBatchRead:
    batch, jobs = _load_batch(db, batch_id)
    return _batch_read(batch, jobs)


@router.get("/transcripts/{job_id}", response_model=TranscriptJobRead)
def read_transcript_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("transcript-read", 120, 60)),
) -> TranscriptJobRead:
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript job not found.")
    return _job_read(job)


@router.post("/transcripts/{job_id}/retry", response_model=TranscriptJobRead, status_code=status.HTTP_202_ACCEPTED)
def retry_transcript_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("transcript-retry", 12, 60)),
) -> TranscriptJobRead:
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript job not found.")
    if job.status not in {TranscriptStatus.FAILED, TranscriptStatus.COMPLETED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This job is already running.")
    job.status = TranscriptStatus.PENDING
    job.progress = 0
    job.stage_detail = "Queued for retry..."
    job.error_log = None
    db.commit()
    db.refresh(job)
    transcribe_playlist_item.delay(str(job.id))
    return _job_read(job)


@router.get("/transcripts/{job_id}/export/{export_format}")
def export_transcript(
    job_id: UUID,
    export_format: str,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("transcript-export", 60, 60)),
) -> FileResponse:
    if export_format not in {"txt", "srt", "vtt", "json"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported export format.")
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript job not found.")
    path_value = (job.artifact_paths or {}).get(export_format)
    path = Path(path_value) if path_value else None
    if not path or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This export is not ready yet.")
    media_types = {
        "txt": "text/plain; charset=utf-8",
        "srt": "application/x-subrip; charset=utf-8",
        "vtt": "text/vtt; charset=utf-8",
        "json": "application/json; charset=utf-8",
    }
    return FileResponse(
        path,
        media_type=media_types[export_format],
        filename=f"{job.video_id}.{export_format}",
        headers={"Content-Disposition": f'attachment; filename="{job.video_id}.{export_format}"'},
    )

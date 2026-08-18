from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse, Response
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
from backend.worker.tasks import (
    run_ai_cleaner_task,
    run_ai_summarizer_task,
    transcribe_playlist_item,
)

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
        enable_ai_cleanup=job.enable_ai_cleanup,
        enable_ai_summary=job.enable_ai_summary,
        transcript_text=job.transcript_text if include_transcript else None,
        segments=job.segments_json if include_transcript else None,
        clean_transcript_text=job.clean_transcript_text if include_transcript else None,
        clean_segments=job.clean_segments_json if include_transcript else None,
        summary_json=job.summary_json if include_transcript else None,
        summary_markdown=job.summary_markdown if include_transcript else None,
        error_summary=(job.error_log or "")[-300:] or None,
        failure_type=job.failure_type,
        is_retryable=job.is_retryable if job.is_retryable is not None else True,
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
        enable_ai_cleanup=batch.enable_ai_cleanup,
        enable_ai_summary=batch.enable_ai_summary,
        batch_summary_markdown=batch.batch_summary_markdown,
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
    limit: int = 30,
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
            enable_ai_cleanup=b.enable_ai_cleanup,
            enable_ai_summary=b.enable_ai_summary,
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
        enable_ai_cleanup=payload.enable_ai_cleanup,
        enable_ai_summary=payload.enable_ai_summary,
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
            enable_ai_cleanup=payload.enable_ai_cleanup,
            enable_ai_summary=payload.enable_ai_summary,
            status=TranscriptStatus.PENDING,
        )
        db.add(job)
        jobs.append(job)
    db.commit()
    for job in jobs:
        db.refresh(job)
        transcribe_playlist_item.delay(str(job.id))
    db.refresh(batch)
    return _batch_read(batch, jobs)


@router.get("/transcripts/recent", response_model=list[TranscriptJobRead])
def list_recent_transcripts(
    limit: int = 50,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("transcripts-recent", 120, 60)),
) -> list[TranscriptJobRead]:
    """Lists all recent transcript jobs (standalone and batch items) for history tracking."""
    jobs = list(
        db.scalars(
            select(TranscriptJob)
            .order_by(desc(TranscriptJob.created_at))
            .limit(min(max(limit, 1), 100))
        )
    )
    return [_job_read(job, include_transcript=False) for job in jobs]


@router.post("/transcripts/single", response_model=TranscriptJobRead, status_code=status.HTTP_202_ACCEPTED)
def create_single_transcript(
    payload: SingleVideoCreateRequest,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("single-transcript-create", 20, 60)),
) -> TranscriptJobRead:
    """Directly transcribes a single YouTube video URL with optional AI cleanup and summary."""
    video_url = payload.video_url.strip()
    title = "YouTube Video"
    video_id = "video"
    channel_title = None
    duration_seconds = None
    thumbnail_url = None

    try:
        analysis = YouTubePlaylistService().analyse(video_url)
        if analysis and analysis.get("videos"):
            first = analysis["videos"][0]
            if isinstance(first, dict):
                video_id = str(first.get("video_id") or video_id)
                title = str(first.get("title") or title)
                channel_title = str(first.get("channel_title")) if first.get("channel_title") else None
                duration_seconds = first.get("duration_seconds")
                thumbnail_url = first.get("thumbnail_url")
    except Exception:
        if "watch?v=" in video_url:
            video_id = video_url.split("watch?v=")[1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[1].split("?")[0]
        title = f"YouTube Video ({video_id})"

    job = TranscriptJob(
        playlist_batch_id=None,
        video_id=video_id,
        video_url=video_url,
        title=title,
        channel_title=channel_title,
        duration_seconds=duration_seconds,
        thumbnail_url=thumbnail_url,
        engine=payload.engine or "local_whisper",
        language=payload.language_code or "unknown",
        mode=payload.mode or "transcribe",
        enable_ai_cleanup=payload.enable_ai_cleanup,
        enable_ai_summary=payload.enable_ai_summary,
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


# --- PAUSE, RESUME, CANCEL CONTROLS ---

@router.post("/transcripts/{job_id}/pause", response_model=TranscriptJobRead)
def pause_transcript_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> TranscriptJobRead:
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.status in {TranscriptStatus.COMPLETED, TranscriptStatus.CANCELLED, TranscriptStatus.FAILED}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job cannot be paused in its current state.")
    job.status = TranscriptStatus.PAUSED
    job.stage_detail = "Paused by user."
    db.commit()
    db.refresh(job)
    return _job_read(job)


@router.post("/transcripts/{job_id}/resume", response_model=TranscriptJobRead, status_code=status.HTTP_202_ACCEPTED)
def resume_transcript_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> TranscriptJobRead:
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.status != TranscriptStatus.PAUSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not paused.")
    job.status = TranscriptStatus.PENDING
    job.stage_detail = "Resuming task..."
    db.commit()
    db.refresh(job)
    transcribe_playlist_item.delay(str(job.id))
    return _job_read(job)


@router.post("/transcripts/{job_id}/cancel", response_model=TranscriptJobRead)
def cancel_transcript_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> TranscriptJobRead:
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    job.status = TranscriptStatus.CANCELLED
    job.stage_detail = "Cancelled by user."
    db.commit()
    db.refresh(job)
    return _job_read(job)


@router.post("/playlists/{batch_id}/pause", response_model=PlaylistBatchRead)
def pause_playlist_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> PlaylistBatchRead:
    batch, jobs = _load_batch(db, batch_id)
    batch.status = PlaylistStatus.PAUSED
    for job in jobs:
        if job.status not in {TranscriptStatus.COMPLETED, TranscriptStatus.FAILED, TranscriptStatus.CANCELLED}:
            job.status = TranscriptStatus.PAUSED
            job.stage_detail = "Paused with batch."
    db.commit()
    db.refresh(batch)
    return _batch_read(batch, jobs)


@router.post("/playlists/{batch_id}/resume", response_model=PlaylistBatchRead, status_code=status.HTTP_202_ACCEPTED)
def resume_playlist_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> PlaylistBatchRead:
    batch, jobs = _load_batch(db, batch_id)
    batch.status = PlaylistStatus.PROCESSING
    for job in jobs:
        if job.status == TranscriptStatus.PAUSED:
            job.status = TranscriptStatus.PENDING
            job.stage_detail = "Resuming batch item..."
            transcribe_playlist_item.delay(str(job.id))
    db.commit()
    db.refresh(batch)
    return _batch_read(batch, jobs)


@router.post("/playlists/{batch_id}/cancel", response_model=PlaylistBatchRead)
def cancel_playlist_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> PlaylistBatchRead:
    batch, jobs = _load_batch(db, batch_id)
    batch.status = PlaylistStatus.CANCELLED
    for job in jobs:
        if job.status not in {TranscriptStatus.COMPLETED, TranscriptStatus.FAILED}:
            job.status = TranscriptStatus.CANCELLED
            job.stage_detail = "Cancelled with batch."
    db.commit()
    db.refresh(batch)
    return _batch_read(batch, jobs)


@router.post("/playlists/{batch_id}/retry-failed", response_model=PlaylistBatchRead, status_code=status.HTTP_202_ACCEPTED)
def retry_failed_playlist_batch_items(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> PlaylistBatchRead:
    """Retries transient failed video transcription jobs in the playlist batch, skipping permanent failures."""
    batch, jobs = _load_batch(db, batch_id)
    failed_jobs = [job for job in jobs if job.status == TranscriptStatus.FAILED]

    if not failed_jobs:
        return _batch_read(batch, jobs)

    retryable_jobs = [job for job in failed_jobs if job.is_retryable is not False]
    if not retryable_jobs:
        # All failed jobs are permanent non-retryable errors (e.g. DRM, unavailable)
        return _batch_read(batch, jobs)

    batch.status = PlaylistStatus.PROCESSING
    batch.failed_videos = max(0, batch.failed_videos - len(retryable_jobs))

    for job in retryable_jobs:
        job.status = TranscriptStatus.PENDING
        job.progress = 0
        job.stage_detail = "Queued for retry..."
        job.failure_type = None
        job.is_retryable = True
        job.error_log = None
        db.add(job)
        transcribe_playlist_item.delay(str(job.id))

    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_read(batch, jobs)



# --- ON-DEMAND AI AGENT ENDPOINTS ---

@router.post("/transcripts/{job_id}/run-cleaner", response_model=TranscriptJobRead, status_code=status.HTTP_202_ACCEPTED)
def trigger_ai_cleaner(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> TranscriptJobRead:
    """Runs the AI Cleanup Agent on an existing completed transcript."""
    job = db.get(TranscriptJob, job_id)
    if not job or not job.transcript_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transcript text is not available for cleanup.")
    run_ai_cleaner_task.delay(str(job.id))
    job.status = TranscriptStatus.CLEANING
    job.stage_detail = "AI Cleanup Agent queued..."
    db.commit()
    db.refresh(job)
    return _job_read(job)


@router.post("/transcripts/{job_id}/run-summarizer", response_model=TranscriptJobRead, status_code=status.HTTP_202_ACCEPTED)
def trigger_ai_summarizer(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> TranscriptJobRead:
    """Runs the AI Summarizer Agent on an existing completed transcript."""
    job = db.get(TranscriptJob, job_id)
    if not job or (not job.transcript_text and not job.clean_transcript_text):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transcript text is not available for summarization.")
    run_ai_summarizer_task.delay(str(job.id))
    job.status = TranscriptStatus.SUMMARIZING
    job.stage_detail = "AI Summarizer Agent queued..."
    db.commit()
    db.refresh(job)
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
    if job.status not in {TranscriptStatus.FAILED, TranscriptStatus.COMPLETED, TranscriptStatus.CANCELLED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This job is already running.")
    job.status = TranscriptStatus.PENDING
    job.progress = 0
    job.stage_detail = "Queued for retry..."
    job.failure_type = None
    job.is_retryable = True
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
) -> Response:
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript job not found.")

    # 1. AI Summary Markdown export
    if export_format == "summary_md":
        content = job.summary_markdown or f"# Summary: {job.title}\n\nNo AI summary generated."
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job.video_id}_summary.md"'},
        )

    # 2. AI Summary JSON export
    if export_format == "summary_json":
        content = json.dumps(job.summary_json or {}, indent=2, ensure_ascii=False)
        return Response(
            content=content,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job.video_id}_summary.json"'},
        )

    # 3. Clean Text export
    if export_format == "clean_txt":
        content = job.clean_transcript_text or job.transcript_text or ""
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{job.video_id}_cleaned.txt"'},
        )

    # 4. Standard file exports (txt, srt, vtt, json)
    if export_format not in {"txt", "srt", "vtt", "json"}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported export format.")

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


@router.get("/playlists/{batch_id}/export/zip")
def export_playlist_zip(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
    __: None = Depends(rate_limit("playlist-export-zip", 30, 60)),
) -> Response:
    """Packages all completed transcripts in the playlist batch into a zip archive with clean titles."""
    import io
    import re
    import unicodedata
    import urllib.parse
    import zipfile
    from backend.services.subtitles import build_srt, build_vtt

    batch, jobs = _load_batch(db, batch_id)

    def _sanitize(text: str) -> str:
        s = re.sub(r'[\x00-\x1f\x7f\\/*?:"<>|]', "", text or "")
        s = re.sub(r"\s+", " ", s).strip(". ")
        s = s[:90].rstrip(". ")
        return s if s else "video"

    def _has_job_content(j: TranscriptJob) -> bool:
        if (
            (j.transcript_text and j.transcript_text.strip())
            or (j.clean_transcript_text and j.clean_transcript_text.strip())
            or (j.summary_markdown and j.summary_markdown.strip())
            or (j.segments_json and len(j.segments_json) > 0)
            or (j.clean_segments_json and len(j.clean_segments_json) > 0)
        ):
            return True
        if j.artifact_paths:
            for key in ("txt", "clean_txt", "summary_md", "srt", "vtt"):
                p = j.artifact_paths.get(key)
                if p and Path(p).is_file():
                    return True
        return False

    completed_jobs = [j for j in jobs if _has_job_content(j)]

    if not completed_jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No completed transcripts available to export",
        )

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Master summary if available
        master_summary = batch.master_summary or batch.batch_summary_markdown
        if master_summary and master_summary.strip():
            zf.writestr(
                "00_MASTER_PLAYLIST_SUMMARY.md",
                (master_summary.strip() + "\n").encode("utf-8"),
            )

        used_bases: set[str] = set()
        for idx, job in enumerate(jobs):
            if not _has_job_content(job):
                continue

            pos_num = (job.position + 1) if (job.position is not None and job.position >= 0) else (idx + 1)
            safe_title = _sanitize(job.title or job.video_id)
            base_candidate = f"{pos_num:02d} - {safe_title}"
            file_base = base_candidate
            if file_base in used_bases:
                file_base = f"{base_candidate}_{str(job.video_id)[:8]}"
            used_bases.add(file_base)

            # 1. Clean Transcript text (if AI cleanup was enabled / clean transcript exists)
            clean_text = job.clean_transcript_text
            if not (clean_text and clean_text.strip()) and job.artifact_paths and job.artifact_paths.get("clean_txt"):
                art_p = Path(job.artifact_paths["clean_txt"])
                if art_p.is_file():
                    try:
                        clean_text = art_p.read_text(encoding="utf-8")
                    except Exception:
                        pass
            if clean_text and clean_text.strip():
                zf.writestr(
                    f"Clean_Transcripts/{file_base} (Clean).txt",
                    (clean_text.strip() + "\n").encode("utf-8"),
                )

            # 2. Main / Raw Transcript text
            raw_text = job.transcript_text
            if not (raw_text and raw_text.strip()) and job.artifact_paths and job.artifact_paths.get("txt"):
                art_p = Path(job.artifact_paths["txt"])
                if art_p.is_file():
                    try:
                        raw_text = art_p.read_text(encoding="utf-8")
                    except Exception:
                        pass
            if not (raw_text and raw_text.strip()) and job.segments_json:
                seg_texts = [
                    s.get("text", "").strip()
                    for s in job.segments_json
                    if isinstance(s, dict) and s.get("text")
                ]
                if seg_texts:
                    raw_text = " ".join(seg_texts)
            if raw_text and raw_text.strip():
                zf.writestr(
                    f"Transcripts/{file_base}.txt",
                    (raw_text.strip() + "\n").encode("utf-8"),
                )

            # 3. AI Summary Markdown (if AI summarization was enabled / summary exists)
            sum_text = job.summary_markdown
            if not (sum_text and sum_text.strip()) and job.artifact_paths and job.artifact_paths.get("summary_md"):
                art_p = Path(job.artifact_paths["summary_md"])
                if art_p.is_file():
                    try:
                        sum_text = art_p.read_text(encoding="utf-8")
                    except Exception:
                        pass
            if sum_text and sum_text.strip():
                zf.writestr(
                    f"Summaries/{file_base} - Summary.md",
                    (sum_text.strip() + "\n").encode("utf-8"),
                )

            # 4. Subtitles SRT (.srt)
            srt_bytes: bytes | None = None
            if job.artifact_paths and job.artifact_paths.get("srt"):
                art_path = Path(job.artifact_paths["srt"])
                if art_path.is_file():
                    try:
                        srt_bytes = art_path.read_bytes()
                    except Exception:
                        pass
            if (not srt_bytes) and (job.clean_segments_json or job.segments_json):
                segments = job.clean_segments_json or job.segments_json
                if segments:
                    try:
                        srt_content = build_srt(segments).strip()
                        if srt_content:
                            srt_bytes = (srt_content + "\n").encode("utf-8")
                    except Exception:
                        pass
            if srt_bytes and srt_bytes.strip():
                zf.writestr(f"Subtitles_SRT/{file_base}.srt", srt_bytes)

            # 5. Subtitles VTT (.vtt)
            vtt_bytes: bytes | None = None
            if job.artifact_paths and job.artifact_paths.get("vtt"):
                art_path = Path(job.artifact_paths["vtt"])
                if art_path.is_file():
                    try:
                        vtt_bytes = art_path.read_bytes()
                    except Exception:
                        pass
            if (not vtt_bytes) and (job.clean_segments_json or job.segments_json):
                segments = job.clean_segments_json or job.segments_json
                if segments:
                    try:
                        vtt_content = build_vtt(segments).strip()
                        if vtt_content and vtt_content != "WEBVTT":
                            vtt_bytes = (vtt_content + "\n").encode("utf-8")
                    except Exception:
                        pass
            if vtt_bytes and vtt_bytes.strip() and vtt_bytes.strip() != b"WEBVTT":
                zf.writestr(f"Subtitles_VTT/{file_base}.vtt", vtt_bytes)

    zip_bytes = zip_buffer.getvalue()

    safe_batch_title = _sanitize(batch.title or f"playlist_{batch.playlist_id}")
    if safe_batch_title == "video" or not safe_batch_title:
        safe_batch_title = "Playlist"

    ascii_title = unicodedata.normalize("NFKD", safe_batch_title).encode("ascii", "ignore").decode("ascii")
    ascii_title = re.sub(r'[\x00-\x1f\x7f\\/*?:"<>|]', "", ascii_title).strip(". ") or "Playlist"

    ascii_filename = f"{ascii_title[:80]} Transcripts.zip"
    encoded_filename = urllib.parse.quote(f"{safe_batch_title} Transcripts.zip")

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}',
            "Content-Type": "application/zip",
        },
    )


@router.delete("/transcripts/{job_id}", status_code=status.HTTP_200_OK)
def delete_transcript_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> dict[str, Any]:
    """Deletes a transcript job and its local artifacts."""
    job = db.get(TranscriptJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    batch = db.get(PlaylistBatch, job.playlist_batch_id) if job.playlist_batch_id else None

    # Remove directory artifacts if exists
    try:
        import shutil
        from backend.services.utils import get_job_directory
        job_dir = get_job_directory(str(job.id))
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
    except Exception:
        pass

    db.delete(job)
    db.commit()

    if batch:
        from backend.worker.tasks import _refresh_playlist_progress
        _refresh_playlist_progress(db, batch)

    return {"message": "Job deleted successfully", "job_id": str(job_id)}


@router.delete("/playlists/{batch_id}", status_code=status.HTTP_200_OK)
def delete_playlist_batch(
    batch_id: UUID,
    db: Session = Depends(get_db),
    _: object = Depends(require_operator),
) -> dict[str, Any]:
    """Deletes an entire playlist batch and its associated jobs and artifacts."""
    batch, jobs = _load_batch(db, batch_id)

    import shutil
    from backend.services.utils import get_job_directory
    for job in jobs:
        try:
            job_dir = get_job_directory(str(job.id))
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass

    db.delete(batch)
    db.commit()
    return {"message": "Playlist batch deleted successfully", "batch_id": str(batch_id)}


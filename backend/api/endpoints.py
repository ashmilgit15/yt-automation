from __future__ import annotations

import secrets
import shutil
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.dependencies import get_auth_session, rate_limit, require_operator
from backend.core.config import get_settings
from backend.core.database import get_db
from backend.core.security import constant_time_equals, encrypt_secret
from backend.models.db_models import JobStatus, VideoJob, YouTubeCredential
from backend.models.schemas import (
    AuthSessionRead,
    BulkJobActionResponse,
    BulkJobCreateResponse,
    BulkJobPublishRequest,
    JobPublishRequest,
    BulkQueuedJobRead,
    BulkVideoJobCreate,
    CredentialResponse,
    JobActionResponse,
    JobCreateResponse,
    JobReviewDecision,
    LoginRequest,
    SourceRemixJobCreate,
    VideoJobCollection,
    VideoJobCreate,
    VideoJobRead,
    VideoJobSummaryRead,
    YouTubeChannelList,
    YouTubeChannelRead,
    YouTubeConnectionStatus,
    YouTubeCredentialUpsert,
)
from backend.services.researcher import ResearcherService
from backend.services.publisher import PublisherService
from backend.worker.tasks import (
    generate_video_pipeline,
    generate_source_remix_pipeline,
    resume_failed_pipeline,
    execute_publish_pipeline,
)


router = APIRouter()
settings = get_settings()


def _safe_error_summary(error_log: str | None) -> str | None:
    if not error_log:
        return None
    lines = [line.strip() for line in error_log.splitlines() if line.strip()]
    if not lines:
        return None

    for line in reversed(lines):
        if "Error" in line or "Exception" in line or "Traceback" in line:
            return line[:220]

    return lines[-1][:220]


def _to_job_summary(job: VideoJob) -> VideoJobSummaryRead:
    usage_metrics = dict(job.usage_metrics or {})
    publish_privacy = str(
        usage_metrics.get("publish_privacy") or settings.youtube_privacy_status
    )
    distribution_label = str(
        usage_metrics.get("distribution_label")
        or ("YouTube Shorts" if job.orientation == "portrait" else "Standard Video")
    )
    batch_label = (
        str(usage_metrics.get("batch_label"))
        if usage_metrics.get("batch_label")
        else None
    )
    batch_index = (
        int(usage_metrics.get("batch_index"))
        if usage_metrics.get("batch_index")
        else None
    )
    return VideoJobSummaryRead(
        id=job.id,
        topic=job.topic,
        target_audience=job.target_audience,
        duration_seconds=job.duration_seconds,
        orientation=job.orientation,
        status=job.status,
        quality_score=job.quality_score,
        publish_privacy=publish_privacy,
        distribution_label=distribution_label,
        batch_label=batch_label,
        batch_index=batch_index,
        youtube_url=job.youtube_url,
        title=job.title,
        critique_text=job.critique_text,
        manual_override=job.manual_override,
        created_at=job.created_at,
        updated_at=job.updated_at,
        scene_count=len(job.scenes_json or []),
        visual_asset_count=len(job.visual_asset_manifest or []),
        error_summary=_safe_error_summary(job.error_log),
    )


def _to_job_detail(job: VideoJob) -> VideoJobRead:
    detail_payload = VideoJobRead.model_validate(job)
    usage_metrics = dict(job.usage_metrics or {})
    detail_payload.publish_privacy = str(
        usage_metrics.get("publish_privacy") or settings.youtube_privacy_status
    )
    detail_payload.distribution_label = str(
        usage_metrics.get("distribution_label")
        or ("YouTube Shorts" if job.orientation == "portrait" else "Standard Video")
    )
    detail_payload.batch_label = (
        str(usage_metrics.get("batch_label"))
        if usage_metrics.get("batch_label")
        else None
    )
    detail_payload.batch_index = (
        int(usage_metrics.get("batch_index"))
        if usage_metrics.get("batch_index")
        else None
    )
    return detail_payload


def _spawn_new_job(
    db: Session,
    *,
    topic: str,
    target_audience: str | None,
    duration_seconds: int,
    orientation: str,
    publish_privacy: str,
    usage_updates: dict[str, object] | None = None,
    queue_task: bool = True,
) -> VideoJob:
    effective_duration = (
        min(duration_seconds, 59) if orientation == "portrait" else duration_seconds
    )
    usage_metrics: dict[str, object] = {
        "publish_privacy": publish_privacy,
        "distribution_label": (
            "YouTube Shorts" if orientation == "portrait" else "Standard Video"
        ),
        "shorts_mode": orientation == "portrait",
        "requested_duration_seconds": duration_seconds,
    }
    if usage_updates:
        usage_metrics.update(usage_updates)

    job = VideoJob(
        topic=topic.strip(),
        target_audience=(target_audience.strip() or None) if target_audience else None,
        duration_seconds=effective_duration,
        orientation=orientation,
        status=JobStatus.PENDING,
        usage_metrics=usage_metrics,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    if queue_task:
        generate_video_pipeline.delay(str(job.id))
    return job


def _spawn_job_clone(db: Session, source_job: VideoJob) -> VideoJob:
    usage_metrics = dict(source_job.usage_metrics or {})
    publish_privacy = str(
        usage_metrics.get("publish_privacy") or settings.youtube_privacy_status
    )
    requested_duration = int(
        usage_metrics.get("requested_duration_seconds") or source_job.duration_seconds
    )
    job_kind = str(usage_metrics.get("job_kind") or "standard")
    usage_updates: dict[str, object] = {}
    if job_kind == "source_remix":
        usage_updates = {
            "job_kind": "source_remix",
            "shots_count": int(usage_metrics.get("shots_count") or 5),
            "distribution_label": str(
                usage_metrics.get("distribution_label")
                or (
                    "YouTube Shorts Remix"
                    if source_job.orientation == "portrait"
                    else "Long-form Remix"
                )
            ),
        }
    cloned_job = _spawn_new_job(
        db,
        topic=source_job.topic,
        target_audience=source_job.target_audience,
        duration_seconds=requested_duration,
        orientation=source_job.orientation,
        publish_privacy=publish_privacy,
        usage_updates=usage_updates,
        queue_task=False,
    )
    if job_kind == "source_remix":
        generate_source_remix_pipeline.delay(str(cloned_job.id))
    else:
        generate_video_pipeline.delay(str(cloned_job.id))
    return cloned_job


@router.get("/auth/session", response_model=AuthSessionRead)
def read_auth_session(
    session: AuthSessionRead = Depends(get_auth_session),
    _: None = Depends(rate_limit("auth-session", 90, 60)),
) -> AuthSessionRead:
    return session


@router.post("/auth/login", response_model=AuthSessionRead)
def login_operator(
    payload: LoginRequest,
    request: Request,
    _: None = Depends(rate_limit("auth-login", 5, 60)),
) -> AuthSessionRead:
    username_matches = constant_time_equals(
        payload.username.strip(), settings.operator_username
    )
    password_matches = constant_time_equals(
        payload.password, settings.operator_password
    )
    if not (username_matches and password_matches):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The operator username or password is incorrect.",
        )

    request.session.clear()
    request.session["operator_authenticated"] = True
    request.session["operator_username"] = settings.operator_username
    return get_auth_session(request)


@router.post("/auth/logout", response_model=AuthSessionRead)
def logout_operator(
    request: Request,
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("auth-logout", 20, 60)),
) -> AuthSessionRead:
    request.session.clear()
    return get_auth_session(request)


@router.post(
    "/jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    payload: VideoJobCreate,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-create", 6, 60)),
) -> JobCreateResponse:
    job = _spawn_new_job(
        db,
        topic=payload.topic,
        target_audience=payload.target_audience,
        duration_seconds=payload.duration_seconds,
        orientation=payload.orientation,
        publish_privacy=payload.publish_privacy,
    )
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.post(
    "/jobs/source-remix",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_source_remix_job(
    payload: SourceRemixJobCreate,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-source-remix", 4, 60)),
) -> JobCreateResponse:
    job = _spawn_new_job(
        db,
        topic=payload.topic,
        target_audience=payload.target_audience,
        duration_seconds=payload.duration_seconds,
        orientation=payload.orientation,
        publish_privacy=payload.publish_privacy,
        usage_updates={
            "job_kind": "source_remix",
            "shots_count": payload.shots_count,
            "distribution_label": (
                "YouTube Shorts Remix"
                if payload.orientation == "portrait"
                else "Long-form Remix"
            ),
        },
        queue_task=False,
    )
    generate_source_remix_pipeline.delay(str(job.id))
    return JobCreateResponse(job_id=job.id, status=job.status)


@router.post(
    "/jobs/bulk",
    response_model=BulkJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_bulk_jobs(
    payload: BulkVideoJobCreate,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-bulk", 3, 60)),
) -> BulkJobCreateResponse:
    planner = ResearcherService()
    batch_id = str(uuid4())
    batch_label = payload.niche.strip()
    subniche_plan = planner.generate_subniche_plan(
        niche=batch_label,
        target_audience=payload.target_audience,
        orientation=payload.orientation,
        videos_count=payload.videos_count,
    )

    queued_jobs: list[BulkQueuedJobRead] = []
    for index, item in enumerate(subniche_plan, start=1):
        topic = str(item.get("topic") or item.get("sub_niche") or batch_label).strip()
        target_audience = (
            str(item.get("target_audience") or payload.target_audience or "").strip()
            or None
        )
        usage_updates: dict[str, object] = {
            "batch_id": batch_id,
            "batch_label": batch_label,
            "batch_index": index,
            "sub_niche": str(item.get("sub_niche") or topic).strip(),
            "angle": str(item.get("angle") or "").strip(),
        }
        job = _spawn_new_job(
            db,
            topic=topic[:255],
            target_audience=target_audience,
            duration_seconds=payload.duration_seconds,
            orientation=payload.orientation,
            publish_privacy=payload.publish_privacy,
            usage_updates=usage_updates,
        )
        queued_jobs.append(
            BulkQueuedJobRead(
                job_id=job.id,
                topic=job.topic,
                target_audience=job.target_audience,
                status=job.status,
                batch_index=index,
            )
        )

    return BulkJobCreateResponse(
        batch_id=batch_id,
        batch_label=batch_label,
        videos_count=len(queued_jobs),
        jobs=queued_jobs,
    )


@router.get("/jobs", response_model=VideoJobCollection)
def list_jobs(
    page_size: int = Query(default=settings.default_jobs_page_size, ge=1, le=50),
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-list", 120, 60)),
) -> VideoJobCollection:
    total_count = db.scalar(select(func.count()).select_from(VideoJob)) or 0
    active_count = (
        db.scalar(
            select(func.count())
            .select_from(VideoJob)
            .where(
                VideoJob.status.notin_(
                    [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
                )
            )
        )
        or 0
    )
    blocked_count = (
        db.scalar(
            select(func.count())
            .select_from(VideoJob)
            .where(VideoJob.status == JobStatus.BLOCKED_BY_QUALITY_GATE)
        )
        or 0
    )
    jobs = db.scalars(
        select(VideoJob).order_by(VideoJob.created_at.desc()).limit(page_size)
    ).all()
    return VideoJobCollection(
        jobs=[_to_job_summary(job) for job in jobs],
        total_count=total_count,
        page_size=page_size,
        active_count=active_count,
        blocked_count=blocked_count,
    )


@router.get("/jobs/{job_id}", response_model=VideoJobRead)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-detail", 120, 60)),
) -> VideoJobRead:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return _to_job_detail(job)


@router.post("/jobs/{job_id}/publish", response_model=JobActionResponse)
def publish_job(
    job_id: UUID,
    payload: JobPublishRequest,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-publish", 10, 60)),
) -> JobActionResponse:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    if job.status != JobStatus.READY_TO_PUBLISH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job must be READY_TO_PUBLISH.",
        )

    job.status = JobStatus.UPLOADING
    db.add(job)
    db.commit()
    db.refresh(job)
    execute_publish_pipeline.delay(str(job.id), payload.channel_label)
    return JobActionResponse(
        job_id=job.id,
        status="publishing",
        message=f"Upload queued for channel: {payload.channel_label}",
    )


@router.post("/jobs/bulk-publish", response_model=BulkJobActionResponse)
def bulk_publish_jobs(
    payload: BulkJobPublishRequest,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-bulk-publish", 5, 60)),
) -> BulkJobActionResponse:
    jobs = db.scalars(select(VideoJob).where(VideoJob.id.in_(payload.job_ids))).all()
    count = 0
    for job in jobs:
        if job.status == JobStatus.READY_TO_PUBLISH:
            job.status = JobStatus.UPLOADING
            db.add(job)
            execute_publish_pipeline.delay(str(job.id), payload.channel_label)
            count += 1
    db.commit()
    return BulkJobActionResponse(jobs_processed=count, status="bulk_publishing")


@router.post("/jobs/{job_id}/review", response_model=VideoJobRead)
def review_quality_gate(
    job_id: UUID,
    payload: JobReviewDecision,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-review", 12, 60)),
) -> VideoJobRead:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if payload.approved:
        job.manual_override = True
        job.status = JobStatus.READY_TO_PUBLISH
        job.critique_text = (
            "\n\n".join(filter(None, [job.critique_text, payload.notes]))
            if payload.notes
            else job.critique_text
        )
        db.add(job)
        db.commit()
        db.refresh(job)
    else:
        job.status = JobStatus.CANCELLED
        job.error_log = (
            payload.notes or "Job terminated by the operator after quality gate review."
        )
        db.add(job)
        db.commit()
        db.refresh(job)

    return _to_job_detail(job)


@router.post("/jobs/{job_id}/resume-from-stage", response_model=VideoJobRead)
def resume_job_from_last_good_stage(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-resume-stage", 10, 60)),
) -> VideoJobRead:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed or cancelled jobs can resume from the last good stage.",
        )

    job.error_log = None
    job.manual_override = False
    job.status = JobStatus.PENDING
    db.add(job)
    db.commit()
    db.refresh(job)
    resume_failed_pipeline.delay(str(job.id))
    return _to_job_detail(job)


@router.post("/jobs/{job_id}/retry", response_model=JobCreateResponse)
def retry_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-retry", 12, 60)),
) -> JobCreateResponse:
    source_job = db.get(VideoJob, job_id)
    if source_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if source_job.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed or cancelled jobs can be retried.",
        )

    cloned_job = _spawn_job_clone(db, source_job)
    return JobCreateResponse(job_id=cloned_job.id, status=cloned_job.status)


@router.post("/jobs/{job_id}/duplicate", response_model=JobCreateResponse)
def duplicate_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-duplicate", 20, 60)),
) -> JobCreateResponse:
    source_job = db.get(VideoJob, job_id)
    if source_job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    cloned_job = _spawn_job_clone(db, source_job)
    return JobCreateResponse(job_id=cloned_job.id, status=cloned_job.status)


@router.post("/jobs/{job_id}/regenerate-metadata", response_model=VideoJobRead)
def regenerate_job_metadata(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-regenerate-metadata", 12, 60)),
) -> VideoJobRead:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if not job.script_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This job does not have enough script content to regenerate metadata yet.",
        )

    researcher = ResearcherService()
    regenerated = researcher.regenerate_metadata(
        topic=job.topic,
        script_text=job.script_text,
        orientation=job.orientation,
        target_audience=job.target_audience,
    )
    job.title = regenerated.get("title") or job.title
    job.description = regenerated.get("description") or job.description
    usage_metrics = dict(job.usage_metrics or {})
    usage_metrics["metadata_tags"] = regenerated.get("tags") or []
    usage_metrics["metadata_hashtags"] = regenerated.get("hashtags") or []
    usage_metrics["hook_text"] = regenerated.get("hook_text") or job.title or job.topic
    job.usage_metrics = usage_metrics
    db.add(job)
    db.commit()
    db.refresh(job)

    if job.youtube_video_id:
        publisher = PublisherService()
        update_result = publisher.update_video_metadata(db=db, job=job)
        job.youtube_url = update_result["youtube_url"]
        db.add(job)
        db.commit()
        db.refresh(job)

    return _to_job_detail(job)


@router.post("/jobs/{job_id}/make-public", response_model=VideoJobRead)
def make_job_public(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-make-public", 10, 60)),
) -> VideoJobRead:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if not job.youtube_video_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This job does not have an uploaded YouTube video yet.",
        )

    publisher = PublisherService()
    update_result = publisher.update_video_privacy(
        db=db,
        job=job,
        privacy_status="public",
    )
    usage_metrics = dict(job.usage_metrics or {})
    usage_metrics["publish_privacy"] = "public"
    job.usage_metrics = usage_metrics
    job.youtube_url = update_result["youtube_url"]
    db.add(job)
    db.commit()
    db.refresh(job)
    return _to_job_detail(job)


@router.delete("/jobs/{job_id}", response_model=JobActionResponse)
def delete_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("jobs-delete", 10, 60)),
) -> JobActionResponse:
    job = db.get(VideoJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    if job.status not in {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.BLOCKED_BY_QUALITY_GATE,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only completed, failed, cancelled, or blocked jobs can be deleted.",
        )

    artifacts_dir = settings.local_artifacts_root / str(job.id)
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir, ignore_errors=True)

    db.delete(job)
    db.commit()
    return JobActionResponse(
        job_id=job_id,
        status="deleted",
        message="The job record and local artifacts were deleted. Any uploaded YouTube video remains untouched.",
    )


@router.post(
    "/webhook/n8n",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job_from_n8n(
    payload: VideoJobCreate,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("n8n-webhook", 10, 60)),
) -> JobCreateResponse:
    return create_job(payload=payload, db=db)


@router.get("/integrations/youtube/channels", response_model=YouTubeChannelList)
def list_youtube_channels(
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("youtube-channels", 60, 60)),
) -> YouTubeChannelList:
    channels = db.scalars(
        select(YouTubeCredential).order_by(YouTubeCredential.created_at.desc())
    ).all()
    return YouTubeChannelList(
        channels=[
            YouTubeChannelRead(
                id=c.id,
                channel_label=c.channel_label,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in channels
        ]
    )


@router.delete("/integrations/youtube/channels/{channel_id}")
def delete_youtube_channel(
    channel_id: int,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("youtube-channel-delete", 10, 60)),
) -> dict[str, str]:
    channel = db.get(YouTubeCredential, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(channel)
    db.commit()
    return {"status": "deleted"}


@router.post("/integrations/youtube/credentials", response_model=CredentialResponse)
def upsert_youtube_credentials(
    payload: YouTubeCredentialUpsert,
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("youtube-credentials", 6, 60)),
) -> CredentialResponse:
    record = (
        db.query(YouTubeCredential)
        .filter(YouTubeCredential.channel_label == payload.channel_label)
        .one_or_none()
    )
    encrypted_token = encrypt_secret(payload.refresh_token)
    if record is None:
        record = YouTubeCredential(
            channel_label=payload.channel_label,
            refresh_token=encrypted_token,
            scopes_json=payload.scopes_json,
        )
    else:
        record.refresh_token = encrypted_token
        record.scopes_json = payload.scopes_json

    db.add(record)
    db.commit()
    return CredentialResponse(channel_label=payload.channel_label, status="saved")


@router.get("/integrations/youtube/status", response_model=YouTubeConnectionStatus)
def get_youtube_connection_status(
    channel_label: str = Query(default="default", min_length=1, max_length=255),
    db: Session = Depends(get_db),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("youtube-status", 60, 60)),
) -> YouTubeConnectionStatus:
    publisher = PublisherService()
    payload = publisher.get_connection_status(db=db, channel_label=channel_label)
    return YouTubeConnectionStatus(**payload)


@router.get("/integrations/youtube/oauth/start")
def start_youtube_oauth(
    request: Request,
    channel_label: str = Query(default="default", min_length=1, max_length=255),
    _: AuthSessionRead = Depends(require_operator),
    __: None = Depends(rate_limit("youtube-oauth-start", 8, 60)),
) -> RedirectResponse:
    publisher = PublisherService()
    state_token = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    request.session["youtube_oauth_state"] = state_token
    request.session["youtube_oauth_code_verifier"] = code_verifier
    request.session["youtube_oauth_channel_label"] = channel_label
    request.session["youtube_oauth_started_at"] = int(time.time())
    try:
        authorization_url = publisher.build_dashboard_authorization_url(
            state=state_token,
            code_verifier=code_verifier,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return RedirectResponse(
        url=authorization_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.get("/integrations/youtube/oauth/callback")
def finish_youtube_oauth(
    request: Request,
    db: Session = Depends(get_db),
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    publisher = PublisherService()

    if error:
        request.session.pop("youtube_oauth_state", None)
        request.session.pop("youtube_oauth_code_verifier", None)
        request.session.pop("youtube_oauth_channel_label", None)
        request.session.pop("youtube_oauth_started_at", None)
        return RedirectResponse(
            url=publisher.build_frontend_callback_url(
                oauth_status="error",
                message=error_description or error,
            ),
            status_code=status.HTTP_302_FOUND,
        )

    expected_state = request.session.get("youtube_oauth_state")
    code_verifier = request.session.get("youtube_oauth_code_verifier")
    started_at = int(request.session.get("youtube_oauth_started_at", 0) or 0)
    channel_label = request.session.get(
        "youtube_oauth_channel_label", settings.youtube_channel_label
    )

    if not state or not code or not expected_state or not code_verifier:
        request.session.pop("youtube_oauth_state", None)
        request.session.pop("youtube_oauth_code_verifier", None)
        request.session.pop("youtube_oauth_channel_label", None)
        request.session.pop("youtube_oauth_started_at", None)
        return RedirectResponse(
            url=publisher.build_frontend_callback_url(
                oauth_status="error",
                message="Missing OAuth session state, PKCE code verifier, or Google authorization code.",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    if not constant_time_equals(str(state), str(expected_state)):
        request.session.pop("youtube_oauth_state", None)
        request.session.pop("youtube_oauth_code_verifier", None)
        request.session.pop("youtube_oauth_channel_label", None)
        request.session.pop("youtube_oauth_started_at", None)
        return RedirectResponse(
            url=publisher.build_frontend_callback_url(
                oauth_status="error",
                message="The OAuth state did not match the active login session. Start the connection flow again.",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    if started_at and (int(time.time()) - started_at) > 900:
        request.session.pop("youtube_oauth_state", None)
        request.session.pop("youtube_oauth_code_verifier", None)
        request.session.pop("youtube_oauth_channel_label", None)
        request.session.pop("youtube_oauth_started_at", None)
        return RedirectResponse(
            url=publisher.build_frontend_callback_url(
                oauth_status="error",
                message="The OAuth session expired. Start the connection flow again.",
            ),
            status_code=status.HTTP_302_FOUND,
        )

    try:
        payload = publisher.complete_dashboard_authorization(
            db=db,
            channel_label=str(channel_label),
            state=str(state),
            code_verifier=str(code_verifier),
            code=str(code),
        )
    except Exception as exc:
        return RedirectResponse(
            url=publisher.build_frontend_callback_url(
                oauth_status="error",
                message=str(exc),
            ),
            status_code=status.HTTP_302_FOUND,
        )
    finally:
        request.session.pop("youtube_oauth_state", None)
        request.session.pop("youtube_oauth_code_verifier", None)
        request.session.pop("youtube_oauth_channel_label", None)
        request.session.pop("youtube_oauth_started_at", None)

    return RedirectResponse(
        url=publisher.build_frontend_callback_url(
            oauth_status="success",
            message="YouTube channel connected successfully.",
            channel_label=payload["channel_label"],
        ),
        status_code=status.HTTP_302_FOUND,
    )

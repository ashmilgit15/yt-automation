from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models.db_models import JobStatus, VideoJob
from backend.services.audio import AudioService
from backend.services.composer import ComposerService
from backend.services.publisher import PublisherService
from backend.services.researcher import ResearcherService
from backend.services.source_remix import SourceRemixService
from backend.services.transcriber import TranscriberService
from backend.services.utils import stacktrace_from_exception
from backend.services.visual_curator import VisualCuratorService
from backend.worker.celery_app import celery_app


def _get_job(db: Session, job_id: str) -> VideoJob:
    job = db.get(VideoJob, UUID(job_id))
    if job is None:
        raise ValueError(f"VideoJob {job_id} does not exist")
    return job


def _merge_dict(
    existing: dict[str, Any] | None, updates: dict[str, Any]
) -> dict[str, Any]:
    base = dict(existing or {})
    base.update(updates)
    return base


def _set_status(db: Session, job: VideoJob, status: JobStatus) -> None:
    job.status = status
    db.add(job)
    db.commit()
    db.refresh(job)


def _resolve_existing_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    resolved = Path(path_value).resolve()
    if resolved.exists():
        return str(resolved)
    return None


def _fail_job(db: Session, job: VideoJob, exc: Exception) -> None:
    job.status = JobStatus.FAILED
    job.error_log = stacktrace_from_exception(exc)
    db.add(job)
    db.commit()


@celery_app.task(bind=True, name="backend.worker.tasks.generate_video_pipeline")
def generate_video_pipeline(self: Task, job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)

        researcher = ResearcherService()
        audio_service = AudioService()
        visual_curator = VisualCuratorService()
        transcriber = TranscriberService()
        composer = ComposerService()
        publisher = PublisherService()

        try:
            _set_status(db, job, JobStatus.RESEARCHING)
            narrative = researcher.generate_narrative(
                topic=job.topic,
                duration_seconds=job.duration_seconds,
                orientation=job.orientation,
                target_audience=job.target_audience,
            )
            job.script_text = narrative.get("script_text")
            job.scenes_json = narrative.get("scenes")
            job.title = narrative.get("title")
            job.description = narrative.get("description")
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {
                    "research_context": narrative.get("context"),
                    "metadata_tags": narrative.get("tags") or [],
                    "metadata_hashtags": narrative.get("hashtags") or [],
                    "hook_text": narrative.get("hook_text") or narrative.get("title"),
                },
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_log = stacktrace_from_exception(exc)
            db.add(job)
            db.commit()
            raise

        try:
            _set_status(db, job, JobStatus.AUDIO)
            audio_result = audio_service.synthesize(
                job_id=job_id,
                script_text=job.script_text or "",
                scenes=job.scenes_json or [],
            )
            job.scenes_json = audio_result["timed_scenes"]
            job.artifact_paths = _merge_dict(
                job.artifact_paths, {"narration": audio_result["audio_path"]}
            )
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {"audio_duration_seconds": audio_result["duration_seconds"]},
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            transcription = transcriber.transcribe(
                job_id=job_id, audio_path=audio_result["audio_path"]
            )
            job.artifact_paths = _merge_dict(
                job.artifact_paths, {"subtitles": transcription["subtitle_path"]}
            )
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {"transcription_word_count": len(transcription.get("words", []))},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_log = stacktrace_from_exception(exc)
            db.add(job)
            db.commit()
            raise

        try:
            _set_status(db, job, JobStatus.VISUALS)
            visuals = visual_curator.curate(
                job_id=job_id, scenes=job.scenes_json or [], orientation=job.orientation
            )
            job.visual_asset_manifest = visuals["assets"]
            job.usage_metrics = _merge_dict(
                job.usage_metrics, {"visual_asset_count": len(visuals["assets"])}
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_log = stacktrace_from_exception(exc)
            db.add(job)
            db.commit()
            raise

        try:
            _set_status(db, job, JobStatus.COMPOSING)
            composition = composer.compose(
                job_id=job_id,
                scenes=job.scenes_json or [],
                visual_manifest=job.visual_asset_manifest or [],
                narration_path=(job.artifact_paths or {}).get("narration", ""),
                subtitles_path=(job.artifact_paths or {}).get("subtitles", ""),
                orientation=job.orientation,
                overlay_text=str(
                    (job.usage_metrics or {}).get("hook_text") or job.title or job.topic
                ),
            )
            job.artifact_paths = _merge_dict(job.artifact_paths, composition)
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_log = stacktrace_from_exception(exc)
            db.add(job)
            db.commit()
            raise

        try:
            gate_result = publisher.evaluate_quality(job=job)
            job.quality_score = int(round(float(gate_result.get("score", 0))))
            job.critique_text = gate_result.get("critique")
            job.critique_json = gate_result
            job.error_log = None
            if (
                job.quality_score < settings.quality_gate_threshold
                and not job.manual_override
            ):
                job.status = JobStatus.BLOCKED_BY_QUALITY_GATE
            else:
                job.status = JobStatus.READY_TO_PUBLISH
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_log = stacktrace_from_exception(exc)
            db.add(job)
            db.commit()
            raise

        return {"job_id": job_id, "status": job.status.value}
    finally:
        db.close()


@celery_app.task(bind=True, name="backend.worker.tasks.generate_source_remix_pipeline")
def generate_source_remix_pipeline(self: Task, job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)

        remix_service = SourceRemixService()
        transcriber = TranscriberService()
        publisher = PublisherService()

        try:
            _set_status(db, job, JobStatus.RESEARCHING)
            shots_count = int((job.usage_metrics or {}).get("shots_count") or 5)
            source_metadata = remix_service.discover_source_video(
                topic=job.topic,
                target_audience=job.target_audience,
            )
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {
                    "job_kind": "source_remix",
                    "source_youtube_url": source_metadata.get("url"),
                    "source_title": source_metadata.get("title"),
                    "source_channel": source_metadata.get("channel"),
                    "source_duration_seconds": source_metadata.get("duration_seconds"),
                    "source_selection_reason": source_metadata.get("selection_reason"),
                    "shots_count": shots_count,
                },
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            _fail_job(db, job, exc)
            raise

        try:
            _set_status(db, job, JobStatus.AUDIO)
            source_result = remix_service.download_source_video(
                job_id=job_id,
                source_url=str(
                    (job.usage_metrics or {}).get("source_youtube_url") or ""
                ),
            )
            job.artifact_paths = _merge_dict(
                job.artifact_paths,
                {
                    "source_video": source_result["video_path"],
                    "source_audio": source_result["audio_path"],
                },
            )
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {
                    "source_video_duration_seconds": source_result[
                        "video_duration_seconds"
                    ]
                },
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            transcription = transcriber.transcribe(
                job_id=job_id,
                audio_path=source_result["audio_path"],
            )
            job.artifact_paths = _merge_dict(
                job.artifact_paths,
                {"source_transcript_subtitles": transcription["subtitle_path"]},
            )
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {"transcription_word_count": len(transcription.get("words", []))},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            _fail_job(db, job, exc)
            raise

        try:
            _set_status(db, job, JobStatus.VISUALS)
            remix_plan = remix_service.plan_remix_shots(
                job_id=job_id,
                topic=job.topic,
                source_metadata={
                    "title": (job.usage_metrics or {}).get("source_title"),
                    "url": (job.usage_metrics or {}).get("source_youtube_url"),
                },
                transcript_payload=transcription["transcript"],
                shots_count=int((job.usage_metrics or {}).get("shots_count") or 5),
                orientation=job.orientation,
                target_audience=job.target_audience,
            )
            job.title = remix_plan.get("title") or job.topic
            job.description = remix_plan.get("description") or job.description
            job.script_text = "\n".join(
                shot.get("transcript_excerpt", "")
                for shot in remix_plan.get("shots", [])
            ).strip()
            job.scenes_json = remix_plan.get("shots")
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {
                    "metadata_tags": remix_plan.get("tags") or [],
                    "metadata_hashtags": remix_plan.get("hashtags") or [],
                    "hook_text": remix_plan.get("hook_text") or job.title or job.topic,
                    "visual_asset_count": len(remix_plan.get("shots", [])),
                },
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            _fail_job(db, job, exc)
            raise

        try:
            _set_status(db, job, JobStatus.COMPOSING)
            composition = remix_service.compose_remix(
                job_id=job_id,
                source_video_path=(job.artifact_paths or {}).get("source_video", ""),
                shots=job.scenes_json or [],
                orientation=job.orientation,
                hook_text=str(
                    (job.usage_metrics or {}).get("hook_text") or job.title or job.topic
                ),
            )
            job.artifact_paths = _merge_dict(job.artifact_paths, composition)
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            _fail_job(db, job, exc)
            raise

        try:
            gate_result = publisher.evaluate_quality(job=job)
            job.quality_score = int(round(float(gate_result.get("score", 0))))
            job.critique_text = gate_result.get("critique")
            job.critique_json = gate_result
            job.error_log = None
            if (
                job.quality_score < settings.quality_gate_threshold
                and not job.manual_override
            ):
                job.status = JobStatus.BLOCKED_BY_QUALITY_GATE
            else:
                job.status = JobStatus.READY_TO_PUBLISH
            db.add(job)
            db.commit()
            db.refresh(job)
        except Exception as exc:
            _fail_job(db, job, exc)
            raise

        return {"job_id": job_id, "status": job.status.value}
    finally:
        db.close()


@celery_app.task(bind=True, name="backend.worker.tasks.execute_publish_pipeline")
def execute_publish_pipeline(
    self: Task, job_id: str, channel_label: str
) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)
        publisher = PublisherService()
        _set_status(db, job, JobStatus.UPLOADING)
        try:
            publish_result = publisher.publish(
                db=db,
                job=job,
                video_path=(job.artifact_paths or {}).get("final_video_path", ""),
                channel_label=channel_label,
                force=True,
            )
            job.youtube_video_id = publish_result.get("youtube_video_id")
            job.youtube_url = publish_result.get("youtube_url")
            usage_metrics = dict(job.usage_metrics or {})
            usage_metrics["uploaded_channel_label"] = channel_label
            job.usage_metrics = usage_metrics
            job.status = JobStatus.COMPLETED
            job.error_log = None
            db.add(job)
            db.commit()
            db.refresh(job)
            return {"job_id": job_id, "status": job.status.value}
        except Exception as exc:
            job.status = JobStatus.FAILED
            job.error_log = stacktrace_from_exception(exc)
            db.add(job)
            db.commit()
            raise
    finally:
        db.close()


@celery_app.task(bind=True, name="backend.worker.tasks.resume_failed_pipeline")
def resume_failed_pipeline(self: Task, job_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        job = _get_job(db, job_id)

        researcher = ResearcherService()
        audio_service = AudioService()
        visual_curator = VisualCuratorService()
        transcriber = TranscriberService()
        composer = ComposerService()
        publisher = PublisherService()

        artifact_paths = dict(job.artifact_paths or {})
        narration_path = _resolve_existing_path(artifact_paths.get("narration"))
        subtitles_path = _resolve_existing_path(artifact_paths.get("subtitles"))
        final_video_path = _resolve_existing_path(
            artifact_paths.get("final_video_path")
        )

        job.error_log = None
        db.add(job)
        db.commit()
        db.refresh(job)

        if not job.script_text or not job.scenes_json:
            _set_status(db, job, JobStatus.RESEARCHING)
            narrative = researcher.generate_narrative(
                topic=job.topic,
                duration_seconds=job.duration_seconds,
                orientation=job.orientation,
                target_audience=job.target_audience,
            )
            job.script_text = narrative.get("script_text")
            job.scenes_json = narrative.get("scenes")
            job.title = narrative.get("title")
            job.description = narrative.get("description")
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {
                    "research_context": narrative.get("context"),
                    "metadata_tags": narrative.get("tags") or [],
                    "metadata_hashtags": narrative.get("hashtags") or [],
                    "hook_text": narrative.get("hook_text") or narrative.get("title"),
                },
            )
            db.add(job)
            db.commit()
            db.refresh(job)

        if not narration_path or not subtitles_path:
            _set_status(db, job, JobStatus.AUDIO)
            audio_result = audio_service.synthesize(
                job_id=job_id,
                script_text=job.script_text or "",
                scenes=job.scenes_json or [],
            )
            job.scenes_json = audio_result["timed_scenes"]
            artifact_paths.update({"narration": audio_result["audio_path"]})
            job.artifact_paths = artifact_paths
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {"audio_duration_seconds": audio_result["duration_seconds"]},
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            transcription = transcriber.transcribe(
                job_id=job_id, audio_path=audio_result["audio_path"]
            )
            artifact_paths.update({"subtitles": transcription["subtitle_path"]})
            job.artifact_paths = artifact_paths
            job.usage_metrics = _merge_dict(
                job.usage_metrics,
                {"transcription_word_count": len(transcription.get("words", []))},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            narration_path = _resolve_existing_path(artifact_paths.get("narration"))
            subtitles_path = _resolve_existing_path(artifact_paths.get("subtitles"))

        if not (job.visual_asset_manifest or []):
            _set_status(db, job, JobStatus.VISUALS)
            visuals = visual_curator.curate(
                job_id=job_id,
                scenes=job.scenes_json or [],
                orientation=job.orientation,
            )
            job.visual_asset_manifest = visuals["assets"]
            job.usage_metrics = _merge_dict(
                job.usage_metrics, {"visual_asset_count": len(visuals["assets"])}
            )
            db.add(job)
            db.commit()
            db.refresh(job)

        if not final_video_path:
            _set_status(db, job, JobStatus.COMPOSING)
            composition = composer.compose(
                job_id=job_id,
                scenes=job.scenes_json or [],
                visual_manifest=job.visual_asset_manifest or [],
                narration_path=narration_path or "",
                subtitles_path=subtitles_path or "",
                orientation=job.orientation,
                overlay_text=str(
                    (job.usage_metrics or {}).get("hook_text") or job.title or job.topic
                ),
            )
            artifact_paths.update(composition)
            job.artifact_paths = artifact_paths
            db.add(job)
            db.commit()
            db.refresh(job)
            final_video_path = _resolve_existing_path(
                artifact_paths.get("final_video_path")
            )

        gate_result = publisher.evaluate_quality(job=job)
        job.quality_score = int(round(float(gate_result.get("score", 0))))
        job.critique_text = gate_result.get("critique")
        job.critique_json = gate_result
        job.error_log = None
        if (
            job.quality_score < settings.quality_gate_threshold
            and not job.manual_override
        ):
            job.status = JobStatus.BLOCKED_BY_QUALITY_GATE
        else:
            job.status = JobStatus.READY_TO_PUBLISH
        db.add(job)
        db.commit()
        db.refresh(job)
        return {"job_id": job_id, "status": job.status.value}
    except Exception as exc:
        job = _get_job(db, job_id)
        job.status = JobStatus.FAILED
        job.error_log = stacktrace_from_exception(exc)
        db.add(job)
        db.commit()
        raise
    finally:
        db.close()

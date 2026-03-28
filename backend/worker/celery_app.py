from celery import Celery

from backend.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "video_factory",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["backend.worker.tasks"],
)

celery_app.conf.update(
    task_default_queue="video-jobs",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
)

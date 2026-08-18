from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.core.config import get_settings


settings = get_settings()


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import text
    from backend.models.db_models import VideoJob, YouTubeCredential  # noqa: F401
    from backend.models.transcription_models import PlaylistBatch, TranscriptJob  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # Automatic schema migration for existing PostgreSQL volumes
    migration_statements = [
        "ALTER TABLE playlist_batches ADD COLUMN IF NOT EXISTS engine VARCHAR(32) DEFAULT 'local_whisper';",
        "ALTER TABLE playlist_batches ADD COLUMN IF NOT EXISTS enable_ai_cleanup BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE playlist_batches ADD COLUMN IF NOT EXISTS enable_ai_summary BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE playlist_batches ADD COLUMN IF NOT EXISTS batch_summary_markdown TEXT;",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS engine VARCHAR(32) DEFAULT 'local_whisper';",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS stage_detail VARCHAR(255);",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS mode VARCHAR(32) DEFAULT 'transcribe';",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS enable_ai_cleanup BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS enable_ai_summary BOOLEAN DEFAULT FALSE;",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS clean_transcript_text TEXT;",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS clean_segments_json JSONB;",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS summary_json JSONB;",
        "ALTER TABLE transcript_jobs ADD COLUMN IF NOT EXISTS summary_markdown TEXT;",
        "ALTER TABLE transcript_jobs ALTER COLUMN playlist_batch_id DROP NOT NULL;",
        "ALTER TYPE playlist_batch_status ADD VALUE IF NOT EXISTS 'PAUSED';",
        "ALTER TYPE playlist_batch_status ADD VALUE IF NOT EXISTS 'CANCELLED';",
        "ALTER TYPE transcript_job_status ADD VALUE IF NOT EXISTS 'CLEANING';",
        "ALTER TYPE transcript_job_status ADD VALUE IF NOT EXISTS 'SUMMARIZING';",
        "ALTER TYPE transcript_job_status ADD VALUE IF NOT EXISTS 'PAUSED';",
        "ALTER TYPE transcript_job_status ADD VALUE IF NOT EXISTS 'CANCELLED';",
    ]

    with engine.begin() as conn:
        for stmt in migration_statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


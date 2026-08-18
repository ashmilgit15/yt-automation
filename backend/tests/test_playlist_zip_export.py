import io
import re
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.dependencies import get_auth_session, require_operator
from backend.api.main import app
from backend.core.database import Base, get_db
from backend.models.schemas import AuthSessionRead
from backend.models.transcription_models import (
    PlaylistBatch,
    PlaylistStatus,
    TranscriptJob,
    TranscriptStatus,
)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


class TestPlaylistZipExport(unittest.TestCase):
    def setUp(self):
        self.test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.test_engine)
        self.TestingSessionLocal = sessionmaker(
            bind=self.test_engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
        self.db = self.TestingSessionLocal()

        def override_get_db():
            try:
                yield self.db
            finally:
                pass

        def override_require_operator():
            return AuthSessionRead(authenticated=True, username="test_operator")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[require_operator] = override_require_operator
        app.dependency_overrides[get_auth_session] = override_require_operator

        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        Base.metadata.drop_all(bind=self.test_engine)

    def test_export_zip_returns_200_and_valid_zip(self):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL12345678",
            source_url="https://www.youtube.com/playlist?list=PL12345678",
            title="Python Mastery Course",
            engine="local_whisper",
            status=PlaylistStatus.COMPLETED,
            total_videos=2,
            completed_videos=2,
            failed_videos=0,
            enable_ai_cleanup=True,
            enable_ai_summary=True,
            batch_summary_markdown="# Master Summary\nOverall course overview and takeaways.",
        )
        self.db.add(batch)

        job1 = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="vid001",
            video_url="https://www.youtube.com/watch?v=vid001",
            title="Introduction to Python",
            channel_title="Code Academy",
            position=0,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Welcome to python intro.",
            clean_transcript_text="Welcome to Python introduction.",
            summary_markdown="### Intro Summary\nKey points of intro.",
            segments_json=[{"start": 0.0, "end": 2.5, "text": "Welcome to python intro."}],
        )
        job2 = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="vid002",
            video_url="https://www.youtube.com/watch?v=vid002",
            title="Advanced Asyncio Patterns",
            channel_title="Code Academy",
            position=1,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Let us talk about asyncio.",
            clean_transcript_text="Let us discuss asyncio patterns.",
            summary_markdown="### Asyncio Summary\nAsyncio details.",
            segments_json=[{"start": 0.0, "end": 3.0, "text": "Let us talk about asyncio."}],
        )
        self.db.add_all([job1, job2])
        self.db.commit()

        response = self.client.get(f"/api/v1/playlists/{batch_id}/export/zip")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertIn("attachment; filename=", response.headers["content-disposition"])

        zip_bytes = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()

            # Check Root Master Summary
            self.assertIn("00_MASTER_PLAYLIST_SUMMARY.md", namelist)
            self.assertTrue(zf.read("00_MASTER_PLAYLIST_SUMMARY.md").decode("utf-8").startswith("# Master Summary"))

            # Check Video 1 Files
            self.assertIn("Transcripts/01 - Introduction to Python.txt", namelist)
            self.assertEqual(zf.read("Transcripts/01 - Introduction to Python.txt").decode("utf-8").strip(), "Welcome to python intro.")

            self.assertIn("Clean_Transcripts/01 - Introduction to Python (Clean).txt", namelist)
            self.assertEqual(zf.read("Clean_Transcripts/01 - Introduction to Python (Clean).txt").decode("utf-8").strip(), "Welcome to Python introduction.")

            self.assertIn("Summaries/01 - Introduction to Python - Summary.md", namelist)
            self.assertEqual(zf.read("Summaries/01 - Introduction to Python - Summary.md").decode("utf-8").strip(), "### Intro Summary\nKey points of intro.")

            self.assertIn("Subtitles_SRT/01 - Introduction to Python.srt", namelist)
            self.assertIn("-->", zf.read("Subtitles_SRT/01 - Introduction to Python.srt").decode("utf-8"))

            self.assertIn("Subtitles_VTT/01 - Introduction to Python.vtt", namelist)
            self.assertIn("WEBVTT", zf.read("Subtitles_VTT/01 - Introduction to Python.vtt").decode("utf-8"))

            # Check Video 2 Files
            self.assertIn("Transcripts/02 - Advanced Asyncio Patterns.txt", namelist)
            self.assertIn("Clean_Transcripts/02 - Advanced Asyncio Patterns (Clean).txt", namelist)
            self.assertIn("Summaries/02 - Advanced Asyncio Patterns - Summary.md", namelist)
            self.assertIn("Subtitles_SRT/02 - Advanced Asyncio Patterns.srt", namelist)
            self.assertIn("Subtitles_VTT/02 - Advanced Asyncio Patterns.vtt", namelist)

    def test_export_zip_without_master_summary(self):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL999",
            source_url="https://www.youtube.com/playlist?list=PL999",
            title="Single Video Batch",
            status=PlaylistStatus.COMPLETED,
            total_videos=1,
            completed_videos=1,
            batch_summary_markdown=None,
        )
        job = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v1",
            video_url="https://www.youtube.com/watch?v=v1",
            title="Quick Tutorial",
            position=0,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Simple tutorial text.",
        )
        self.db.add_all([batch, job])
        self.db.commit()

        response = self.client.get(f"/api/v1/playlists/{batch_id}/export/zip")
        self.assertEqual(response.status_code, 200)

        zip_bytes = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()
            self.assertNotIn("00_MASTER_PLAYLIST_SUMMARY.md", namelist)
            self.assertIn("Transcripts/01 - Quick Tutorial.txt", namelist)

    def test_export_zip_0_completed_returns_400(self):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL_EMPTY",
            source_url="https://www.youtube.com/playlist?list=PL_EMPTY",
            title="Pending Batch",
            status=PlaylistStatus.QUEUED,
            total_videos=2,
            completed_videos=0,
        )
        job1 = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v1",
            video_url="https://www.youtube.com/watch?v=v1",
            title="Pending Video 1",
            position=0,
            status=TranscriptStatus.PENDING,
            transcript_text=None,
        )
        job2 = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v2",
            video_url="https://www.youtube.com/watch?v=v2",
            title="Pending Video 2",
            position=1,
            status=TranscriptStatus.PENDING,
            transcript_text=None,
        )
        self.db.add_all([batch, job1, job2])
        self.db.commit()

        response = self.client.get(f"/api/v1/playlists/{batch_id}/export/zip")
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("No completed transcripts available to export", data["detail"])

    def test_export_zip_partial_batch_includes_only_completed(self):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL_PARTIAL",
            source_url="https://www.youtube.com/playlist?list=PL_PARTIAL",
            title="Partial Batch",
            status=PlaylistStatus.PARTIAL,
            total_videos=3,
            completed_videos=1,
            failed_videos=1,
        )
        job_done = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_done",
            video_url="https://www.youtube.com/watch?v=v_done",
            title="Done Video",
            position=0,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Completed text.",
        )
        job_failed = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_failed",
            video_url="https://www.youtube.com/watch?v=v_failed",
            title="Failed Video",
            position=1,
            status=TranscriptStatus.FAILED,
            transcript_text=None,
        )
        job_processing = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_proc",
            video_url="https://www.youtube.com/watch?v=v_proc",
            title="Processing Video",
            position=2,
            status=TranscriptStatus.TRANSCRIBING,
            transcript_text=None,
        )
        self.db.add_all([batch, job_done, job_failed, job_processing])
        self.db.commit()

        response = self.client.get(f"/api/v1/playlists/{batch_id}/export/zip")
        self.assertEqual(response.status_code, 200)

        zip_bytes = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("Transcripts/01 - Done Video.txt", namelist)
            self.assertEqual(len([f for f in namelist if f.startswith("Transcripts/")]), 1)

    def test_export_zip_sanitizes_special_characters_and_emojis(self):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL_CHARS",
            source_url="https://www.youtube.com/playlist?list=PL_CHARS",
            title="Crazy /: * ? <> | Title 🚀 — Em Dash",
            status=PlaylistStatus.COMPLETED,
            total_videos=1,
            completed_videos=1,
        )
        job = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_special",
            video_url="https://www.youtube.com/watch?v=v_special",
            title='Video With "Quotes" & Slashes / \\ ? * < > | and Emojis 🔥',
            position=0,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Special text.",
        )
        self.db.add_all([batch, job])
        self.db.commit()

        response = self.client.get(f"/api/v1/playlists/{batch_id}/export/zip")
        self.assertEqual(response.status_code, 200)

        zip_bytes = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_bytes, "r") as zf:
            namelist = zf.namelist()
            for filename in namelist:
                self.assertFalse(re.search(r'[\\*?:"<>|]', filename), f"Illegal char in filename: {filename}")


if __name__ == "__main__":
    unittest.main()

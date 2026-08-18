import io
import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("SESSION_SECRET", "test-secret-key-1234567890123456")
os.environ.setdefault("OPERATOR_PASSWORD", "testpassword123")

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
from backend.services.utils import verify_audio_file
from backend.services.ytdlp_classifier import (
    FailureClassification,
    FailureType,
    PermanentExtractionError,
    TransientExtractionError,
    classify_ytdlp_failure,
)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


class TestYtdlpClassification(unittest.TestCase):
    def test_classify_drm_errors(self):
        err1 = "WARNING: Some tv client https formats have been skipped as they are DRM protected. See https://github.com/yt-dlp/yt-dlp/issues/12563\nWARNING: This video is drm protected and only images are available for download\nERROR: Requested format is not available"
        c1 = classify_ytdlp_failure(err1)
        self.assertFalse(c1.is_retryable)
        self.assertEqual(c1.failure_type, FailureType.DRM_PROTECTED)
        self.assertIn("DRM-protected", c1.user_message)

        err2 = "This video is drm protected and only images are available for download"
        c2 = classify_ytdlp_failure(err2)
        self.assertFalse(c2.is_retryable)
        self.assertEqual(c2.failure_type, FailureType.DRM_PROTECTED)

    def test_classify_unavailable_videos(self):
        err = "ERROR: [youtube] 12345: Video unavailable. This video has been removed by the uploader"
        c = classify_ytdlp_failure(err)
        self.assertFalse(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.VIDEO_UNAVAILABLE)

        err_private = "ERROR: [youtube] abcde: Private video. Sign in if you've been granted access"
        c_priv = classify_ytdlp_failure(err_private)
        self.assertFalse(c_priv.is_retryable)
        self.assertEqual(c_priv.failure_type, FailureType.VIDEO_UNAVAILABLE)

    def test_classify_age_restricted(self):
        err = "ERROR: [youtube] xyz: Sign in to confirm your age. This video may be inappropriate for some users."
        c = classify_ytdlp_failure(err)
        self.assertFalse(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.AGE_RESTRICTED)

    def test_classify_geo_blocked(self):
        err = "ERROR: [youtube] geo1: The uploader has not made this video available in your country"
        c = classify_ytdlp_failure(err)
        self.assertFalse(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.GEO_BLOCKED)

    def test_classify_corrupt_audio(self):
        err = "Audio acquisition produced a corrupt file (346 bytes). No valid audio stream detected."
        c = classify_ytdlp_failure(err)
        self.assertFalse(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.CORRUPT_AUDIO)

    def test_classify_rate_limit(self):
        err = "WARNING: [youtube] Unable to download webpage: HTTP Error 429: Too Many Requests"
        c = classify_ytdlp_failure(err)
        self.assertTrue(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.RATE_LIMITED)

    def test_classify_session_reload(self):
        err = "ERROR: [youtube] The page needs to be reloaded. Please try again."
        c = classify_ytdlp_failure(err)
        self.assertTrue(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.SESSION_RELOAD)

    def test_classify_network_errors(self):
        err = "urllib.error.URLError: <urlopen error [Errno 110] Connection timed out>"
        c = classify_ytdlp_failure(err)
        self.assertTrue(c.is_retryable)
        self.assertEqual(c.failure_type, FailureType.NETWORK_ERROR)

    def test_classify_custom_exceptions(self):
        perm = PermanentExtractionError("DRM detected", failure_type=FailureType.DRM_PROTECTED, user_message="DRM block")
        c_perm = classify_ytdlp_failure(perm)
        self.assertFalse(c_perm.is_retryable)
        self.assertEqual(c_perm.failure_type, FailureType.DRM_PROTECTED)
        self.assertEqual(c_perm.user_message, "DRM block")

        trans = TransientExtractionError("Rate limit hit", failure_type=FailureType.RATE_LIMITED, user_message="Rate limit")
        c_trans = classify_ytdlp_failure(trans)
        self.assertTrue(c_trans.is_retryable)
        self.assertEqual(c_trans.failure_type, FailureType.RATE_LIMITED)


class TestAudioVerification(unittest.TestCase):
    def test_nonexistent_file(self):
        is_valid, reason = verify_audio_file(Path("/nonexistent/path/test.mp3"))
        self.assertFalse(is_valid)
        self.assertIn("does not exist", reason)

    def test_small_file_fails(self, tmp_path=None):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3") as tmp:
            tmp.write(b"ID3" + b"\x00" * 300)
            tmp.flush()
            is_valid, reason = verify_audio_file(Path(tmp.name), min_size=10_000)
            self.assertFalse(is_valid)
            self.assertIn("below the minimum threshold", reason)


class TestRetryEndpointAndClassificationAPI(unittest.TestCase):
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

    def test_job_read_includes_failure_classification(self):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL_TEST",
            source_url="https://www.youtube.com/playlist?list=PL_TEST",
            title="Test Batch",
            status=PlaylistStatus.PARTIAL,
            total_videos=2,
            completed_videos=1,
            failed_videos=1,
        )
        job1 = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_completed",
            video_url="https://www.youtube.com/watch?v=v_completed",
            title="Completed Video",
            position=0,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Completed audio text.",
            failure_type=None,
            is_retryable=True,
        )
        job2 = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_drm",
            video_url="https://www.youtube.com/watch?v=v_drm",
            title="DRM Video",
            position=1,
            status=TranscriptStatus.FAILED,
            stage_detail="DRM-protected — cannot be transcribed",
            failure_type="DRM_PROTECTED",
            is_retryable=False,
            error_log="DRM protected video stream",
        )
        self.db.add_all([batch, job1, job2])
        self.db.commit()

        response = self.client.get(f"/api/v1/playlists/{batch_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["jobs"]), 2)

        drm_job = next(j for j in data["jobs"] if j["video_id"] == "v_drm")
        self.assertEqual(drm_job["status"], "FAILED")
        self.assertEqual(drm_job["failure_type"], "DRM_PROTECTED")
        self.assertFalse(drm_job["is_retryable"])
        self.assertEqual(drm_job["stage_detail"], "DRM-protected — cannot be transcribed")

    @patch("backend.worker.tasks.transcribe_playlist_item.delay")
    def test_retry_failed_batch_skips_permanent_failures(self, mock_delay):
        batch_id = uuid.uuid4()
        batch = PlaylistBatch(
            id=batch_id,
            playlist_id="PL_RETRY",
            source_url="https://www.youtube.com/playlist?list=PL_RETRY",
            title="Retry Test Batch",
            status=PlaylistStatus.PARTIAL,
            total_videos=3,
            completed_videos=1,
            failed_videos=2,
        )
        job_done = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v1",
            video_url="https://www.youtube.com/watch?v=v1",
            title="Done Video",
            position=0,
            status=TranscriptStatus.COMPLETED,
            transcript_text="Text.",
        )
        job_perm_failed = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_drm",
            video_url="https://www.youtube.com/watch?v=v_drm",
            title="DRM Video",
            position=1,
            status=TranscriptStatus.FAILED,
            stage_detail="DRM-protected — cannot be transcribed",
            failure_type="DRM_PROTECTED",
            is_retryable=False,
        )
        job_trans_failed = TranscriptJob(
            id=uuid.uuid4(),
            playlist_batch_id=batch_id,
            video_id="v_rate",
            video_url="https://www.youtube.com/watch?v=v_rate",
            title="Rate Limited Video",
            position=2,
            status=TranscriptStatus.FAILED,
            stage_detail="Rate limited (429)",
            failure_type="RATE_LIMITED",
            is_retryable=True,
        )
        self.db.add_all([batch, job_done, job_perm_failed, job_trans_failed])
        self.db.commit()

        response = self.client.post(f"/api/v1/playlists/{batch_id}/retry-failed")
        self.assertEqual(response.status_code, 202)

        # Ensure only the transient job was queued for Celery retry
        mock_delay.assert_called_once_with(str(job_trans_failed.id))

        self.db.refresh(job_perm_failed)
        self.db.refresh(job_trans_failed)
        self.assertEqual(job_perm_failed.status, TranscriptStatus.FAILED)
        self.assertEqual(job_trans_failed.status, TranscriptStatus.PENDING)

    @patch("backend.worker.tasks.transcribe_playlist_item.delay")
    def test_single_job_retry_allows_forced_retry(self, mock_delay):
        job = TranscriptJob(
            id=uuid.uuid4(),
            video_id="v_single",
            video_url="https://www.youtube.com/watch?v=v_single",
            title="Single Video",
            position=0,
            status=TranscriptStatus.FAILED,
            stage_detail="DRM protected",
            failure_type="DRM_PROTECTED",
            is_retryable=False,
        )
        self.db.add(job)
        self.db.commit()

        response = self.client.post(f"/api/v1/transcripts/{job.id}/retry")
        self.assertEqual(response.status_code, 202)
        mock_delay.assert_called_once_with(str(job.id))

        self.db.refresh(job)
        self.assertEqual(job.status, TranscriptStatus.PENDING)
        self.assertIsNone(job.failure_type)
        self.assertTrue(job.is_retryable)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import dataclasses
from typing import Any


YOUTUBE_PLAYER_CLIENTS_ARG = (
    "youtube:player_client=web_embedded,android_creator,ios_creator,tv_embedded,android_music,ios_music,web_safari,web"
)


class FailureType:
    DRM_PROTECTED = "DRM_PROTECTED"
    VIDEO_UNAVAILABLE = "VIDEO_UNAVAILABLE"
    AGE_RESTRICTED = "AGE_RESTRICTED"
    GEO_BLOCKED = "GEO_BLOCKED"
    CORRUPT_AUDIO = "CORRUPT_AUDIO"
    RATE_LIMITED = "RATE_LIMITED"
    SESSION_RELOAD = "SESSION_RELOAD"
    NETWORK_ERROR = "NETWORK_ERROR"
    UNKNOWN_TRANSIENT = "UNKNOWN_TRANSIENT"
    UNKNOWN_PERMANENT = "UNKNOWN_PERMANENT"


@dataclasses.dataclass(frozen=True)
class FailureClassification:
    is_retryable: bool
    failure_type: str
    user_message: str
    technical_detail: str


class PermanentExtractionError(RuntimeError):
    """Raised when an extraction failure is permanent and should not be retried."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: str = FailureType.UNKNOWN_PERMANENT,
        user_message: str | None = None,
        technical_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.user_message = user_message or message
        self.technical_detail = technical_detail or message
        self.is_retryable = False


class TransientExtractionError(RuntimeError):
    """Raised when an extraction failure is temporary and can be retried."""

    def __init__(
        self,
        message: str,
        *,
        failure_type: str = FailureType.UNKNOWN_TRANSIENT,
        user_message: str | None = None,
        technical_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.user_message = user_message or message
        self.technical_detail = technical_detail or message
        self.is_retryable = True


def classify_ytdlp_failure(error_input: str | Exception) -> FailureClassification:
    """
    Inspects yt-dlp stderr output or python exception text to categorize
    the failure as either transient (retryable) or permanent (fail fast).
    """
    if isinstance(error_input, PermanentExtractionError):
        return FailureClassification(
            is_retryable=False,
            failure_type=error_input.failure_type,
            user_message=error_input.user_message,
            technical_detail=error_input.technical_detail,
        )
    if isinstance(error_input, TransientExtractionError):
        return FailureClassification(
            is_retryable=True,
            failure_type=error_input.failure_type,
            user_message=error_input.user_message,
            technical_detail=error_input.technical_detail,
        )

    text = str(error_input or "").lower().strip()
    original_text = str(error_input or "").strip()

    # 1. DRM Protection (Permanent)
    if (
        "drm protected" in text
        or "is drm protected" in text
        or ("drm" in text and "only images are available" in text)
        or "drm-protected" in text
        or "video is drm protected" in text
    ):
        return FailureClassification(
            is_retryable=False,
            failure_type=FailureType.DRM_PROTECTED,
            user_message="DRM-protected — cannot be transcribed",
            technical_detail=original_text[-400:],
        )

    # 2. Unavailable / Private / Deleted (Permanent)
    if (
        "video unavailable" in text
        or "this video is unavailable" in text
        or "private video" in text
        or "this video is private" in text
        or "this video has been removed" in text
        or "this video is not available" in text
        or "video has been deleted" in text
        or "account associated with this video has been terminated" in text
        or "sign in if you've been granted access" in text
        or "no video formats found" in text
        or "this video is only available to members" in text
    ):
        return FailureClassification(
            is_retryable=False,
            failure_type=FailureType.VIDEO_UNAVAILABLE,
            user_message="Video unavailable or deleted",
            technical_detail=original_text[-400:],
        )

    # 3. Age-Restricted / Sign In Required (Permanent)
    if (
        "sign in to confirm your age" in text
        or "confirm your age" in text
        or "inappropriate for some users" in text
        or "please sign in" in text
        or "use --cookies" in text
    ):
        return FailureClassification(
            is_retryable=False,
            failure_type=FailureType.AGE_RESTRICTED,
            user_message="Age-restricted content — requires sign in",
            technical_detail=original_text[-400:],
        )

    # 4. Geo-Blocked / Country Restricted (Permanent)
    if (
        "not available in your country" in text
        or "blocked it in your country" in text
        or "geo-restricted" in text
        or "uploader has not made this video available in your country" in text
    ):
        return FailureClassification(
            is_retryable=False,
            failure_type=FailureType.GEO_BLOCKED,
            user_message="Region-locked video — not available in this region",
            technical_detail=original_text[-400:],
        )

    # 5. Corrupt Audio / No Audio Stream (Permanent)
    if (
        "no valid audio stream" in text
        or "invalid data found when processing input" in text
        or "unplayable audio" in text
        or "corrupt file" in text
        or "empty mp3" in text
        or "0 bytes" in text
        or "audio acquisition produced a corrupt file" in text
        or "no audio stream found" in text
    ):
        return FailureClassification(
            is_retryable=False,
            failure_type=FailureType.CORRUPT_AUDIO,
            user_message="Corrupt audio — downloaded stream contains no audio data",
            technical_detail=original_text[-400:],
        )

    # 6. Rate Limiting (Retryable)
    if (
        "http error 429" in text
        or "429: too many requests" in text
        or "too many requests" in text
        or "rate limit" in text
    ):
        return FailureClassification(
            is_retryable=True,
            failure_type=FailureType.RATE_LIMITED,
            user_message="YouTube rate limit (HTTP 429) — temporary error, will retry",
            technical_detail=original_text[-400:],
        )

    # 7. Session Reload Hiccup (Retryable)
    if (
        "the page needs to be reloaded" in text
        or "page needs to be reloaded" in text
    ):
        return FailureClassification(
            is_retryable=True,
            failure_type=FailureType.SESSION_RELOAD,
            user_message="YouTube session hiccup — page reload required, will retry",
            technical_detail=original_text[-400:],
        )

    # 8. Network Connection Issues (Retryable)
    if (
        "connection reset" in text
        or "connection refused" in text
        or "timed out" in text
        or "timeout" in text
        or "network is unreachable" in text
        or "temporary failure in name resolution" in text
        or "remotedisconnected" in text
        or "http error 500" in text
        or "http error 502" in text
        or "http error 503" in text
        or "http error 504" in text
        or "ssl error" in text
    ):
        return FailureClassification(
            is_retryable=True,
            failure_type=FailureType.NETWORK_ERROR,
            user_message="Network error — will retry",
            technical_detail=original_text[-400:],
        )

    # Default to transient retryable error for unknown exceptions
    return FailureClassification(
        is_retryable=True,
        failure_type=FailureType.UNKNOWN_TRANSIENT,
        user_message=f"Temporary failure — {original_text[:80]}",
        technical_detail=original_text[-400:],
    )

from fastapi import Depends, HTTPException, Request, Response, status

from backend.core.config import get_settings
from backend.core.rate_limit import apply_rate_limit
from backend.models.schemas import AuthSessionRead


settings = get_settings()


def get_auth_session(request: Request) -> AuthSessionRead:
    session = request.session
    authenticated = bool(session.get("operator_authenticated"))
    warning = None
    if settings.operator_password.startswith("change-me"):
        warning = "Change `OPERATOR_PASSWORD` in `.env` before exposing this app beyond local development."
    return AuthSessionRead(
        authenticated=authenticated,
        username=session.get("operator_username") if authenticated else None,
        warning=warning,
    )


def require_operator(
    session: AuthSessionRead = Depends(get_auth_session),
) -> AuthSessionRead:
    if not session.authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in as the operator to access this resource.",
        )
    return session


def rate_limit(bucket: str, limit: int, window_seconds: int):
    def dependency(request: Request, response: Response) -> None:
        apply_rate_limit(
            request,
            response,
            bucket=bucket,
            limit=limit,
            window_seconds=window_seconds,
        )

    return dependency

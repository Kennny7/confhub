import secrets

from fastapi import Header, HTTPException, Request, status

from confhub.config import get_settings


async def require_api_access(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()

    # Allow loopback clients without a key when no key is configured.
    client_host = (request.client.host if request.client else "") or ""
    is_loopback = client_host in {"127.0.0.1", "::1", "localhost"}
    if not settings.api_key and is_loopback:
        return

    # Extract token from Authorization header if present.
    bearer_token: str | None = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization[7:].strip()

    candidate = x_api_key or bearer_token
    if settings.api_key and candidate and secrets.compare_digest(candidate, settings.api_key):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid API key",
    )

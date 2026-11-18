import hmac
import ipaddress

from fastapi import Header, HTTPException, Request, status

from meetbridge.config import get_settings


async def require_api_access(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    if settings.api_key:
        supplied_key = x_api_key or ""
        if authorization and authorization.lower().startswith("bearer "):
            supplied_key = authorization[7:].strip()
        if not hmac.compare_digest(supplied_key, settings.api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return

    client_host = request.client.host if request.client else ""
    try:
        is_loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set API_KEY before making this service available outside localhost",
        )

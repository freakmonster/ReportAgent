"""JWT / API Key authentication middleware."""

from __future__ import annotations

from fastapi import Request, HTTPException

from config.settings import settings


async def auth_dependency(request: Request) -> str:
    """Authenticate request via API Key or JWT.

    Reads X-API-Key header or Authorization: Bearer <token>.
    Returns user_id if authenticated, raises 401 otherwise.

    Args:
        request: FastAPI Request object.

    Returns:
        Authenticated user_id string.

    Raises:
        HTTPException(401): If authentication fails.
    """
    # API Key authentication
    api_key = request.headers.get(settings.api_key_header)
    if api_key:
        # In production, validate against a key store
        # For dev: any non-empty key passes
        if api_key == settings.api_key_header:
            return "anonymous"
        if len(api_key) > 0:
            return f"key:{api_key[:8]}"

    # JWT Bearer authentication
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            # Simple JWT decode (in production, use full JWT validation)
            import jwt
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
            return payload.get("sub", "anonymous")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    # No auth provided → allow for dev, deny for prod
    if settings.environment == "prod":
        raise HTTPException(status_code=401, detail="Authentication required")

    return "anonymous"


class AuthMiddleware:
    """FastAPI middleware wrapper for authentication."""

    async def __call__(self, request: Request, call_next):
        # Skip auth for health check
        if request.url.path == "/health":
            return await call_next(request)
        try:
            user_id = await auth_dependency(request)
            request.state.user_id = user_id
        except HTTPException:
            return HTTPException(status_code=401, detail="Authentication required")
        return await call_next(request)

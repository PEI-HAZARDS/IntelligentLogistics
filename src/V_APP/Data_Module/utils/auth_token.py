"""
Internal JWT token generation and validation.

KEYCLOAK: this module will be replaced by Keycloak token validation once
integrated. For now it issues and verifies minimal HS256 JWTs so auth is
structurally enforced end-to-end.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

_bearer = HTTPBearer(auto_error=True)


def generate_internal_jwt(sub: str, role: str) -> str:
    """
    Issue a signed HS256 JWT with sub, role, and exp claims.

    Parameters
    ----------
    sub : str
        Subject identifier (drivers_license or num_worker).
    role : str
        One of "driver", "operator", "manager".
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=settings.token_expiry_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_jwt(token: str) -> dict:
    """Decode and validate a JWT; raises HTTPException 401 on failure."""
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_claims(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """FastAPI dependency: validate Bearer token and return JWT claims.

    Also verifies that a server-side Redis session still exists for the
    ``(role, sub)`` pair, so deleting the session at logout (or letting it
    expire) effectively revokes the JWT even before its ``exp``.
    """
    claims = verify_jwt(credentials.credentials)
    role = claims.get("role")
    sub = claims.get("sub")
    if role and sub:
        # Local import to avoid pulling redis at module import time (test isolation).
        from infrastructure.persistence.redis import get_session
        try:
            session = get_session(role, sub)
        except Exception:
            if not settings.redis_auth_fail_open:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Auth service temporarily unavailable",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            session = True  # fail-open: proceed with JWT-only validation
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session revoked or expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return claims


def require_role(*allowed_roles: str):
    """Return a FastAPI dependency that enforces one of the given roles."""

    def _dep(
        claims: Annotated[dict, Depends(get_current_claims)],
    ) -> dict:
        if claims.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{claims.get('role')}' not permitted for this endpoint",
            )
        return claims

    return _dep

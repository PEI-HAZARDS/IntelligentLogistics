"""
Internal JWT token generation.

KEYCLOAK: this module will be replaced by Keycloak token validation once
integrated. For now it issues minimal HS256 JWTs so the driver and worker
login flows return structurally valid tokens end-to-end.
"""

from datetime import datetime, timedelta, timezone

import jwt

from config import settings


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

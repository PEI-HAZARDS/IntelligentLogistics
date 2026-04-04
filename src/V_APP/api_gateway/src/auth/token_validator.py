"""
JWT token validation using Keycloak's RS256 public keys.

Provides FastAPI dependencies for extracting and validating the current user
from a Bearer token, and for enforcing role-based access control.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable

import jwt
from jwt import PyJWKClient, PyJWK
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

logger = logging.getLogger("TokenValidator")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/workers/login", auto_error=False)


@dataclass
class TokenPayload:
    """Decoded JWT claims relevant to the application."""

    sub: str                          # Subject (email or drivers_license)
    roles: list[str] = field(default_factory=list)        # Realm roles
    client_roles: list[str] = field(default_factory=list)  # Client roles (access_level_*)


class TokenValidator:
    """
    Validates Keycloak-issued JWTs using the realm's JWKS endpoint.

    Instantiate once at app startup and store on app.state.
    """

    def __init__(self, jwks_url: str, issuer: str, audience: str | None = None) -> None:
        self._jwks_client = PyJWKClient(jwks_url, cache_keys=True)
        self._issuer = issuer
        self._audience = audience
        self._algorithms = ["RS256"]

    def decode(self, token: str) -> TokenPayload:
        """Decode and validate a JWT, returning a TokenPayload."""
        try:
            # Debug: log token header to diagnose kid mismatch
            try:
                header = jwt.get_unverified_header(token)
                logger.debug("JWT header: alg=%s kid=%s", header.get("alg"), header.get("kid"))
            except Exception:
                logger.warning("Could not decode JWT header from token (len=%d): %.40s...", len(token), token)

            signing_key: PyJWK = self._jwks_client.get_signing_key_from_jwt(token)
        except Exception as exc:
            logger.warning("JWKS key lookup failed: %s (jwks_url=%s)", exc, self._jwks_client.uri)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate token signature",
                headers={"WWW-Authenticate": "Bearer"},
            )

        decode_options = {
            "verify_exp": True,
            "verify_iss": True,
            "verify_aud": self._audience is not None,
        }

        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=self._algorithms,
                issuer=self._issuer,
                audience=self._audience,
                options=decode_options,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as exc:
            logger.warning("Token validation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Extract realm roles from Keycloak's standard claim structure
        realm_access = payload.get("realm_access", {})
        realm_roles = realm_access.get("roles", [])

        # Extract client roles for api-gateway
        resource_access = payload.get("resource_access", {})
        client_access = resource_access.get("api-gateway", {})
        client_roles = client_access.get("roles", [])

        # Use preferred_username as the application identity (email for workers,
        # drivers_license for drivers). Fall back to sub (Keycloak UUID) if missing.
        identity = payload.get("preferred_username", payload.get("sub", ""))

        return TokenPayload(
            sub=identity,
            roles=realm_roles,
            client_roles=client_roles,
        )


# ------------------------------------------------------------------ #
# FastAPI dependencies
# ------------------------------------------------------------------ #

async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> TokenPayload:
    """
    FastAPI dependency that extracts and validates the Bearer token.
    Returns the decoded TokenPayload.
    """
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    validator: TokenValidator = request.app.state.token_validator
    return validator.decode(token)


def require_role(*allowed_roles: str) -> Callable:
    """
    Factory that returns a FastAPI dependency enforcing role membership.

    Usage:
        @router.get("/some-endpoint")
        async def endpoint(user: TokenPayload = Depends(require_role("operator", "manager"))):
            ...
    """

    async def _check_role(
        current_user: TokenPayload = Depends(get_current_user),
    ) -> TokenPayload:
        user_roles = set(current_user.roles)
        if not user_roles.intersection(allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(allowed_roles)}",
            )
        return current_user

    return _check_role


def validate_ws_token(request: Request, token: str) -> TokenPayload:
    """
    Validate a token passed as a WebSocket query parameter.
    Synchronous wrapper for WebSocket handlers.
    """
    validator: TokenValidator = request.app.state.token_validator
    return validator.decode(token)

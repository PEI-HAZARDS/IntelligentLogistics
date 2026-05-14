"""
Auth Router — Keycloak-mediated authentication endpoints.

All login/refresh/logout flows are handled here. The frontends send
credentials to these endpoints; the API Gateway exchanges them with
Keycloak behind the scenes and returns standard OIDC tokens.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from clients import internal_api_client as internal_client
from auth.keycloak_client import KeycloakClient

router = APIRouter(prefix="/auth", tags=["auth"])


# ==================== REQUEST / RESPONSE MODELS ====================

class WorkerLoginRequest(BaseModel):
    email: str
    password: str


class DriverLoginRequest(BaseModel):
    drivers_license: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


# ==================== HELPERS ====================

def _get_keycloak(request: Request) -> KeycloakClient:
    return request.app.state.keycloak_client


# ==================== ENDPOINTS ====================

@router.post("/workers/login")
async def worker_login(credentials: WorkerLoginRequest, request: Request):
    """
    Worker (operator/manager) login.

    1. Exchange credentials with Keycloak (ROPC).
    2. Fetch worker profile from the Data Module.
    3. Return tokens + user info.
    """
    kc = _get_keycloak(request)

    # Authenticate against Keycloak
    token_data = await kc.exchange_credentials(credentials.email, credentials.password)

    # Fetch worker profile from Data Module
    try:
        user_info = await internal_client.get(f"/workers/by-email/{credentials.email}")
    except HTTPException:
        # If the profile lookup fails, still return tokens (user exists in KC but maybe not yet in DM)
        user_info = {"email": credentials.email}

    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_in": token_data.get("expires_in"),
        "token_type": token_data.get("token_type", "Bearer"),
        "user_info": user_info,
    }


@router.post("/drivers/login")
async def driver_login(credentials: DriverLoginRequest, request: Request):
    """
    Driver login (mobile app).

    1. Exchange credentials with Keycloak (ROPC).
    2. Fetch driver profile from the Data Module.
    3. Return tokens + user info.
    """
    kc = _get_keycloak(request)

    # Authenticate against Keycloak
    token_data = await kc.exchange_credentials(credentials.drivers_license, credentials.password)

    # Fetch driver profile from Data Module
    try:
        user_info = await internal_client.get(f"/drivers/{credentials.drivers_license}")
    except HTTPException:
        user_info = {"drivers_license": credentials.drivers_license}

    # Create a DM internal session so /me/* endpoints work via the gateway.
    # Non-fatal: Keycloak auth is authoritative; DM session is a warm-up detail.
    try:
        await internal_client.post("/drivers/login", json={
            "drivers_license": credentials.drivers_license,
            "password": credentials.password,
        })
    except HTTPException:
        pass

    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_in": token_data.get("expires_in"),
        "token_type": token_data.get("token_type", "Bearer"),
        "user_info": user_info,
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request):
    """Exchange a refresh token for a new token pair."""
    kc = _get_keycloak(request)
    token_data = await kc.refresh_token(body.refresh_token)

    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_in": token_data.get("expires_in"),
        "token_type": token_data.get("token_type", "Bearer"),
    }


@router.post("/logout")
async def logout(body: LogoutRequest, request: Request):
    """Revoke the refresh token, ending the Keycloak session."""
    kc = _get_keycloak(request)
    await kc.logout(body.refresh_token)
    return {"detail": "Logged out successfully"}

"""
Keycloak REST API client for the API Gateway.

Handles credential exchange (ROPC), token refresh, logout,
and user management via the Admin REST API.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException, status

logger = logging.getLogger("KeycloakClient")


@dataclass
class KeycloakClient:
    """Thin wrapper around Keycloak's OpenID Connect and Admin REST endpoints."""

    server_url: str        # e.g. http://keycloak:8080
    realm: str             # e.g. intelligent-logistics
    client_id: str         # e.g. api-gateway
    client_secret: str     # confidential client secret

    # ------------------------------------------------------------------ #
    # Derived URLs
    # ------------------------------------------------------------------ #

    @property
    def _token_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token"

    @property
    def _logout_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/logout"

    @property
    def _jwks_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/certs"

    @property
    def _admin_base(self) -> str:
        return f"{self.server_url}/admin/realms/{self.realm}"

    # ------------------------------------------------------------------ #
    # Token operations (OpenID Connect)
    # ------------------------------------------------------------------ #

    async def exchange_credentials(self, username: str, password: str) -> dict[str, Any]:
        """
        Exchange user credentials for tokens using the Resource Owner Password
        Credentials (Direct Access Grants) flow.

        Returns the full Keycloak token response:
        {access_token, refresh_token, expires_in, token_type, ...}
        """
        payload = {
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": username,
            "password": password,
            "scope": "openid",
        }
        return await self._post_token(payload)

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        """Exchange a refresh token for a new token pair."""
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        return await self._post_token(payload)

    async def logout(self, refresh_token: str) -> None:
        """Revoke a refresh token (end the Keycloak session)."""
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(self._logout_url, data=payload)
        if resp.status_code >= 400:
            logger.warning("Keycloak logout returned %s: %s", resp.status_code, resp.text)

    # ------------------------------------------------------------------ #
    # Admin REST API — user management
    # ------------------------------------------------------------------ #

    async def _get_admin_token(self) -> str:
        """Obtain a service-account token for Admin REST API calls."""
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        data = await self._post_token(payload)
        return data["access_token"]

    async def create_user(
        self,
        username: str,
        password_hash: str | None = None,
        email: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        realm_roles: list[str] | None = None,
        client_roles: list[str] | None = None,
        enabled: bool = True,
    ) -> str:
        """
        Create a user in Keycloak. Optionally imports a bcrypt password hash
        so existing users keep their current password.

        Returns the new user's Keycloak ID.
        """
        admin_token = await self._get_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        user_repr: dict[str, Any] = {
            "username": username,
            "enabled": enabled,
            "emailVerified": True,
        }
        if email:
            user_repr["email"] = email
        if first_name:
            user_repr["firstName"] = first_name
        if last_name:
            user_repr["lastName"] = last_name

        # Import bcrypt hash directly so users keep their existing password
        if password_hash:
            user_repr["credentials"] = [
                {
                    "type": "password",
                    "hashedSaltedValue": password_hash,
                    "algorithm": "bcrypt",
                    "hashIterations": 0,
                    "temporary": False,
                }
            ]

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._admin_base}/users",
                json=user_repr,
                headers=headers,
            )

        if resp.status_code == 409:
            logger.info("User %s already exists in Keycloak, skipping", username)
            return await self._get_user_id(username, headers)

        if resp.status_code not in (200, 201):
            logger.error("Failed to create user %s: %s %s", username, resp.status_code, resp.text)
            raise HTTPException(status_code=502, detail=f"Keycloak user creation failed: {resp.text}")

        user_id = await self._get_user_id(username, headers)

        # Assign realm roles
        if realm_roles:
            await self._assign_realm_roles(user_id, realm_roles, headers)

        # Assign client roles
        if client_roles:
            await self._assign_client_roles(user_id, client_roles, headers)

        return user_id

    async def _get_user_id(self, username: str, headers: dict[str, str]) -> str:
        """Look up a user by username and return their Keycloak ID."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{self._admin_base}/users",
                params={"username": username, "exact": "true"},
                headers=headers,
            )
        users = resp.json()
        if not users:
            raise HTTPException(status_code=404, detail=f"User {username} not found in Keycloak")
        return users[0]["id"]

    async def _assign_realm_roles(
        self, user_id: str, role_names: list[str], headers: dict[str, str]
    ) -> None:
        """Assign realm-level roles to a user."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Fetch available realm roles
            resp = await client.get(f"{self._admin_base}/roles", headers=headers)
            all_roles = resp.json()
            role_map = {r["name"]: r for r in all_roles}

            roles_to_assign = [role_map[name] for name in role_names if name in role_map]
            if roles_to_assign:
                await client.post(
                    f"{self._admin_base}/users/{user_id}/role-mappings/realm",
                    json=roles_to_assign,
                    headers=headers,
                )

    async def _assign_client_roles(
        self, user_id: str, role_names: list[str], headers: dict[str, str]
    ) -> None:
        """Assign client-level roles (on the api-gateway client) to a user."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get the internal ID of the api-gateway client
            resp = await client.get(
                f"{self._admin_base}/clients",
                params={"clientId": self.client_id},
                headers=headers,
            )
            clients = resp.json()
            if not clients:
                logger.warning("Client %s not found, skipping client role assignment", self.client_id)
                return
            client_internal_id = clients[0]["id"]

            # Fetch available client roles
            resp = await client.get(
                f"{self._admin_base}/clients/{client_internal_id}/roles",
                headers=headers,
            )
            all_roles = resp.json()
            role_map = {r["name"]: r for r in all_roles}

            roles_to_assign = [role_map[name] for name in role_names if name in role_map]
            if roles_to_assign:
                await client.post(
                    f"{self._admin_base}/users/{user_id}/role-mappings/clients/{client_internal_id}",
                    json=roles_to_assign,
                    headers=headers,
                )

    # ------------------------------------------------------------------ #
    # JWKS (for token_validator startup)
    # ------------------------------------------------------------------ #

    async def fetch_jwks(self) -> dict[str, Any]:
        """Fetch the realm's JSON Web Key Set for token verification."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self._jwks_url)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch JWKS from Keycloak: {resp.status_code}")
        return resp.json()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _post_token(self, payload: dict[str, str]) -> dict[str, Any]:
        """POST to the token endpoint, raising appropriate HTTP errors."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._token_url, data=payload)
        except httpx.RequestError as exc:
            logger.error("Keycloak connection error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not reach identity provider",
            )

        if resp.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        if resp.status_code >= 400:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            logger.error("Keycloak token error %s: %s", resp.status_code, error_body)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Identity provider error: {error_body}",
            )

        return resp.json()

#!/usr/bin/env python3
"""
Keycloak User Sync Script

Reads all workers and drivers from PostgreSQL and creates corresponding
users in Keycloak. Imports bcrypt password hashes so users keep their
existing passwords. Idempotent — skips users that already exist.

Usage:
    python sync_users.py

Environment variables (read from .env or set directly):
    DATABASE_URL         — PostgreSQL connection string
    KEYCLOAK_URL         — e.g. http://keycloak:8080
    KEYCLOAK_REALM       — e.g. intelligent-logistics
    KEYCLOAK_CLIENT_ID   — e.g. api-gateway
    KEYCLOAK_CLIENT_SECRET — confidential client secret
"""

import os
import sys
import logging
from pathlib import Path

import httpx
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sync_users")

# Load .env from parent directory if present
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://pei_user:peiHazards**@localhost:5432/IntelligentLogistics")
KC_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8443")
KC_REALM = os.getenv("KEYCLOAK_REALM", "intelligent-logistics")
KC_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "api-gateway")
KC_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "api-gateway-secret")
KC_ADMIN_USER = os.getenv("KC_ADMIN_USER", "admin")
KC_ADMIN_PASSWORD = os.getenv("KC_ADMIN_PASSWORD", "admin")


def get_admin_token() -> str:
    """Obtain an admin token from Keycloak's master realm."""
    url = f"{KC_URL}/realms/master/protocol/openid-connect/token"
    resp = httpx.post(url, data={
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": KC_ADMIN_USER,
        "password": KC_ADMIN_PASSWORD,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_kc_user(
    token: str,
    username: str,
    password: str,
    email: str | None = None,
    first_name: str | None = None,
    realm_roles: list[str] | None = None,
    client_roles: list[str] | None = None,
) -> None:
    """Create a single user in Keycloak."""
    admin_base = f"{KC_URL}/admin/realms/{KC_REALM}"
    headers = {"Authorization": f"Bearer {token}"}

    user_repr = {
        "username": username,
        "enabled": True,
        "emailVerified": True,
    }
    if email:
        user_repr["email"] = email
    if first_name:
        user_repr["firstName"] = first_name

    # Create user
    resp = httpx.post(f"{admin_base}/users", json=user_repr, headers=headers)
    if resp.status_code == 409:
        logger.info("  User '%s' already exists, skipping", username)
        return
    if resp.status_code not in (200, 201):
        logger.error("  Failed to create '%s': %s %s", username, resp.status_code, resp.text)
        return

    # Get user ID
    resp = httpx.get(f"{admin_base}/users", params={"username": username, "exact": "true"}, headers=headers)
    users = resp.json()
    if not users:
        logger.error("  Could not find user '%s' after creation", username)
        return
    user_id = users[0]["id"]

    # Set password via reset-password endpoint
    resp = httpx.put(
        f"{admin_base}/users/{user_id}/reset-password",
        json={"type": "password", "value": password, "temporary": False},
        headers=headers,
    )
    if resp.status_code not in (200, 204):
        logger.error("  Failed to set password for '%s': %s %s", username, resp.status_code, resp.text)

    # Assign realm roles
    if realm_roles:
        resp = httpx.get(f"{admin_base}/roles", headers=headers)
        all_roles = {r["name"]: r for r in resp.json()}
        roles_to_assign = [all_roles[r] for r in realm_roles if r in all_roles]
        if roles_to_assign:
            httpx.post(
                f"{admin_base}/users/{user_id}/role-mappings/realm",
                json=roles_to_assign,
                headers=headers,
            )

    # Assign client roles
    if client_roles:
        resp = httpx.get(f"{admin_base}/clients", params={"clientId": KC_CLIENT_ID}, headers=headers)
        clients = resp.json()
        if clients:
            client_internal_id = clients[0]["id"]
            resp = httpx.get(f"{admin_base}/clients/{client_internal_id}/roles", headers=headers)
            all_client_roles = {r["name"]: r for r in resp.json()}
            roles_to_assign = [all_client_roles[r] for r in client_roles if r in all_client_roles]
            if roles_to_assign:
                httpx.post(
                    f"{admin_base}/users/{user_id}/role-mappings/clients/{client_internal_id}",
                    json=roles_to_assign,
                    headers=headers,
                )

    logger.info("  Created '%s' with roles %s %s", username, realm_roles, client_roles or [])


def sync_workers(conn, token: str) -> int:
    """Sync all active workers to Keycloak."""
    count = 0
    with conn.cursor() as cur:
        # Workers with their role (operator or manager)
        cur.execute("""
            SELECT w.num_worker, w.name, w.email,
                   CASE WHEN m.num_worker IS NOT NULL THEN 'manager' ELSE 'operator' END AS role,
                   m.access_level
            FROM worker w
            LEFT JOIN manager m ON m.num_worker = w.num_worker
            LEFT JOIN operator o ON o.num_worker = w.num_worker
            WHERE w.active = true
        """)
        for row in cur.fetchall():
            num_worker, name, email, role, access_level = row
            logger.info("Syncing worker: %s (%s) — %s", email, num_worker, role)

            realm_roles = [role]
            client_roles = []
            if role == "manager" and access_level:
                client_roles.append(f"access_level_{access_level}")

            create_kc_user(
                token=token,
                username=email,
                password="password123",
                email=email,
                first_name=name,
                realm_roles=realm_roles,
                client_roles=client_roles,
            )
            count += 1
    return count


def sync_drivers(conn, token: str) -> int:
    """Sync all active drivers to Keycloak."""
    count = 0
    with conn.cursor() as cur:
        cur.execute("""
            SELECT d.drivers_license, d.name
            FROM driver d
            WHERE d.active = true
        """)
        for row in cur.fetchall():
            drivers_license, name = row
            logger.info("Syncing driver: %s (%s)", name, drivers_license)

            create_kc_user(
                token=token,
                username=drivers_license,
                password="driver123",
                first_name=name,
                realm_roles=["driver"],
            )
            count += 1
    return count


def main():
    logger.info("Connecting to PostgreSQL: %s", DATABASE_URL.split("@")[-1])
    conn = psycopg2.connect(DATABASE_URL)

    logger.info("Obtaining Keycloak admin token from %s", KC_URL)
    token = get_admin_token()

    logger.info("--- Syncing Workers ---")
    worker_count = sync_workers(conn, token)

    logger.info("--- Syncing Drivers ---")
    driver_count = sync_drivers(conn, token)

    conn.close()
    logger.info("Done! Synced %d workers + %d drivers = %d total", worker_count, driver_count, worker_count + driver_count)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Shared bootstrap for data seed scripts.

Provides:
  _hash(pw)                       — bcrypt helper
  _sync_to_keycloak(db)           — Keycloak user provisioning
  create_and_seed(url, mode)      — engine setup + dispatch to init_*_data
  __main__                        — entry point (--mode trial|demo or DATA_INIT_MODE)
"""

import os
import sys

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from Data_Module.models.sql_models import Base, Driver, Manager, Worker
except Exception:
    try:
        from infrastructure.persistence.sql_models import Base, Driver, Manager, Worker
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _sync_to_keycloak(db) -> None:
    kc_url = os.getenv("KEYCLOAK_URL", "")
    kc_admin_pw = os.getenv("KC_ADMIN_PASSWORD", "")
    if not kc_url or not kc_admin_pw:
        print("\n  [KC-SYNC] KEYCLOAK_URL / KC_ADMIN_PASSWORD not set — skipping."
              "\n  Run 'docker-compose run --rm keycloak-sync' manually after seeding.")
        return

    try:
        import httpx as _httpx
    except ImportError:
        print("\n  [KC-SYNC] httpx not installed — skipping Keycloak sync.")
        return

    kc_realm = os.getenv("KEYCLOAK_REALM", "intelligent-logistics")
    kc_admin_user = os.getenv("KC_ADMIN_USER", "admin")
    worker_pw = os.getenv("DEFAULT_WORKER_PASSWORD", "password123")
    driver_pw = os.getenv("DEFAULT_DRIVER_PASSWORD", "driver123")

    print(f"\n  [KC-SYNC] Syncing users to {kc_url} realm '{kc_realm}'...")
    try:
        r = _httpx.post(
            f"{kc_url}/realms/master/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli",
                  "username": kc_admin_user, "password": kc_admin_pw},
            timeout=15.0,
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    except Exception as exc:
        print(f"\n  [KC-SYNC] Cannot reach Keycloak ({exc}) — skipping sync.")
        return

    admin_base = f"{kc_url}/admin/realms/{kc_realm}"
    headers = {"Authorization": f"Bearer {token}"}
    synced = 0

    def _assign_realm_roles(user_id: str, role_names: list) -> None:
        r2 = _httpx.get(f"{admin_base}/roles", headers=headers, timeout=10.0)
        role_map = {ro["name"]: ro for ro in r2.json()}
        roles = [role_map[rn] for rn in role_names if rn in role_map]
        if roles:
            _httpx.post(f"{admin_base}/users/{user_id}/role-mappings/realm",
                        json=roles, headers=headers, timeout=10.0)

    def _upsert(username: str, password: str, email: str | None = None,
                first_name: str | None = None, realm_roles: list | None = None) -> None:
        nonlocal synced
        body: dict = {"username": username, "enabled": True, "emailVerified": True}
        if email:
            body["email"] = email
        if first_name:
            body["firstName"] = first_name
        r2 = _httpx.post(f"{admin_base}/users", json=body, headers=headers, timeout=10.0)
        if r2.status_code == 409:
            return
        if r2.status_code not in (200, 201):
            print(f"  [KC-SYNC] Failed to create '{username}': {r2.status_code} {r2.text[:80]}")
            return
        r3 = _httpx.get(f"{admin_base}/users", params={"username": username, "exact": "true"},
                        headers=headers, timeout=10.0)
        users = r3.json()
        if not users:
            return
        user_id = users[0]["id"]
        _httpx.put(f"{admin_base}/users/{user_id}/reset-password",
                   json={"type": "password", "value": password, "temporary": False},
                   headers=headers, timeout=10.0)
        if realm_roles:
            _assign_realm_roles(user_id, realm_roles)
        synced += 1

    for w in db.query(Worker).filter_by(active=True).all():
        role = "manager" if w.manager else "operator"
        _upsert(w.email, worker_pw, email=w.email, first_name=w.name, realm_roles=[role])

    for d in db.query(Driver).filter_by(active=True).all():
        _upsert(d.drivers_license, driver_pw, first_name=d.name, realm_roles=["driver"])

    print(f"  [KC-SYNC] Done — {synced} user(s) provisioned in Keycloak.")


def create_and_seed(database_url: str, mode: str = "demo") -> None:
    if mode == "trial":
        from data_init_trial import init_trial_data as _init
    elif mode == "demo":
        from data_init_demo import init_demo_data as _init
    else:
        raise ValueError(f"Unknown mode '{mode}'. Use 'trial' or 'demo'.")

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        _init(db)
        _sync_to_keycloak(db)
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed the database with demo or trial data.")
    parser.add_argument(
        "--mode", choices=["demo", "trial"],
        default=os.getenv("DATA_INIT_MODE", "demo"),
        help="Seed mode: 'demo' (full rich dataset) or 'trial' (minimal live demo). "
             "Also read from DATA_INIT_MODE env var.",
    )
    args = parser.parse_args()

    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    print(f"\n  Connecting to: {DATABASE_URL}")
    print(f"  Mode: {args.mode}\n")
    create_and_seed(DATABASE_URL, mode=args.mode)

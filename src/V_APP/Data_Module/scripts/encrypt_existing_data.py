"""
RGPD migration: encrypt existing plaintext PII columns in PostgreSQL.

Run ONCE after setting ENCRYPTION_KEY in the environment.
Safe to re-run — already-encrypted rows are detected via the base64url prefix
and skipped (the GCM decrypt would raise on a plaintext value that happens to
be valid base64, but the AAD mismatch prevents false positives).

Usage:
    ENCRYPTION_KEY=<key> PYTHONPATH=. python scripts/encrypt_existing_data.py

Generate a key:
    python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
"""

from __future__ import annotations

import logging
import sys

from infrastructure.persistence.postgres import SessionLocal
from infrastructure.persistence.sql_models import Driver, Worker
from utils.crypto_utils import encrypt, encrypt_deterministic, decrypt

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _is_encrypted(value: str) -> bool:
    """Heuristic: encrypted tokens are base64url and long enough to hold nonce+tag."""
    if not value or len(value) < 40:
        return False
    try:
        decrypt(value)
        return True
    except Exception:
        return False


def migrate_workers(session) -> tuple[int, int]:
    skipped = 0
    updated = 0
    for worker in session.query(Worker).all():
        changed = False
        if worker.email and not _is_encrypted(worker.email):
            worker.email = encrypt_deterministic(worker.email)  # searchable — deterministic nonce
            changed = True
        if worker.phone and not _is_encrypted(worker.phone):
            worker.phone = encrypt(worker.phone)  # non-searchable — random nonce
            changed = True
        if changed:
            updated += 1
        else:
            skipped += 1
    return updated, skipped


def migrate_drivers(session) -> tuple[int, int]:
    skipped = 0
    updated = 0
    for driver in session.query(Driver).all():
        if driver.mobile_device_token and not _is_encrypted(driver.mobile_device_token):
            driver.mobile_device_token = encrypt(driver.mobile_device_token)
            updated += 1
        else:
            skipped += 1
    return updated, skipped


def main() -> None:
    session = SessionLocal()
    try:
        logger.info("Migrating Worker.email and Worker.phone …")
        w_updated, w_skipped = migrate_workers(session)
        logger.info("  workers: %d updated, %d already encrypted/skipped", w_updated, w_skipped)

        logger.info("Migrating Driver.mobile_device_token …")
        d_updated, d_skipped = migrate_drivers(session)
        logger.info("  drivers: %d updated, %d already encrypted/skipped", d_updated, d_skipped)

        session.commit()
        logger.info("Migration committed successfully.")
    except Exception as exc:
        session.rollback()
        logger.exception("Migration failed, rolled back")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()

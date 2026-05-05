"""
AES-256-GCM application-level field encryption for RGPD-sensitive columns.

Key lifecycle:
  - ENCRYPTION_KEY env var: base64url-encoded 32-byte key (256 bits).
  - Generate with: python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  - Rotate keys by re-running scripts/encrypt_existing_data.py with the new key.

Two TypeDecorators are provided:

  EncryptedString (random nonce)
    - Random 12-byte nonce per write → identical plaintexts produce different
      ciphertexts.  Use for fields that are NEVER searched or compared in SQL
      (e.g. phone, mobile_device_token).  Cannot be used with UNIQUE constraints
      or WHERE clauses, because every encryption is unique.

  SearchableEncryptedString (deterministic nonce)
    - Nonce = HMAC-SHA256(key, plaintext)[:12] → identical plaintexts produce
      identical ciphertexts.  Use for fields that must support equality queries
      or DB-level UNIQUE constraints (e.g. email used for login).
    - Trade-off: an observer with access to the ciphertext column can detect
      whether two rows share the same value (frequency analysis).  Acceptable
      for academic demo; for production use a blind-index table instead.

Wire format (both variants): base64url( nonce || ciphertext || GCM-tag )
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

_KEY_ENV = "ENCRYPTION_KEY"
_NONCE_BYTES = 12  # 96-bit nonce recommended for AES-GCM
_AAD = b"intelligent-logistics-v1"  # additional authenticated data (version tag)


def _load_key() -> bytes:
    """Load and validate the 32-byte encryption key (env var or settings)."""
    raw = os.environ.get(_KEY_ENV, "")
    if not raw:
        # Fallback to pydantic settings (avoids circular import at module level)
        try:
            from config import settings  # noqa: PLC0415
            raw = settings.encryption_key
        except Exception:
            pass
    if not raw:
        raise RuntimeError(
            f"[RGPD] {_KEY_ENV} is not set. "
            "Generate with: python -c \"import secrets,base64; "
            "print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())\""
        )
    key = base64.urlsafe_b64decode(raw + "==")  # lenient padding
    if len(key) != 32:
        raise ValueError(f"[RGPD] {_KEY_ENV} must decode to exactly 32 bytes, got {len(key)}")
    return key


def encrypt(plaintext: str) -> str:
    """
    Encrypt *plaintext* with AES-256-GCM using a random nonce.
    Returns a base64url string: nonce || ciphertext || tag.
    Use for non-searchable fields (phone, device token).
    """
    key = _load_key()
    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode(), _AAD)
    blob = nonce + ciphertext_and_tag
    return base64.urlsafe_b64encode(blob).decode()


def encrypt_deterministic(plaintext: str) -> str:
    """
    Encrypt *plaintext* with AES-256-GCM using a deterministic nonce derived
    from HMAC-SHA256(key, plaintext)[:12].  Identical plaintexts always produce
    the same ciphertext, so DB UNIQUE constraints and WHERE-equality queries work.
    Use only for searchable fields (email).
    """
    key = _load_key()
    nonce = hmac.new(key, plaintext.encode(), hashlib.sha256).digest()[:_NONCE_BYTES]
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext.encode(), _AAD)
    blob = nonce + ciphertext_and_tag
    return base64.urlsafe_b64encode(blob).decode()


def decrypt(token: str) -> str:
    """
    Decrypt a token produced by :func:`encrypt`.
    Raises ``ValueError`` on authentication failure (tampered data).
    """
    key = _load_key()
    blob = base64.urlsafe_b64decode(token + "==")
    nonce = blob[:_NONCE_BYTES]
    ciphertext_and_tag = blob[_NONCE_BYTES:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext_and_tag, _AAD).decode()


# ---------------------------------------------------------------------------
# SQLAlchemy TypeDecorator — transparent encryption at the ORM boundary
# ---------------------------------------------------------------------------

def _safe_decrypt(value: str, label: str) -> str:
    """Decrypt *value*, returning the raw string on failure (pre-migration rows)."""
    try:
        return decrypt(value)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "%s: failed to decrypt — row may be unmigrated. "
            "Run scripts/encrypt_existing_data.py.", label
        )
        return value


class EncryptedString(TypeDecorator):
    """
    Random-nonce AES-256-GCM encryption.  Use for non-searchable PII fields
    (phone, mobile_device_token).  Cannot be used with UNIQUE constraints or
    WHERE-equality queries — each write produces a unique ciphertext.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _safe_decrypt(value, "EncryptedString")


class SearchableEncryptedString(TypeDecorator):
    """
    Deterministic-nonce AES-256-GCM encryption.  Use for PII fields that must
    support equality queries or DB UNIQUE constraints (e.g. Worker.email).
    Nonce = HMAC-SHA256(key, plaintext)[:12] — same input → same ciphertext.

    Trade-off: frequency analysis is possible (an observer can detect equal
    values).  Acceptable for the academic demo; use a blind-index in production.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_deterministic(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _safe_decrypt(value, "SearchableEncryptedString")

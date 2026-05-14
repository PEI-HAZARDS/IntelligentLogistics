"""
Unit tests for Phase 2 auth gap fixes.

Covers:
  - verify_jwt: valid token decodes correctly
  - verify_jwt: expired token raises 401
  - verify_jwt: tampered token raises 401
  - require_role: correct role passes; wrong role raises 403
  - Redis session helpers: set/get/delete round-trip

Note: HTTP-level 401/403 assertions belong in integration tests that can
load the full FastAPI app with all dependencies available.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest


# ---------------------------------------------------------------------------
# verify_jwt / require_role (unit — no HTTP)
# ---------------------------------------------------------------------------

class TestVerifyJWT:
    _SECRET = "test-jwt-secret-for-unit-testing-only!"  # ≥32 bytes — avoids InsecureKeyLengthWarning

    def _token(self, payload_override=None, secret=None):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "AB-12-CD",
            "role": "driver",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        if payload_override:
            payload.update(payload_override)
        return jwt.encode(payload, secret or self._SECRET, algorithm="HS256")

    def test_valid_token_returns_claims(self):
        from utils.auth_token import verify_jwt
        with patch("utils.auth_token.settings") as mock_settings:
            mock_settings.jwt_secret = self._SECRET
            claims = verify_jwt(self._token())
        assert claims["sub"] == "AB-12-CD"
        assert claims["role"] == "driver"

    def test_expired_token_raises_401(self):
        from fastapi import HTTPException
        from utils.auth_token import verify_jwt
        token = self._token({"exp": datetime.now(timezone.utc) - timedelta(seconds=1)})
        with patch("utils.auth_token.settings") as mock_settings:
            mock_settings.jwt_secret = self._SECRET
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises_401(self):
        from fastapi import HTTPException
        from utils.auth_token import verify_jwt
        token = self._token()
        tampered = token[:-4] + "XXXX"
        with patch("utils.auth_token.settings") as mock_settings:
            mock_settings.jwt_secret = self._SECRET
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(tampered)
        assert exc_info.value.status_code == 401

    def test_wrong_secret_raises_401(self):
        from fastapi import HTTPException
        from utils.auth_token import verify_jwt
        token = self._token(secret="alt-jwt-secret-for-unit-testing-only!")
        with patch("utils.auth_token.settings") as mock_settings:
            mock_settings.jwt_secret = self._SECRET
            with pytest.raises(HTTPException) as exc_info:
                verify_jwt(token)
        assert exc_info.value.status_code == 401


class TestRequireRole:
    def _claims(self, role: str) -> dict:
        return {"sub": "W001", "role": role}

    def test_matching_role_passes(self):
        from fastapi import HTTPException
        from utils.auth_token import require_role
        dep = require_role("operator", "manager")
        # Should not raise
        result = dep(self._claims("operator"))
        assert result["sub"] == "W001"

    def test_wrong_role_raises_403(self):
        from fastapi import HTTPException
        from utils.auth_token import require_role
        dep = require_role("manager")
        with pytest.raises(HTTPException) as exc_info:
            dep(self._claims("driver"))
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Redis session helpers
# ---------------------------------------------------------------------------

class TestRedisSessions:
    def test_set_get_delete_round_trip(self):
        import json
        from infrastructure.persistence import redis as rmod

        mock_redis = MagicMock()
        stored = {}

        def fake_setex(key, ttl, value):
            stored[key] = value

        mock_redis.setex.side_effect = fake_setex
        mock_redis.get.side_effect = lambda key: stored.get(key)
        mock_redis.delete.side_effect = lambda key: stored.pop(key, None)

        original = rmod.redis_client
        rmod.redis_client = mock_redis
        try:
            rmod.set_session("driver", "AB-12-CD", {"sub": "AB-12-CD", "role": "driver"})
            result = rmod.get_session("driver", "AB-12-CD")
            assert result == {"sub": "AB-12-CD", "role": "driver"}

            rmod.delete_session("driver", "AB-12-CD")
            assert rmod.get_session("driver", "AB-12-CD") is None
        finally:
            rmod.redis_client = original

    def test_get_returns_none_on_miss(self):
        from infrastructure.persistence import redis as rmod
        mock_redis = MagicMock()
        mock_redis.get.return_value = None
        original = rmod.redis_client
        rmod.redis_client = mock_redis
        try:
            assert rmod.get_session("driver", "MISSING") is None
        finally:
            rmod.redis_client = original



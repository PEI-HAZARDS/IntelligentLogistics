import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status  # type: ignore
from fastapi.responses import StreamingResponse  # type: ignore
from minio import Minio  # type: ignore
from minio.error import S3Error  # type: ignore

from auth.token_validator import oauth2_scheme, validate_ws_token

logger = logging.getLogger("APIGateway.media")

router = APIRouter(tags=["media"])

_ALLOWED_ROLES = {"operator", "manager"}

# Only buckets produced by the AI agents are reachable through this proxy.
_BUCKET_PATTERN = re.compile(r"^agent[a-c]-[A-Za-z0-9_-]+$")


def _require_media_role(
    request: Request,
    token: str | None = None,
    bearer: str | None = Depends(oauth2_scheme),
):
    """
    Resolve auth from either `?token=...` (so `<img>` tags work) or the
    standard `Authorization: Bearer` header. Enforces operator/manager role.
    """
    raw = token or bearer
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = validate_ws_token(request, raw)
    if not _ALLOWED_ROLES.intersection(payload.roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return payload


def get_minio_client(request: Request) -> Minio:
    """Lazily build (and cache) a Minio client on app.state."""
    state = request.app.state
    client = getattr(state, "minio_client", None)
    if client is not None:
        return client

    cfg = state.minio_config
    client = Minio(
        endpoint=cfg["endpoint"],
        access_key=cfg["access_key"],
        secret_key=cfg["secret_key"],
        secure=cfg.get("secure", False),
    )
    state.minio_client = client
    return client


@router.get("/media/{bucket}/{key:path}")
async def media_proxy(
    bucket: str,
    key: str,
    request: Request,
    _auth=Depends(_require_media_role),
):
    """Proxy crop/frame images from MinIO using signed S3 requests."""
    if not _BUCKET_PATTERN.match(bucket):
        raise HTTPException(status_code=404, detail="unknown bucket")

    client = get_minio_client(request)
    try:
        response = client.get_object(bucket, key)
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchBucket"):
            raise HTTPException(status_code=404, detail="not found") from exc
        logger.warning("MinIO S3Error bucket=%s key=%s code=%s", bucket, key, exc.code)
        raise HTTPException(status_code=502, detail="minio error") from exc
    except Exception as exc:
        logger.error("MinIO get_object failed bucket=%s key=%s: %s", bucket, key, exc)
        raise HTTPException(status_code=502, detail="minio unreachable") from exc

    content_type = response.headers.get("Content-Type", "application/octet-stream")
    response_headers: dict[str, str] = {}
    if response.headers.get("Content-Length"):
        response_headers["Content-Length"] = response.headers["Content-Length"]
    if response.headers.get("ETag"):
        response_headers["ETag"] = response.headers["ETag"]
    # Object keys embed truck_id + timestamp, so the content is effectively immutable.
    response_headers["Cache-Control"] = "private, max-age=86400, immutable"

    def iterator():
        try:
            for chunk in response.stream(amt=64 * 1024):
                yield chunk
        finally:
            response.close()
            response.release_conn()

    return StreamingResponse(
        iterator(),
        media_type=content_type,
        headers=response_headers,
    )

import logging
from typing import Annotated
from urllib.parse import urlparse

import httpx  # type: ignore
from fastapi import APIRouter, Depends, HTTPException, Request, Response  # type: ignore
from fastapi.responses import StreamingResponse  # type: ignore

from dependencies import (
    get_api_prefix,
    get_mediamtx_hls_internal_url,
    get_mediamtx_webrtc_internal_url,
)
from auth.token_validator import require_role

logger = logging.getLogger("APIGateway.stream")

router = APIRouter(tags=["stream"], dependencies=[Depends(require_role("operator", "manager"))])

# httpx default timeout — generous because MediaMTX needs to negotiate ICE.
_WHEP_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


def _build_hls_url(api_prefix: str, gate_id: str, quality: str) -> str:
    """Client-facing HLS playlist URL served by this gateway."""
    prefix = api_prefix.rstrip("/")
    return f"{prefix}/stream/{gate_id}/{quality}/hls/index.m3u8"


def _build_webrtc_url(api_prefix: str, gate_id: str, quality: str) -> str:
    """Client-facing WHEP endpoint served by this gateway (browser POSTs SDP here)."""
    prefix = api_prefix.rstrip("/")
    return f"{prefix}/stream/{gate_id}/{quality}/whep"


def _rewrite_session_location(
    location: str | None,
    gate_id: str,
    quality: str,
    api_prefix: str,
) -> str | None:
    """Rewrite a MediaMTX session Location header to a gateway-relative path."""
    if not location:
        return None
    parsed = urlparse(location)
    path = parsed.path or location
    session_id = path.rstrip("/").rsplit("/", 1)[-1]
    if not session_id:
        return None
    prefix = api_prefix.rstrip("/")
    return f"{prefix}/stream/{gate_id}/{quality}/whep/sessions/{session_id}"


@router.get("/stream/{gate_id}/low")
async def get_low_stream(
    gate_id: str,
    api_prefix: Annotated[str, Depends(get_api_prefix)],
):
    return {
        "gate_id": gate_id,
        "quality": "low",
        "hls_url": _build_hls_url(api_prefix, gate_id=gate_id, quality="low"),
        "webrtc_url": _build_webrtc_url(api_prefix, gate_id=gate_id, quality="low"),
    }


@router.get("/stream/{gate_id}/high")
async def get_high_stream(
    gate_id: str,
    api_prefix: Annotated[str, Depends(get_api_prefix)],
):
    return {
        "gate_id": gate_id,
        "quality": "high",
        "hls_url": _build_hls_url(api_prefix, gate_id=gate_id, quality="high"),
        "webrtc_url": _build_webrtc_url(api_prefix, gate_id=gate_id, quality="high"),
    }


@router.get("/stream/{gate_id}/{quality}/hls/{path:path}")
async def hls_proxy(
    gate_id: str,
    quality: str,
    path: str,
    request: Request,
    hls_url: Annotated[str, Depends(get_mediamtx_hls_internal_url)],
):
    """Proxy HLS playlists and segments from MediaMTX. Auth enforced by router-level role check."""
    if quality not in ("low", "high"):
        raise HTTPException(status_code=404, detail="unknown quality")

    target = f"{hls_url.rstrip('/')}/streams_{quality}/{gate_id}/{path}"
    # Preserve query string — LL-HLS variants and partial segments carry session ids
    # plus _HLS_msn / _HLS_part flags that MediaMTX needs to honor.
    if request.url.query:
        target = f"{target}?{request.url.query}"
    upstream_headers: dict[str, str] = {}
    range_hdr = request.headers.get("range")
    if range_hdr:
        upstream_headers["Range"] = range_hdr

    # MediaMTX low-latency HLS redirects index.m3u8 internally to the variant playlist.
    # follow_redirects=True so we deliver the final body to the client transparently.
    client = httpx.AsyncClient(timeout=_WHEP_TIMEOUT, follow_redirects=True)
    try:
        req = client.build_request("GET", target, headers=upstream_headers)
        upstream = await client.send(req, stream=True)
    except httpx.RequestError as exc:
        await client.aclose()
        logger.error("HLS upstream GET failed: %s", exc)
        raise HTTPException(status_code=502, detail="mediamtx unreachable") from exc

    if upstream.status_code >= 400:
        body = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        return Response(content=body, status_code=upstream.status_code)

    content_type = upstream.headers.get("content-type", "application/octet-stream")
    response_headers: dict[str, str] = {}
    if "content-length" in upstream.headers:
        response_headers["Content-Length"] = upstream.headers["content-length"]
    if "content-range" in upstream.headers:
        response_headers["Content-Range"] = upstream.headers["content-range"]
    response_headers["Cache-Control"] = "no-cache" if path.endswith(".m3u8") else "max-age=3"

    async def iterator():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        iterator(),
        status_code=upstream.status_code,
        media_type=content_type,
        headers=response_headers,
    )


@router.post("/stream/{gate_id}/{quality}/whep")
async def whep_create(
    gate_id: str,
    quality: str,
    request: Request,
    mediamtx_url: Annotated[str, Depends(get_mediamtx_webrtc_internal_url)],
    api_prefix: Annotated[str, Depends(get_api_prefix)],
):
    """Create a WHEP session — proxies the SDP offer to MediaMTX and rewrites Location."""
    if quality not in ("low", "high"):
        raise HTTPException(status_code=404, detail="unknown quality")

    body = await request.body()
    content_type = request.headers.get("content-type", "application/sdp")
    target = f"{mediamtx_url.rstrip('/')}/streams_{quality}/{gate_id}/whep"

    try:
        async with httpx.AsyncClient(timeout=_WHEP_TIMEOUT, follow_redirects=False) as client:
            upstream = await client.post(target, content=body, headers={"Content-Type": content_type})
    except httpx.RequestError as exc:
        logger.error("WHEP upstream POST failed: %s", exc)
        raise HTTPException(status_code=502, detail="mediamtx unreachable") from exc

    rewritten_location = _rewrite_session_location(
        upstream.headers.get("location"), gate_id, quality, api_prefix
    )

    response_headers: dict[str, str] = {}
    if rewritten_location:
        response_headers["Location"] = rewritten_location
    upstream_ct = upstream.headers.get("content-type")
    if upstream_ct:
        response_headers["Content-Type"] = upstream_ct
    upstream_etag = upstream.headers.get("etag")
    if upstream_etag:
        response_headers["ETag"] = upstream_etag

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@router.patch("/stream/{gate_id}/{quality}/whep/sessions/{session_id}")
async def whep_patch(
    gate_id: str,
    quality: str,
    session_id: str,
    request: Request,
    mediamtx_url: Annotated[str, Depends(get_mediamtx_webrtc_internal_url)],
):
    """Trickle ICE — proxy PATCH to MediaMTX session."""
    if quality not in ("low", "high"):
        raise HTTPException(status_code=404, detail="unknown quality")

    body = await request.body()
    content_type = request.headers.get("content-type", "application/trickle-ice-sdpfrag")
    if_match = request.headers.get("if-match")
    target = f"{mediamtx_url.rstrip('/')}/streams_{quality}/{gate_id}/whep/{session_id}"

    headers = {"Content-Type": content_type}
    if if_match:
        headers["If-Match"] = if_match

    try:
        async with httpx.AsyncClient(timeout=_WHEP_TIMEOUT, follow_redirects=False) as client:
            upstream = await client.patch(target, content=body, headers=headers)
    except httpx.RequestError as exc:
        logger.error("WHEP PATCH upstream failed: %s", exc)
        raise HTTPException(status_code=502, detail="mediamtx unreachable") from exc

    return Response(content=upstream.content, status_code=upstream.status_code)


@router.delete("/stream/{gate_id}/{quality}/whep/sessions/{session_id}")
async def whep_delete(
    gate_id: str,
    quality: str,
    session_id: str,
    mediamtx_url: Annotated[str, Depends(get_mediamtx_webrtc_internal_url)],
):
    """Terminate a WHEP session."""
    if quality not in ("low", "high"):
        raise HTTPException(status_code=404, detail="unknown quality")

    target = f"{mediamtx_url.rstrip('/')}/streams_{quality}/{gate_id}/whep/{session_id}"
    try:
        async with httpx.AsyncClient(timeout=_WHEP_TIMEOUT, follow_redirects=False) as client:
            upstream = await client.delete(target)
    except httpx.RequestError as exc:
        logger.error("WHEP DELETE upstream failed: %s", exc)
        raise HTTPException(status_code=502, detail="mediamtx unreachable") from exc

    return Response(status_code=upstream.status_code)

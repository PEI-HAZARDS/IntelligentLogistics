from fastapi import APIRouter, Depends, Request  # type: ignore

from dependencies import get_stream_base_url, get_stream_webrtc_base_url
from auth.token_validator import require_role, TokenPayload

router = APIRouter(tags=["stream"], dependencies=[Depends(require_role("operator", "manager"))])


def _build_hls_url(stream_base_url: str, gate_id: str, quality: str) -> str:
    """
    Build the HLS URL for MediaMTX.

    Example:
      stream_base_url = http://mediamtx:8888
      quality = "low"
      gate_id = "gate1"

      -> http://mediamtx:8888/streams_low/gate1/index.m3u8
    """
    base = stream_base_url.rstrip("/")
    return f"{base}/streams_{quality}/{gate_id}/index.m3u8"


def _build_webrtc_url(webrtc_base_url: str, gate_id: str, quality: str) -> str:
    """
    Build the WebRTC iframe URL for MediaMTX.

    Example:
      webrtc_base_url = http://mediamtx:8889
      quality = "low"
      gate_id = "gate1"

      -> http://mediamtx:8889/streams_low/gate1/
    """
    base = webrtc_base_url.rstrip("/")
    return f"{base}/streams_{quality}/{gate_id}/"


@router.get("/stream/{gate_id}/low")
async def get_low_stream(
    gate_id: str,
    stream_base_url: str = Depends(get_stream_base_url),
    webrtc_base_url: str = Depends(get_stream_webrtc_base_url),
):
    """
    Returns the HLS and WebRTC URLs for the LOW quality stream of a gate.

    Response example:
    {
      "gate_id": "gate1",
      "quality": "low",
      "hls_url": "http://mediamtx:8888/streams_low/gate1/index.m3u8",
      "webrtc_url": "http://mediamtx:8889/streams_low/gate1/"
    }
    """
    return {
        "gate_id": gate_id,
        "quality": "low",
        "hls_url": _build_hls_url(stream_base_url, gate_id=gate_id, quality="low"),
        "webrtc_url": _build_webrtc_url(webrtc_base_url, gate_id=gate_id, quality="low"),
    }


@router.get("/stream/{gate_id}/high")
async def get_high_stream(
    gate_id: str,
    stream_base_url: str = Depends(get_stream_base_url),
    webrtc_base_url: str = Depends(get_stream_webrtc_base_url),
):
    """
    Returns the HLS and WebRTC URLs for the HIGH quality stream of a gate.

    Response example:
    {
      "gate_id": "gate1",
      "quality": "high",
      "hls_url": "http://mediamtx:8888/streams_high/gate1/index.m3u8",
      "webrtc_url": "http://mediamtx:8889/streams_high/gate1/"
    }
    """
    return {
        "gate_id": gate_id,
        "quality": "high",
        "hls_url": _build_hls_url(stream_base_url, gate_id=gate_id, quality="high"),
        "webrtc_url": _build_webrtc_url(webrtc_base_url, gate_id=gate_id, quality="high"),
    }

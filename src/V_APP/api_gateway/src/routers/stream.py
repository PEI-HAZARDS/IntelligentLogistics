from fastapi import APIRouter, Depends, Request # type: ignore

from dependencies import get_stream_base_url

router = APIRouter(tags=["stream"])


def _build_hls_url(stream_base_url: str, gate_id: str, quality: str) -> str:
    """
    Constrói a URL HLS com base na configuração e no gate_id.

    Exemplo:
      stream_base_url = http://nginx-rtmp:8080
      quality = "low"
      gate_id = "gate01"

      -> http://nginx-rtmp:8080/hls/low/gate01/index.m3u8
    """
    base = stream_base_url.rstrip("/")
    return f"{base}/hls/{quality}/{gate_id}/index.m3u8"


@router.get("/stream/{gate_id}/low")
async def get_low_stream(gate_id: str, stream_base_url: str = Depends(get_stream_base_url)):
    """
    Devolve a URL HLS para a stream LOW de um gate.

    Response exemplo:
    {
      "gate_id": "gate01",
      "quality": "low",
      "hls_url": "http://nginx-rtmp:8080/hls/low/gate01/index.m3u8"
    }
    """
    hls_url = _build_hls_url(stream_base_url, gate_id=gate_id, quality="low")
    return {
        "gate_id": gate_id,
        "quality": "low",
        "hls_url": hls_url,
    }


@router.get("/stream/{gate_id}/high")
async def get_high_stream(gate_id: str, stream_base_url: str = Depends(get_stream_base_url)):
    """
    Devolve a URL HLS para a stream HIGH de um gate.

    Response exemplo:
    {
      "gate_id": "gate01",
      "quality": "high",
      "hls_url": "http://nginx-rtmp:8080/hls/high/gate01/index.m3u8"
    }
    """
    hls_url = _build_hls_url(stream_base_url, gate_id=gate_id, quality="high")
    return {
        "gate_id": gate_id,
        "quality": "high",
        "hls_url": hls_url,
    }

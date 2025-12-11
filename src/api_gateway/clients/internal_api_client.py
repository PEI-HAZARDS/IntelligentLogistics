import httpx
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from ..config import settings

API_V1_PREFIX = "/api/v1"


def _build_url(path: str) -> str:
    """
    Constrói a URL final para chamar o Data Module.

    - Garante que o path começa por "/"
    - Preenche o prefixo "/api/v1"
    - Junta com o BASE_URL vindo das settings
    """
    if not path.startswith("/"):
        path = "/" + path
    # path aqui é algo tipo "/arrivals/1/pending"
    return f"{settings.DATA_MODULE_URL.rstrip('/')}{API_V1_PREFIX}{path}"


async def _request(
    method: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Any] = None,
    timeout: float = 10.0,
) -> Any:
    """
    Helper interno para fazer requests HTTP ao Data Module.

    - method: "GET", "POST", "PUT", etc.
    - path: caminho relativo no Data Module (ex: "/arrivals/1/pending")
    - params: query string (opcional)
    - json: body em JSON (opcional)
    """
    url = _build_url(path)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method=method, url=url, params=params, json=json)
    except httpx.RequestError as exc:
        # erro de rede / timeout / DNS
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Erro ao comunicar com o Data Module: {exc}",
        )

    # Converter erros HTTP do Data Module em HTTPException
    if response.status_code >= 400:
        # tenta obter mensagem mais legível
        try:
            payload = response.json()
        except Exception:
            payload = {"detail": response.text}

        raise HTTPException(
            status_code=response.status_code,
            detail=payload.get("detail", payload),
        )

    # Se tudo OK, devolve o JSON (ou texto, se não tiver JSON)
    try:
        return response.json()
    except ValueError:
        return response.text


async def get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> Any:
    """
    Faz um GET ao Data Module.

    Exemplo de uso num router:
        data = await internal_client.get(f"/arrivals/{gate_id}/pending", params={"page": 1, "limit": 20})
    """
    return await _request("GET", path, params=params, timeout=timeout)


async def post(
    path: str,
    json: Optional[Any] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> Any:
    """
    Faz um POST ao Data Module.
    """
    return await _request("POST", path, params=params, json=json, timeout=timeout)


async def put(
    path: str,
    json: Optional[Any] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = 10.0,
) -> Any:
    """
    Faz um PUT ao Data Module.
    """
    return await _request("PUT", path, params=params, json=json, timeout=timeout)

from typing import Optional

from fastapi import APIRouter, Query

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["arrivals"])


# -------------------------------
# GET: /api/arrivals
# -------------------------------
@router.get("/arrivals")
async def list_all_arrivals(
    matricula: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals no Data Module.
    Lista todas as chegadas, opcionalmente filtradas por matrícula.
    """
    params = {
        "page": page,
        "limit": limit,
    }
    if matricula:
        params["matricula"] = matricula

    return await internal_client.get("/arrivals", params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}
# -------------------------------
@router.get("/arrivals/{gate_id}")
async def list_arrivals_by_gate(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id} no Data Module.
    Lista chegadas filtradas por gate.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}")
async def list_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift} no Data Module.
    Lista chegadas por gate e turno.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/{shift}"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/total
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/total")
async def count_arrivals_by_gate_shift(
    gate_id: int,
    shift: int,
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/total no Data Module.
    Retorna o total de chegadas para um gate e turno.
    """
    path = f"/arrivals/{gate_id}/{shift}/total"
    return await internal_client.get(path)


# -------------------------------
# GET: /api/arrivals/{gate_id}/pending
# -------------------------------
@router.get("/arrivals/{gate_id}/pending")
async def list_arrivals_pending(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/pending no Data Module.
    Lista chegadas pendentes (em_transito) por gate.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/pending"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/pending
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/pending")
async def list_arrivals_pending_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/pending no Data Module.
    Lista chegadas pendentes por gate e turno.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/{shift}/pending"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/pending/total
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/pending/total")
async def count_arrivals_pending(
    gate_id: int,
    shift: int,
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/pending/total no Data Module.
    Retorna o total de chegadas pendentes para um gate e turno.
    """
    path = f"/arrivals/{gate_id}/{shift}/pending/total"
    return await internal_client.get(path)


# -------------------------------
# GET: /api/arrivals/{gate_id}/in_progress
# -------------------------------
@router.get("/arrivals/{gate_id}/in_progress")
async def list_arrivals_in_progress(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/in_progress no Data Module.
    Lista chegadas em progresso (em_descarga) por gate.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/in_progress"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/in_progress
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/in_progress")
async def list_arrivals_in_progress_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/in_progress no Data Module.
    Lista chegadas em progresso por gate e turno.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/{shift}/in_progress"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/in_progress/total
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/in_progress/total")
async def count_arrivals_in_progress(
    gate_id: int,
    shift: int,
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/in_progress/total no Data Module.
    Retorna o total de chegadas em progresso para um gate e turno.
    """
    path = f"/arrivals/{gate_id}/{shift}/in_progress/total"
    return await internal_client.get(path)


# -------------------------------
# GET: /api/arrivals/{gate_id}/finished
# -------------------------------
@router.get("/arrivals/{gate_id}/finished")
async def list_arrivals_finished(
    gate_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/finished no Data Module.
    Lista chegadas concluídas (concluida) por gate.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/finished"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/finished
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/finished")
async def list_arrivals_finished_shift(
    gate_id: int,
    shift: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/finished no Data Module.
    Lista chegadas concluídas por gate e turno.
    """
    params = {"page": page, "limit": limit}
    path = f"/arrivals/{gate_id}/{shift}/finished"
    return await internal_client.get(path, params=params)


# -------------------------------
# GET: /api/arrivals/{gate_id}/{shift}/finished/total
# -------------------------------
@router.get("/arrivals/{gate_id}/{shift}/finished/total")
async def count_arrivals_finished(
    gate_id: int,
    shift: int,
):
    """
    Proxy para GET /api/v1/arrivals/{gate_id}/{shift}/finished/total no Data Module.
    Retorna o total de chegadas concluídas para um gate e turno.
    """
    path = f"/arrivals/{gate_id}/{shift}/finished/total"
    return await internal_client.get(path)

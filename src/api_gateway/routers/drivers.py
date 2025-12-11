from fastapi import APIRouter, Query
from typing import Dict, Any

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["drivers"])


# ---------------------------------
# GET: /api/drivers
# ---------------------------------
@router.get("/drivers")
async def list_drivers(
    limit: int = Query(default=100, ge=1, le=500),
):
    """
    Proxy para GET /api/v1/drivers no Data Module.

    No Data Module:
      @router.get("/drivers", response_model=List[CondutorResponse])
      def list_drivers(db: Session = Depends(get_db))
    """
    # O Data Module atualmente não tem paginação neste endpoint, portanto
    # o parâmetro `limit` aqui é só para futura extensão, se decidirem adicionar.
    params: Dict[str, Any] = {}
    # Se quiserem suportar limit no futuro, podem adicionar ao Data Module e descomentar:
    # params["limit"] = limit

    return await internal_client.get("/drivers", params=params or None)


# ---------------------------------
# GET: /api/drivers/{id}/arrivals
# ---------------------------------
@router.get("/drivers/{driver_id}/arrivals")
async def get_arrivals_for_driver(
    driver_id: int,
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Proxy para GET /api/v1/drivers/{id}/arrivals no Data Module.

    No Data Module:
      @router.get("/drivers/{id}/arrivals", response_model=List[ChegadaResponse])
      def get_arrivals_for_driver(id: int, db: Session = Depends(get_db))
    """
    path = f"/drivers/{driver_id}/arrivals"
    # Tal como em list_drivers, o Data Module não usa `limit` ainda, mas já deixamos preparado.
    params: Dict[str, Any] = {}
    # params["limit"] = limit  # se decidirem adicionar no Data Module

    return await internal_client.get(path, params=params or None)

from fastapi import APIRouter, Query
from typing import Optional, Dict, Any

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["alerts"])


# ---------------------------------
# GET: /api/alerts
# ---------------------------------
@router.get("/alerts")
async def list_alerts(
    severidade: Optional[int] = Query(default=None, ge=1, le=5),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Proxy para GET /api/v1/alerts no Data Module.

    No Data Module:
      @router.get("/alerts", response_model=List[AlertaResponse])
      def list_alerts(severidade: Optional[int] = None, limit: int = 50)

    - severidade: filtra por severidade (ex: 1-5)
    - limit: nº máximo de alertas
    """
    params: Dict[str, Any] = {"limit": limit}
    if severidade is not None:
        params["severidade"] = severidade

    return await internal_client.get("/alerts", params=params)


# ---------------------------------
# GET: /api/alerts/{alert_id}
# ---------------------------------
@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: int):
    """
    Proxy para GET /api/v1/alerts/{alert_id} no Data Module.

    No Data Module:
      @router.get("/alerts/{alert_id}", response_model=AlertaResponse)
    """
    path = f"/alerts/{alert_id}"
    return await internal_client.get(path)

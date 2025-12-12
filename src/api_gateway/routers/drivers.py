from fastapi import APIRouter, Query, Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["drivers"])


# ---------------------------------
# GET: /api/drivers
# ---------------------------------
@router.get("/drivers")
async def list_drivers(
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    """
    Proxy to GET /api/v1/drivers in Data Module.
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    return await internal_client.get("/drivers", params=params)


# ---------------------------------
# GET: /api/drivers/{drivers_license}
# ---------------------------------
@router.get("/drivers/{drivers_license}")
async def get_driver(
    drivers_license: str = Path(..., description="Driver's License"),
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}
    """
    # URL encode if necessary, but requests handles it usually
    return await internal_client.get(f"/drivers/{drivers_license}")


# ---------------------------------
# GET: /api/drivers/{drivers_license}/arrivals
# ---------------------------------
@router.get("/drivers/{drivers_license}/arrivals")
async def get_arrivals_for_driver(
    drivers_license: str = Path(..., description="Driver's License"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Proxy to GET /api/v1/drivers/{drivers_license}/arrivals
    """
    path = f"/drivers/{drivers_license}/arrivals"
    params = {"limit": limit}
    return await internal_client.get(path, params=params)

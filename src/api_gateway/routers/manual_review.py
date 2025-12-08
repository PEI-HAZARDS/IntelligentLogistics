from typing import Dict, Any

from fastapi import APIRouter, Body

from ..clients import internal_api_client as internal_client

router = APIRouter(tags=["manual_review"])


# ---------------------------------
# PUT: /api/manual_review/{gate_id}/{truck_id}/{decision}
# ---------------------------------
@router.put("/manual_review/{gate_id}/{truck_id}/{decision}")
async def manual_review(
    gate_id: int,
    truck_id: str,
    decision: str,
    payload: Dict[str, Any] = Body(default={}),
):
    """
    Endpoint exposto ao frontend para revisão manual do operador.

    Este método faz proxy para o Data Module:
      PUT /api/v1/manual_review/{gate_id}/{truck_id}/{decision}

    O `payload` pode incluir:
      - user_id
      - observacoes
      - matched_chegada_id
      - reason
      - notify_channel
      - etc.
    """
    path = f"/manual_review/{gate_id}/{truck_id}/{decision}"

    # Garante que o truck_id também vai no payload,
    # tal como o Data Module espera.
    payload = payload or {}
    payload.setdefault("truck_id", truck_id)

    return await internal_client.put(path, json=payload)

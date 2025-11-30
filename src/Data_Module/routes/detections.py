from fastapi import APIRouter, HTTPException
from models.pydantic_models import DetectionCreate, DetectionResponse
from services.decision_service import process_detection

router = APIRouter()

@router.post("/detections", response_model=DetectionResponse)
def create_detection(detection: DetectionCreate):
    """
    Endpoint chamado pelos agentes ao detectar um camião/matrícula/placa de Segurança.
    O processamento é delegado ao decision_service.
    Retorna o documento final guardado, não o modelo recebido.
    """
    try:
        # Pydantic v2 → .model_dump()
        detection_data = detection.model_dump()

        # O service deve devolver o documento final (MongoDB ou pós-processamento)
        stored_doc = process_detection(detection_data)

        if stored_doc is None:
            raise ValueError("process_detection returned None")

        # Garantir que o retorno é compatível com DetectionResponse
        return DetectionResponse.model_validate(stored_doc)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

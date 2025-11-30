from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from typing import Optional

app = FastAPI()

class Detection(BaseModel):
    timestamp: Optional[str]
    gate_id: Optional[int]
    matricula_detectada: Optional[str]
    confidence: Optional[float]
    metadata: Optional[dict]

@app.post("/process-detection")
async def process_detection(d: Detection):
    # Lógica simple: se matricula == "AA-00-11" -> match a chegada id 1
    matricula = d.matricula_detectada
    if matricula == "AA-00-11":
        return {
            "decision": "granted",
            "matched_chegada_id": 1,
            "estado_entrega": "em_descarga",
            "notify_channel": "notifications:driver:driver-123"
        }
    # se confidence baixa -> pending
    if d.confidence and d.confidence < 0.5:
        return {"decision": "pending", "reason": "low_confidence"}
    # default deny
    return {"decision": "denied", "matched_chegada_id": None, "notify_channel": "notifications:gate:1"}

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)



* pipeline completo (sequência numerada),
* formatos de mensagem (MQTT / REST / gRPC / S3),
* decisões de engenharia (quando enviar a box vs pedir 4K),
* transformações de coordenadas entre streams,
* mecanismos de tracking/confirm/anti-flapping,
* timeout, retry e políticas de fallback,
* segurança e eficiência energética,
* exemplos práticos (tópicos, payloads JSON, pseudocódigo de Agent-A e Agent-B),
* checklist mínimo para implementar o PoC.

Assumindo resoluções típicas: 720p = **1280×720**; 4K = **3840×2160** (factor de escala = 3x em X e Y). 

---

# 1) Pipeline end-to-end (sequência numerada)

1. **Ingest vídeo (dual-stream)**
   A câmara fornece 2 streams simultâneos ou um 4K com downscale local: 720p (sempre-on, consumos baixos) + 4K (on-demand). Agent-A consome o 720p sempre; Agent-B processa 4K quando acordado.

2. **Agent-A — deteção leve (YOLO tiny / TinyML)**

   * Faz inferência a cada frame (ex.: 5–10 fps) e produz bbox(es) para “truck”.
   * Aplica *debounce / temporal confirmation*: só considera deteção válida se a mesma bbox (ou track) é vista por **N** frames consecutivos (ex.: N=3) ou mantém um tracker (SORT/DeepSORT).
   * Quando confirmado, publica evento de deteção mínimo no **Broker (MQTT)**: `gate/{id}/detection` com metadados (timestamp, bbox em coordenadas do 720p, confidence, event_id).

3. **Broker / Orchestrator**

   * Repassa o evento ao Orchestrator e a subscritores (Agent-B). Orchestrator aplica regras (throttling, denylist, cache). Se Orchestrator decide activar Agent-B, publica `gate/{id}/wake` ou envia um RPC para Agent-B.

4. **Agent-B wake & stream**

   * Agent-B acorda (se estava hibernado). Solicita o stream 4K da câmara (via RTSP/ONVIF/GStreamer). Orchestrator pode comandar a câmara para aumentar bitrate ou ligar IR lights.
   * Agent-B escala a bbox do 720p → 4K (ver secção 3) e extrai crop(s) com margem (pad) para procurar *placa* e *placard laranja*. Também pode extrair multi-crops (frente, lateral, traseira) ou usar sliding windows dentro da box se truck grande.

5. **Detecção plate + placard no crop**

   * Primeiro: detector de placa (pequeno modelo YOLO) sobre crops; se encontrar bbox de placa, faz OCR (CRNN / PaddleOCR / transformer OCR).
   * Paralelamente: detector de placard laranja (hazmat panel) no mesmo crop/patchs; se detectado, recorta e aplica OCR de números (UN/HIN) — normalmente 3–4 dígitos.
   * Faz *multi-frame fusion*: junta resultados de várias frames (voting) para aumentar robustez.

6. **Decisão / lookup**

   * Agent-B chama a API do datacenter (`POST /api/authorize` ou gRPC `AuthorizePlate`) com `plate`, `UN_number`, imagens (ou S3 URLs) e metadata.
   * Backend verifica manifestos, permissões e devolve decisão (`allow/deny/hold` + `destination` + `reason`). Orchestrator aplica políticas locais e publica `gate/{id}/decision`.

7. **Actuação e UI**

   * Orchestrator envia comando ao actuator (PLC/GPIO) para abrir cancela e envia dados para UI local (painel) com destino e instruções.
   * Logs, thumbnails, crops e metadados vão para S3/MinIO e Postgres; métricas para Prometheus.

8. **Finalização**

   * Agent-B pára o stream 4K após timeout de inatividade (ex.: 5–10 s). Agent-B volta a hibernar. Agent-A continua.

---

# 2) Coordenadas e escala entre 720p e 4K

Se Agent-A detecta bbox em 720p e Agent-B processa 4K, deves transformar bbox:

* Notação: bbox720 = (x, y, w, h) relativamente a 1280×720.
* fator_x = width4K / width720 = 3840 / 1280 = **3**
* fator_y = height4K / height720 = 2160 / 720 = **3**

Portanto:

```
x4k = x720 * fator_x
y4k = y720 * fator_y
w4k = w720 * fator_x
h4k = h720 * fator_y
```

**Importante:** acrescenta margem/padding ao bbox4k (ex.: +20–50%) porque bbox apenas do YOLO tiny pode cortar a placa. Ex.: pad=0.3 ⇒ expandir area para +30%.

Se as resoluções não são exactamente essas calcula os factors reais.

---

# 3) O que enviar no evento inicial (Agent-A → Broker)

Envio mínimo (pequeno) para não saturar broker:

**Tópico:** `gate/{gate_id}/detection`

**Payload JSON:**

```json
{
  "event_id":"uuid-1234",
  "timestamp":"2025-10-04T09:12:34Z",
  "gate_id":"gate-01",
  "device_id":"agentA-01",
  "class":"truck",
  "confidence":0.95,
  "bbox": [x, y, w, h],          // x,y,w,h em pixels relativos à resolução do stream 720p
  "frame_id": 45223,
  "suggest":"request_4k",
  "thumbnail": "base64_if_small_or_s3_url"  // optional, small JPEG base64 if < 64KB
}
```

Regras:

* **Não** enviar crop 4K via MQTT (é pesado) — enviar só pequena thumbnail (opcional) ou instrução para upload via presigned URL.

---

# 4) Como transferir crops/imagens para OCR de forma eficiente

Opções (ordenadas por recomendação):

**A — Presigned S3 upload (recomendado)**

1. Agent-B aciona Orchestrator/Storage service (`POST /api/presign`) pedindo URL para upload.
2. Orchestrator responde com presigned PUT URL.
3. Agent-B grava crop JPEG e faz PUT → S3/MinIO.
4. Agent-B envia ao broker/Orchestrator o S3 URL no `decision` payload.

Vantagens: evita enviar imagens pesadas pelo MQTT, armazenamento já organizado, acessível por backend.

**B — Direct upload to storage (edge MinIO)**

* Agent-B grava localmente em MinIO que replica para datacenter. Recomendado se tens MinIO no edge.

**C — MQTT base64 (apenas para thumbnails pequenos)**

* Só para imagens < 64KB e apenas thumbnails. Não usar para crops 4K.

---

# 5) Tracking e confirmação (evitar falsas triggers)

* Use tracker (SORT/DeepSORT) no Agent-A para gerar `track_id`. Só quando `track.frames_seen >= N` e `avg_confidence >= threshold` entao publicar detection.
* Se houver várias boxes (multi-truck), Agent-A publica uma detecção por track_id. Agent-B processa uma por vez ou em paralelo respeitando recursos.

---

# 6) Mensagens / tópicos MQTT sugeridos

* `gate/{id}/status` — retained: device status/heartbeat.
* `gate/{id}/detection` — Agent-A → event descrito acima.
* `gate/{id}/wake` — Orchestrator → Agent-B (optional)
* `gate/{id}/request_upload` — Orchestrator → Agent-B (presign info)
* `gate/{id}/decision` — Agent-B → Orchestrator / UI → final decision.
* `gate/{id}/actuator` — Orchestrator → PLC/GPIO (open/close).
* `audit/{id}/events` — long-term log stream (retained centrally).

---

# 7) Exemplo de payload `decision` (Agent-B → Orchestrator)

```json
{
  "event_id": "uuid-1234",
  "timestamp": "2025-10-04T09:12:45Z",
  "gate_id": "gate-01",
  "agent_b_id": "agentB-01",
  "plate": "AA-12-BB",
  "plate_confidence": 0.93,
  "placard_detected": true,
  "UN_number": "1203",           // opcional
  "UN_confidence": 0.88,
  "hazards": ["flammable"],
  "image_url": "s3://minio/gate-01/uuid-1234/crop_plate.jpg",
  "decision": "allow",
  "destination": "wharf-7",
  "open_gate": true,
  "notes": "matched manifest id 6789"
}
```

---

# 8) API / endpoints (orchestrator ↔ datacenter) — contrato REST / gRPC

**REST examples**

* `POST /api/authorize`
  Body:

  ```json
  {
    "plate": "AA-12-BB",
    "UN": "1203",
    "gate_id":"gate-01",
    "images": ["s3://.../crop_plate.jpg"]
  }
  ```

  Response:

  ```json
  {
    "decision":"allow",
    "destination":"wharf-7",
    "reason":"manifest OK",
    "valid_until":"2025-10-04T15:00:00Z"
  }
  ```

* `POST /api/presign`
  Body: `{ "path": "gate-01/uuid-1234/crop_plate.jpg", "ttl_sec": 300 }`
  Response: `{ "put_url":"https://...","get_url":"s3://..." }`

**gRPC / Protobuf** (compacto, para latência)

* Define `AuthorizePlate(PlateRequest) returns (AuthDecision)` com campos plate, UN, image_url etc. gRPC é recomendado entre Orchestrator e backend para baixa latência e compactação.

---

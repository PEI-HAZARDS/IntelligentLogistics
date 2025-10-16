# Componentes e tecnologias recomendadas 

1. **Stream Manager / RTSP Proxy** (Desnecessário)

   * Tech: `rtsp-simple-server` ou GStreamer (com NVDEC se tiveres GPU).
   * Porquê: mantém sessões abertas (reduz handshake latency) e faz multiplexing/transcode on-demand.

2. **Broker / Middleware**

   * Tech: Mosquitto (simples) ou EMQX (se preveres mais dispositivos).
   * Porquê: MQTT é leve, tópico-based e ideal para wake/decision flows.

3. **Agent-A (720p detector)**

   * Tech: Docker Container Python + ONNXRuntime/TFLite (modelo quantizado YOLO-nano / MobileNet-SSD).
   * Porquê: modelo leve, rápido e pouco consumo de CPU para deteção contínua.

4. **Orchestrator** (Desnecessário)

   * Tech: FastAPI/Go microservice, Redis (cache TTL), regras configuráveis.
   * Porquê: centraliza política (wake, timeouts, fallback) e coordena actuadores/UI.

5. **Agent-B (4K worker)**

   * Tech: Worker(s) containerizados usando TensorRT/Triton + PaddleOCR/CRNN.
   * Porquê: GPUs no DC permitem OCR e detecção de símbolos em alta resolução com throughput decente.

6. **Storage & Upload**

   * Tech: MinIO (S3 compatível) + presigned URLs para upload de crops.
   * Porquê: evita envio large payloads pelo broker; acessível para backend e auditoria.

7. **DB & Policy**

   * Tech: Postgres (manifests), Redis cache (decisões recentes).
   * Porquê: ACID e cache para offline decisions.

8. **Monitoring & MLOps**

   * Tech: Prometheus + Grafana, MLflow / Triton model registry.
   * Porquê: métricas e controlo de modelos no DC.

9. **UI / Actuator**

   * Tech: Web app (React) subscrito a MQTT ou Orchestrator; Actuator Gateway (MQTT/HTTP → PLC).
   * Porquê: interface para operador + comando seguro para cancela.

---

# Fluxo detalhado (passos de runtime)

1. **Agent-A** consome 720p, faz inferência a 5–10 fps, tracking (SORT), confirma detections (N frames) e publica:

   * Tópico: `gate/01/detection` (payload com `event_id`, `track_id`, `bbox720`, `timestamp`, `conf`, `res=[w,h]`).
<!-- 3. **Orchestrator** subscreve detections; aplica rules (debounce, rate limit) e publica `wake` se necessário: `gate/01/wake`. -->
4. **Agent-B** (worker) recebe wake, pede ao Stream Manager o 4K feed; transforma bbox720 → bbox4K (scale + padding), extrai crop(s) e executa:

   * placa detection → OCR (CRNN / PaddleOCR)
   * placard/hazard detection → OCR do número UN
   * multi-frame fusion (voting) para robustez
5. **Agent-B** sobe crop para MinIO via presigned PUT e chama `POST /api/authorize` com `plate`, `UN`, `image_url`.
6. **Policy API** retorna `allow/deny/destination` → Orchestrator publica `gate/01/decision` e aciona UI/Actuator.
7. **Agent-B** fecha 4K stream após idle timeout (p.ex. 5–10 s); volta a hibernar.


# System Responsibilities and Message Flow

## 2. Responsibilities 

### Agent-B (Crop Producer)
- Reads 4K video stream, selecting the best frame nearest to the detection timestamp.
- Generates N crops per frame:
  - Main crop: Scaled and padded bounding box (bbox).
  - Optional: Sliding crops (left/right).
- Preprocesses crops (deskews if 4 points are available).
- Saves crops locally and/or uploads via presigned URL to MinIO.
- Publishes metadata job to a queue, indicating crop location and type (e.g., `plate`, `placard`).
- Registers: `event_id`, `track_id`, `frame_id`, `crop_path`, `crop_type`, `crop_ts`.

### Agent-C (LPR Workers)
- Subscribes to topic/queue for crops with `crop_type == plate` (or executes plate detection followed by OCR).
- Performs plate OCR using CRNN/PaddleOCR.
- Produces candidate with: `plate_text`, `conf`, `crop_ref`, `frame_ts`.
- Sends candidate to a results channel (Redis list or DB table) associated with `event_id`/`track_id`.

### Agent-D (Placard Workers)
- Subscribes to crops with `crop_type == placard`.
- Detects placard/pictograms and performs OCR for UN number (3-4 digits).
- Produces candidate with: `UN_number`, `conf`, `crop_ref`, `frame_ts`.
- Saves candidate to the same aggregator as Agent-C.

<!-- 
### Orchestrator / Consensus Service
- Receives candidates in streaming and accumulates by `event_id`/`track_id`.
- Applies voting/fusion rules (see Section 5).
- Upon consensus (or timeout), emits `truck_identified` with:
  - Plate, UN number, confidences, and image URLs.
- Calls Policy API for authorization and triggers UI/actuator. -->

## 3. Message Flow and Temporal Details

1. **Agent-A** detects a truck and publishes to `gate/01/detection`:
   - Payload: `{event_id, track_id, bbox720, ts, res}`.
2. **Orchestrator** sends `gate/01/wake` to activate **Agent-B**.
3. **Agent-B** pulls 4K frames and generates crops for frames `F0`, `F1`, `F2`, etc. (e.g., 1 main crop per frame, up to 5 frames). For each crop:
   - Saves locally: `/tmp/gate01/evt-123/t-7_f045_plate.jpg`.
   - Optional: Requests presigned PUT, uploads to MinIO, obtains `s3://.../plate.jpg`.
   - Publishes job to queue:
     - Topic: `crops.plate`
     - Payload: `{event_id, track_id, crop_id, crop_url, frame_ts, crop_meta}`
4. **Agent-C** consumes jobs from `crops.plate`, runs OCR, and publishes candidate:
   - Topic: `candidates.plate`
   - Payload: `{event_id, track_id, crop_id, plate_text, plate_conf, frame_ts, crop_url}`
5. **Agent-D** processes `crops.placard` and publishes to `candidates.placard` with similar payload.
6. **Consensus Service (or Orchestrator)**:
   - Reads candidates in real-time and maintains a structure in memory/Redis.
   - When consensus rule is satisfied (e.g., same plate in ≥3 candidates or `avg_conf` ≥ threshold), publishes to `gate/01/truck_identified`:
     - Payload: Final `plate`, `UN`, confidences, and references to canonical crop images.
7. **Orchestrator** calls `POST /api/authorize` with `plate`, `UN`, and image URLs for final decision.
8. Decision is published to `gate/01/decision` topic and sent to actuator/UI.

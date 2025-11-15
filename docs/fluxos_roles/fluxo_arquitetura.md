# Fluxo Completo do Sistema Intelligent Logistics

Baseado na arquitetura da imagem e no código fornecido, aqui está o fluxo detalhado:

---

## 1. Pipeline End-to-End (Sequência Numerada)

### **1.1 Ingest de Vídeo (Dual-Stream) via Nginx RTMP**

**Arquitetura de Streaming:**

- **Câmara IP** fornece 2 streams RTSP simultâneos:
  - **720p** (low-res): Always-on, baixo consumo de recursos (~2-5 Mbps)
  - **4K** (high-res): On-demand, ativado quando necessário (~15-25 Mbps)

**Servidor Nginx RTMP (Middleware de Streaming):**

- Recebe streams RTSP da câmara via `rtsp://camera-ip:554/stream_720p` e `stream_4k`
- Re-transmite via RTMP para múltiplos consumidores:
  - **Agentes (A, B, C)**: Consomem via RTSP/RTMP para processamento
  - **Interface Web**: HLS/DASH para visualização em tempo real pelo porteiro
  - **Gravação**: DVR opcional para armazenamento histórico

**Configuração Nginx RTMP:**

```nginx
rtmp {
    server {
        listen 1935;

        application live {
            live on;

            # Stream 720p (always-on)
            exec ffmpeg -i rtsp://camera:554/stream_720p
                       -c:v copy -f flv rtmp://localhost/live/gate01_720p;

            # Stream 4K (on-demand)
            exec_pull ffmpeg -i rtsp://camera:554/stream_4k
                            -c:v copy -f flv rtmp://localhost/live/gate01_4k;

            # HLS para interface web
            hls on;
            hls_path /tmp/hls;
            hls_fragment 2s;
        }
    }
}
```

**Benefícios:**

- **Desacoplamento**: Câmara não precisa suportar múltiplas conexões diretas
- **Transcoding**: Conversão de formatos (RTSP → HLS/DASH) para web
- **Baixa Latência**: HLS com fragmentos de 2s (~4-6s latência total)
- **Escalabilidade**: Nginx distribui para N consumidores sem sobrecarregar câmara

---

### **1.2 Agent-A — Detecção de Caminhões (YOLO)**

**Responsabilidades:**

- Consome stream 720p via `rtmp://nginx:1935/live/gate01_720p`
- Processa em loop (~5-10 fps)
- Executa YOLO para detetar classe "truck"
- Implementa tracking (ex: DeepSORT/ByteTrack) para manter `track_id` consistente
- Aplica threshold de confiança (ex: `conf >= 0.75`)
- Aguarda confirmação temporal (ex: 3 frames consecutivos)

**Quando confirmado:**

```
Publica no Kafka:
├── Tópico: gate.{gate_id}.detection (truck-detected)
├── Payload:
│   ├── event_id: UUID único
│   ├── source: "agent-A-gate-01"
│   ├── timestamp: ISO 8601
│   ├── track_id: ID do tracking
│   ├── class: "truck"
│   ├── conf: 0.87
│   ├── bbox720: [x, y, w, h]
│   └── stream_url: "rtmp://nginx:1935/live/gate01_720p"
└── Key: track_id (para particionamento)
```

**Estado interno:**

- Mantém dicionário de `track_id` ativos
- Remove tracks obsoletos após N frames sem deteção
- Evita re-publicação de tracks já processados

---

### **1.3 Broker Kafka — Hub Central de Eventos**

**Configuração (docker-compose.yml):**

- KRaft mode (sem Zookeeper)
- 3 partições por tópico (paralelismo)
- Replication factor 1 (desenvolvimento)
- Advertised listeners: `10.255.32.64:9092`

**Tópicos criados no bootstrap:**

1. `gate.{gate_id}.detection` (truck-detected)
2. `candidates.{gate_id}.plate` (license-plate-detected)
3. `candidates.{gate_id}.placard` (hazard-plate-detected)
4. `gate.{gate_id}.decision` (access-decision)

**Subscribers ativos:**

- **Agent-B**: Consome `gate.{gate_id}.detection` (group: `agent-B-gate-01-group`)
- **Agent-C**: Consome `gate.{gate_id}.detection` (group: `agent-C-gate-01-group`)
- **Decision Engine**: Consome `candidates.{gate_id}.plate` + `candidates.{gate_id}.placard`

---

### **1.4 Agent-B — Detecção de Matrícula (YOLO + OCR)**

**Consumer Loop:**

```
while running:
    ├── Aguarda mensagem em gate.{gate_id}.detection
    ├── Recebe payload com event_id, track_id, bbox720
    └── Trigger: Callback _handle_truck_detection()
```

**Processamento (quando recebe truck-detected):**

1. **Ativação do Stream 4K:**

   - Inicia conexão com `rtmp://nginx:1935/live/gate01_4k` (se não estava ativo)
   - Mantém stream aberto por timeout (ex: 30s idle)
   - Nginx faz pull da câmara apenas quando há consumidores

2. **Transformação de Coordenadas:**

   - Converte `bbox720` [x, y, w, h] para coordenadas 4K
   - Aplica padding (+30%) para garantir captura completa

3. **Detecção de Placa (YOLO):**

   - Processa apenas ROI do frame 4K
   - YOLO especializado em placas portuguesas
   - Filtra por confiança (ex: `conf >= 0.70`)

4. **Crop e Armazenamento:**

   - Extrai crops das placas detetadas
   - **Guarda localmente** (temporário): `./crops/{event_id}_plate_{idx}.jpg`

5. **Upload para MinIO (Object Storage):**

   ```python
   # Upload para MinIO
   minio_client.put_object(
       bucket_name="license-plates",
       object_name=f"{gate_id}/{event_id}/{crop_id}.jpg",
       data=crop_file,
       content_type="image/jpeg"
   )

   # Gerar URL pública (presigned, válido por 24h)
   image_url = minio_client.presigned_get_object(
       bucket_name="license-plates",
       object_name=f"{gate_id}/{event_id}/{crop_id}.jpg",
       expires=timedelta(hours=24)
   )
   ```

6. **OCR (PaddleOCR):**

   - Executa OCR sobre cada crop
   - Valida formato português: `XX-XX-XX` ou `XX-XX-XXX`
   - Calcula confiança agregada

7. **Publicação no Kafka:**
   ```
   Publica no Kafka:
   ├── Tópico: candidates.{gate_id}.plate (license-plate-detected)
   ├── Payload:
   │   ├── event_id: (mesmo do truck original)
   │   ├── crop_id: "{event_id}_plate_0"
   │   ├── source: "agent-B-gate-01"
   │   ├── timestamp: ISO 8601
   │   ├── track_id: (link ao truck)
   │   ├── plate_text: "12-AB-34"
   │   ├── conf: 0.91
   │   ├── image_url: "https://minio:9000/license-plates/.../presigned-url"
   │   ├── minio_bucket: "license-plates"
   │   ├── minio_object_key: "gate-01/{event_id}/{crop_id}.jpg"
   │   └── gate_id: "gate-01"
   └── Key: event_id (agrupa por evento)
   ```

**Referência na Base de Dados:**

- A API consome esta mensagem Kafka e persiste no PostgreSQL:
  ```sql
  INSERT INTO license_plate_detections (
      event_id, crop_id, plate_text, confidence,
      minio_bucket, minio_object_key, image_url,
      detected_at, gate_id
  ) VALUES (...);
  ```

---

### **1.5 Agent-C — Detecção de Placas de Perigo (Paralelo ao B)**

**Comportamento similar ao Agent-B, mas:**

- Processa mesmo stream 4K via Nginx RTMP
- YOLO especializado em UN numbers (1203, 1428, etc.)
- OCR adaptado para dígitos grandes em losangos/quadrados

**Upload para MinIO:**

```python
# Bucket separado para placards
minio_client.put_object(
    bucket_name="hazard-placards",
    object_name=f"{gate_id}/{event_id}/{crop_id}.jpg",
    data=crop_file
)
```

**Payload publicado:**

```json
{
  "event_id": "...",
  "crop_id": "...",
  "placard_un": "1203",
  "conf": 0.85,
  "hazard_class": "3",
  "image_url": "https://minio:9000/hazard-placards/.../presigned-url",
  "minio_bucket": "hazard-placards",
  "minio_object_key": "gate-01/{event_id}/{crop_id}.jpg"
}
```

**Referência na Base de Dados:**

```sql
INSERT INTO placard_detections (
    event_id, crop_id, placard_un, hazard_class, confidence,
    minio_bucket, minio_object_key, image_url,
    detected_at, gate_id
) VALUES (...);
```

---

### **1.6 Decision Engine (Orchestrator) — Agregação e Decisão**

**Componentes:**

- **Kafka Consumer**: Consome `candidates.{gate_id}.plate` + `placard`
- **PostgreSQL Client**: Acesso READ-ONLY para validações
- **Kafka Producer**: Publica decisões em `gate.{gate_id}.decision`

**Conexão ao PostgreSQL:**

```python
# Configuração com pool de conexões (READ-ONLY)
DATABASE_URL = "postgresql://decision_user:readonly_pass@postgres:5432/logistics"
engine = create_engine(
    DATABASE_URL,
    pool_size=10,           # 10 conexões permanentes
    max_overflow=20,        # +20 sob demanda
    pool_pre_ping=True,     # Valida conexões antes de usar
    pool_recycle=3600       # Recicla conexões a cada 1h
)

# Permissões SQL (apenas leitura):
# GRANT SELECT ON vehicles, hazard_materials, access_rules TO decision_user;
# REVOKE INSERT, UPDATE, DELETE ON ALL TABLES FROM decision_user;
```

**Lógica de Agregação:**

1. **Aguarda inputs** de Agent-B e Agent-C (timeout 5s)
2. **Correlaciona** por `event_id`
3. **Consulta PostgreSQL** (queries em paralelo):

```python
async def validate_access(
    self,
    plate_text: str,
    un_number: str,
    gate_id: str
) -> dict:
    """Executa validações em paralelo"""

    # Query 1: Validar matrícula
    vehicle_query = text("""
        SELECT authorized, vehicle_type, company_id, expires_at
        FROM vehicles
        WHERE plate_number = :plate
          AND (expires_at IS NULL OR expires_at > NOW())
    """)

    # Query 2: Validar UN number
    hazard_query = text("""
        SELECT restricted, hazard_class, requires_permit
        FROM hazard_materials
        WHERE un_number = :un
    """)

    # Query 3: Regras temporais (horário de acesso)
    time_query = text("""
        SELECT allowed, reason
        FROM access_rules
        WHERE gate_id = :gate
          AND CURRENT_TIME BETWEEN start_time AND end_time
          AND (day_of_week IS NULL OR day_of_week = EXTRACT(DOW FROM NOW()))
    """)

    # Executar em paralelo (~8ms total)
    async with self.db.begin() as conn:
        vehicle_result, hazard_result, time_result = await asyncio.gather(
            conn.execute(vehicle_query, {"plate": plate_text}),
            conn.execute(hazard_query, {"un": un_number}),
            conn.execute(time_query, {"gate": gate_id})
        )

    vehicle = vehicle_result.fetchone()
    hazard = hazard_result.fetchone()
    time_rule = time_result.fetchone()

    return {
        "plate_authorized": vehicle and vehicle.authorized,
        "vehicle_expired": vehicle and vehicle.expires_at and vehicle.expires_at < datetime.now(),
        "un_restricted": hazard and hazard.restricted,
        "un_requires_permit": hazard and hazard.requires_permit,
        "time_allowed": time_rule and time_rule.allowed,
        "time_reason": time_rule.reason if time_rule else None
    }
```

4. **Aplica regras de negócio:**

```python
# DENY cases (prioridade alta)
if not validation["plate_authorized"]:
    decision = "DENY"
    reason = "unauthorized_plate"
elif validation["vehicle_expired"]:
    decision = "DENY"
    reason = "vehicle_authorization_expired"
elif validation["un_restricted"]:
    decision = "DENY"
    reason = "hazardous_material_restricted"
elif not validation["time_allowed"]:
    decision = "DENY"
    reason = f"time_restriction: {validation['time_reason']}"

# MANUAL_REVIEW cases
elif validation["un_requires_permit"]:
    decision = "MANUAL_REVIEW"
    reason = "hazmat_permit_verification_required"

# APPROVE (todas validações passaram)
else:
    decision = "APPROVE"
    reason = "all_checks_passed"
```

**Publicação da Decisão:**

```
Publica no Kafka:
├── Tópico: gate.{gate_id}.decision (access-decision)
├── Payload:
│   ├── event_id: "..."
│   ├── decision: "APPROVE" | "DENY" | "MANUAL_REVIEW"
│   ├── reason: "authorized_plate"
│   ├── timestamp: ISO 8601
│   ├── plate_text: "12-AB-34"
│   ├── plate_image_url: "https://minio:9000/..." (do Agent-B)
│   ├── placard_un: "1203"
│   ├── placard_image_url: "https://minio:9000/..." (do Agent-C)
│   ├── gate_id: "gate-01"
│   └── validation_details: {...} (para auditoria)
└── Key: gate_id
```

**Nota:** Decision Engine **NÃO persiste** no PostgreSQL. Apenas publica a decisão no Kafka. A persistência é responsabilidade da FastAPI (próxima seção).

---

### **1.7 FastAPI Backend — Persistência, API e WebSocket**

**Arquitetura:**

```
FastAPI Application
├── Kafka Consumer (background task)
│   ├── Consome: gate.{gate_id}.decision
│   ├── Persiste no PostgreSQL (INSERT)
│   └── Notifica WebSocket clients
│
├── REST Endpoints (READ)
│   ├── GET /api/v1/events/{event_id}
│   ├── GET /api/v1/decisions?gate_id=...&date=...
│   ├── GET /api/v1/plates/{plate_text}/history
│   └── POST /api/v1/manual-review/{event_id}
│
└── WebSocket Endpoint (notificações em tempo real)
    └── WS /ws/gate/{gate_id}
```

**Kafka Consumer (Background Task):**

```python
@app.on_event("startup")
async def start_kafka_consumer():
    """Inicia consumer de decisões do Decision Engine"""
    asyncio.create_task(consume_decisions())

async def consume_decisions():
    """Consome decisões e persiste no PostgreSQL"""
    broker = KafkaBroker(
        bootstrap_servers=settings.KAFKA_SERVERS,
        client_id="fastapi-consumer"
    )

    await broker.subscribe(
        topics=["gate.*.decision"],
        callback=persist_decision,
        group_id="fastapi-decisions-group"
    )

async def persist_decision(decision_data: dict):
    """Callback: persiste decisão e notifica clients"""
    async with AsyncSession(engine) as session:
        # 1. Criar registro de decisão
        decision = AccessDecision(
            event_id=decision_data["event_id"],
            gate_id=decision_data["gate_id"],
            decision=decision_data["decision"],
            reason=decision_data["reason"],
            plate_text=decision_data["plate_text"],
            placard_un=decision_data.get("placard_un"),
            plate_image_url=decision_data.get("plate_image_url"),
            placard_image_url=decision_data.get("placard_image_url"),
            decided_at=datetime.fromisoformat(decision_data["timestamp"].replace('Z', '+00:00'))
        )
        session.add(decision)

        # 2. Criar audit log
        audit = AuditLog(
            event_id=decision_data["event_id"],
            action="DECISION_MADE",
            actor="decision-engine",
            details=decision_data.get("validation_details", {}),
            timestamp=datetime.utcnow()
        )
        session.add(audit)

        await session.commit()

        # 3. Notificar WebSocket clients conectados a este gate
        gate_id = decision_data["gate_id"]
        for ws in active_connections.get(gate_id, []):
            await ws.send_json({
                "type": "decision",
                "data": decision_data
            })

        logger.info(f"Decisão persistida: {decision_data['event_id']} -> {decision_data['decision']}")
```

**Schema PostgreSQL:**

```sql
-- Tabela de decisões (escrita pela FastAPI)
CREATE TABLE access_decisions (
    id SERIAL PRIMARY KEY,
    event_id UUID UNIQUE NOT NULL,
    gate_id VARCHAR(50) NOT NULL,
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('APPROVE', 'DENY', 'MANUAL_REVIEW')),
    reason TEXT,
    plate_text VARCHAR(20),
    placard_un VARCHAR(10),
    plate_image_url TEXT,
    placard_image_url TEXT,
    decided_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_gate_date (gate_id, decided_at DESC),
    INDEX idx_event (event_id)
);

-- Tabela de auditoria
CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    event_id UUID NOT NULL,
    action VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    details JSONB,
    timestamp TIMESTAMP NOT NULL,
    INDEX idx_event (event_id),
    INDEX idx_timestamp (timestamp DESC)
);

-- Usuários PostgreSQL com permissões separadas
-- 1. Decision Engine (READ-ONLY nas tabelas de validação)
CREATE USER decision_user WITH PASSWORD 'decision_pass';
GRANT SELECT ON vehicles, hazard_materials, access_rules TO decision_user;

-- 2. FastAPI (READ-WRITE em access_decisions e audit_logs)
CREATE USER fastapi_user WITH PASSWORD 'fastapi_pass';
GRANT SELECT, INSERT, UPDATE ON access_decisions, audit_logs TO fastapi_user;
GRANT SELECT ON vehicles, hazard_materials, access_rules TO fastapi_user;  -- Para consultas da API
```

**REST Endpoints (FastAPI):**

```python
@router.get("/api/v1/events/{event_id}")
async def get_event(event_id: str, current_user: User = Depends(get_current_user)):
    """Retorna detalhes de um evento específico"""
    async with AsyncSession(engine) as session:
        result = await session.execute(
            select(AccessDecision).where(AccessDecision.event_id == event_id)
        )
        decision = result.scalar_one_or_none()

        if not decision:
            raise HTTPException(404, "Event not found")

        return {
            "event_id": str(decision.event_id),
            "gate_id": decision.gate_id,
            "decision": decision.decision,
            "reason": decision.reason,
            "plate_text": decision.plate_text,
            "placard_un": decision.placard_un,
            "plate_image_url": decision.plate_image_url,
            "placard_image_url": decision.placard_image_url,
            "decided_at": decision.decided_at.isoformat()
        }

@router.post("/api/v1/manual-review/{event_id}")
async def manual_review(
    event_id: str,
    review: ManualReviewRequest,
    current_user: User = Depends(require_role("operator"))
):
    """Permite operador humano revisar e alterar decisão"""
    async with AsyncSession(engine) as session:
        # Atualiza decisão
        result = await session.execute(
            select(AccessDecision).where(AccessDecision.event_id == event_id)
        )
        decision = result.scalar_one_or_none()

        if not decision:
            raise HTTPException(404, "Event not found")

        decision.decision = review.new_decision
        decision.reason = f"Manual review by {current_user.username}: {review.reason}"

        # Cria audit log
        audit = AuditLog(
            event_id=event_id,
            action="MANUAL_REVIEW",
            actor=current_user.username,
            details={"old_decision": decision.decision, "new_decision": review.new_decision},
            timestamp=datetime.utcnow()
        )
        session.add(audit)
        await session.commit()

        # Notifica via WebSocket
        for ws in active_connections.get(decision.gate_id, []):
            await ws.send_json({"type": "manual_review", "event_id": event_id})

        return {"status": "updated"}
```

**WebSocket (Notificações em Tempo Real):**

```python
@app.websocket("/ws/gate/{gate_id}")
async def websocket_gate(websocket: WebSocket, gate_id: str, token: str = Query(...)):
    """WebSocket para receber notificações em tempo real de um gate"""
    # Validar JWT token
    user = verify_jwt(token)
    if not user:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Adicionar à lista de conexões ativas
    if gate_id not in active_connections:
        active_connections[gate_id] = []
    active_connections[gate_id].append(websocket)

    try:
        while True:
            # Manter conexão viva (ping/pong)
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        active_connections[gate_id].remove(websocket)
```

**Separação de Responsabilidades:**

| Componente          | PostgreSQL Access           | Responsabilidades                                                                                                                                         |
| ------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Decision Engine** | READ-ONLY (`decision_user`) | - Ler dados de validação (vehicles, hazard_materials, access_rules)<br>- Executar lógica de decisão<br>- Publicar decisão no Kafka                        |
| **FastAPI**         | READ-WRITE (`fastapi_user`) | - Consumir decisões do Kafka<br>- Persistir decisões (INSERT)<br>- Servir API REST (SELECT)<br>- Notificar WebSocket clients<br>- Manual reviews (UPDATE) |

---

---

### **1.7 FastAPI Backend — API RESTful + WebSocket**

**Arquitetura da API:**

```
FastAPI Application
├── Kafka Consumer (background task)
│   ├── Consome: gate.{gate_id}.decision
│   ├── Persiste no PostgreSQL
│   └── Notifica WebSocket clients
│
├── REST Endpoints
│   ├── GET /api/v1/events/{event_id}
│   ├── GET /api/v1/decisions?gate_id=...&date=...
│   ├── GET /api/v1/plates/{plate_text}/history
│   └── POST /api/v1/manual-review/{event_id}
│
└── WebSocket Endpoint
    └── WS /ws/gate/{gate_id}  (notificações em tempo real)
```

**Autenticação e Autorização:**

1. **JWT (JSON Web Tokens):**

   ```python
   # Login endpoint
   @app.post("/api/v1/auth/login")
   async def login(credentials: LoginSchema):
       user = authenticate_user(credentials.username, credentials.password)
       if not user:
           raise HTTPException(401, "Invalid credentials")

       # Gerar JWT
       access_token = create_access_token(
           data={"sub": user.username, "role": user.role},
           expires_delta=timedelta(hours=8)
       )

       return {"access_token": access_token, "token_type": "bearer"}
   ```

2. **Middleware de Autenticação:**

   ```python
   from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

   security = HTTPBearer()

   async def get_current_user(
       credentials: HTTPAuthorizationCredentials = Depends(security)
   ):
       token = credentials.credentials
       payload = decode_jwt(token)  # Valida signature e expiration

       user = db.query(User).filter(User.username == payload["sub"]).first()
       if not user:
           raise HTTPException(401, "User not found")

       return user
   ```

3. **RBAC (Role-Based Access Control):**

   ```python
   def require_role(required_role: str):
       def decorator(func):
           async def wrapper(*args, user: User = Depends(get_current_user), **kwargs):
               if user.role != required_role:
                   raise HTTPException(403, "Insufficient permissions")
               return await func(*args, user=user, **kwargs)
           return wrapper
       return decorator

   # Exemplo de uso
   @app.post("/api/v1/manual-review/{event_id}")
   @require_role("supervisor")
   async def manual_review(event_id: str, user: User = Depends(get_current_user)):
       # Apenas supervisores podem fazer revisão manual
       ...
   ```

4. **Permissões Granulares:**
   ```sql
   -- Tabela de permissões
   CREATE TABLE user_permissions (
       user_id UUID,
       gate_id VARCHAR,
       can_view BOOLEAN DEFAULT TRUE,
       can_approve BOOLEAN DEFAULT FALSE,
       can_override BOOLEAN DEFAULT FALSE
   );
   ```

**Fluxo de Acesso à Imagem:**

1. **Cliente faz request:**

   ```http
   GET /api/v1/events/{event_id}
   Authorization: Bearer <JWT_TOKEN>
   ```

2. **API valida token e busca no PostgreSQL:**

   ```python
   @app.get("/api/v1/events/{event_id}")
   async def get_event(event_id: str, user: User = Depends(get_current_user)):
       # Buscar evento e decisão
       decision = db.query(AccessDecision).filter_by(event_id=event_id).first()

       # Buscar detecções de placa (com referência MinIO)
       plate_detection = db.query(LicensePlateDetection).filter_by(
           event_id=event_id
       ).first()

       # Buscar detecção de placard
       placard_detection = db.query(PlacardDetection).filter_by(
           event_id=event_id
       ).first()

       # Gerar presigned URLs (válidos por 1h)
       plate_image_url = minio_client.presigned_get_object(
           bucket_name=plate_detection.minio_bucket,
           object_name=plate_detection.minio_object_key,
           expires=timedelta(hours=1)
       )

       placard_image_url = minio_client.presigned_get_object(
           bucket_name=placard_detection.minio_bucket,
           object_name=placard_detection.minio_object_key,
           expires=timedelta(hours=1)
       ) if placard_detection else None

       return {
           "event_id": event_id,
           "decision": decision.decision,
           "plate_text": plate_detection.plate_text,
           "plate_image_url": plate_image_url,
           "placard_un": placard_detection.placard_un if placard_detection else None,
           "placard_image_url": placard_image_url,
           "timestamp": decision.decided_at
       }
   ```

3. **Cliente recebe response:**

   ```json
   {
     "event_id": "abc-123",
     "decision": "APPROVE",
     "plate_text": "12-AB-34",
     "plate_image_url": "https://minio:9000/license-plates/gate-01/.../abc-123.jpg?X-Amz-Expires=3600&...",
     "placard_un": "1203",
     "placard_image_url": "https://minio:9000/hazard-placards/...",
     "timestamp": "2025-11-15T10:30:00Z"
   }
   ```

4. **Frontend faz request direto ao MinIO:**
   - Usa o `presigned_url` recebido da API
   - MinIO valida signature e expiration
   - Retorna imagem sem necessidade de autenticação adicional

**WebSocket para Notificações em Tempo Real:**

```python
# Conexão WebSocket requer autenticação
@app.websocket("/ws/gate/{gate_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    gate_id: str,
    token: str = Query(...)  # Token JWT via query param
):
    # Validar token
    try:
        payload = decode_jwt(token)
        user = get_user_by_username(payload["sub"])
    except:
        await websocket.close(code=1008)  # Policy violation
        return

    # Verificar permissão para gate
    if not has_permission(user, gate_id):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Adicionar à lista de clients ativos
    active_connections[gate_id].append(websocket)

    try:
        while True:
            # Aguardar mensagens (keepalive)
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections[gate_id].remove(websocket)

# Background task que consome Kafka e notifica WebSocket clients
async def kafka_to_websocket_bridge():
    consumer = Consumer(...)
    consumer.subscribe(['gate.*.decision'])

    while True:
        msg = consumer.poll(1.0)
        if msg and not msg.error():
            decision = json.loads(msg.value())
            gate_id = decision["gate_id"]

            # Notificar todos os clients conectados a este gate
            for ws in active_connections.get(gate_id, []):
                await ws.send_json(decision)
```

**Segurança Adicional:**

1. **Rate Limiting:**

   ```python
   from slowapi import Limiter

   limiter = Limiter(key_func=get_remote_address)

   @app.get("/api/v1/events/{event_id}")
   @limiter.limit("10/minute")  # Max 10 requests por minuto
   async def get_event(...):
       ...
   ```

2. **CORS Configurado:**

   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["https://frontend.logistics.com"],
       allow_credentials=True,
       allow_methods=["GET", "POST"],
       allow_headers=["Authorization"]
   )
   ```

3. **Audit Log:**
   ```sql
   INSERT INTO audit_logs (
       user_id, action, resource, timestamp, ip_address
   ) VALUES (
       user.id, 'VIEW_EVENT', event_id, NOW(), request.client.host
   );
   ```

---

### **1.8 Consumers Externos (Interfaces & Sistemas)**

**Frontend React (Porteiro):**

- Consome API REST para histórico e detalhes
- WebSocket para notificações em tempo real
- Visualiza stream 720p via HLS: `http://nginx:8080/hls/gate01_720p.m3u8`
- Acessa imagens via presigned URLs do MinIO

**Sistema de Controle de Portão:**

- Consome diretamente `gate.{gate_id}.decision` via Kafka
- Aciona atuadores físicos (barreira, semáforo)
- Publica feedback em `gate.{gate_id}.actuator.status`

**Sistema de Logs/Metrics:**

- Consome todos os tópicos Kafka
- Agrega métricas (latências, throughputs)
- Dashboards Grafana/Prometheus

---

## 2. Fluxo Temporal Completo (Atualizado)

```
T+0ms:    Caminhão entra no FOV da câmara

T+50ms:   Nginx RTMP recebe frames e distribui

T+100ms:  Agent-A (720p) deteta truck (frame 1)

T+200ms:  Agent-A confirma (frame 2)

T+300ms:  Agent-A publica truck-detected (frame 3)
          ├─ Kafka: gate.01.detection
          └─ Particionamento: track_id → partition 1

T+310ms:  Agent-B e Agent-C recebem mensagem (consumer poll)
          ├─ Agent-B: _handle_truck_detection()
          ├─ Agent-C: _handle_truck_detection()
          └─ Ambos requisitam stream 4K via Nginx RTMP

T+320ms:  Nginx RTMP faz pull do stream 4K da câmara

T+500ms:  Agent-B captura frame 4K
          ├─ YOLO deteta placa
          └─ Crop extraído

T+600ms:  Agent-B faz upload para MinIO
          └─ Bucket: license-plates/gate-01/{event_id}/plate_0.jpg

T+700ms:  Agent-B executa OCR
          └─ Resultado: "12-AB-34" (conf: 0.91)

T+800ms:  Agent-B publica license-plate-detected
          ├─ Payload inclui minio_object_key
          └─ API consome e persiste no PostgreSQL

T+850ms:  Agent-C processa placard (em paralelo)
          ├─ Upload para MinIO (hazard-placards bucket)
          └─ Publica placard-detected

T+1000ms: Decision Engine recebe ambas as detecções
          ├─ Correlaciona por event_id
          ├─ Consulta PostgreSQL (whitelist/blacklist)
          └─ Aplica regras de negócio

T+1100ms: Decision Engine publica APPROVE
          └─ API persiste decisão no PostgreSQL

T+1110ms: API notifica via WebSocket
          ├─ Frontend do porteiro recebe notificação
          └─ Exibe: "Acesso autorizado - Placa: 12-AB-34"

T+1150ms: Frontend faz GET /api/v1/events/{event_id}
          ├─ API retorna presigned URLs do MinIO
          └─ Frontend carrega imagens diretamente do MinIO

T+1200ms: Sistema físico abre portão
          └─ Publica feedback em gate.01.actuator.status
```

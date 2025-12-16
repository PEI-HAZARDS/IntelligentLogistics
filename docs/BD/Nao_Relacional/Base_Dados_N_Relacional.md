Arquitetura da Base de Dados Não Relacional (MongoDB)

**Projeto: PEI – Intelligent Logistics**

A base de dados MongoDB funciona como um sistema de armazenamento orientado a eventos, complementando o modelo relacional do porto em PostgreSQL.

Enquanto o PostgreSQL guarda o estado oficial e validado (e.g., chegadas, cargas), o MongoDB captura detecções IA, logs técnicos, eventos operacionais e telemetria, servindo como fonte para o Decision Feed e para consultas rápidas via o `data_module`.

## 1. Objetivo do MongoDB

MongoDB é utilizado para armazenar dados não estruturados ou altamente variáveis, tais como:

- Detecções IA (matrículas, confiança, imagens, metadados)
- Eventos operacionais (ações do operador, autorizações, workflow)
- Logs internos de microserviços
- Dados de sensores / telemetria
- Falhas de OCR / YOLO
- Outputs volumosos de IA

O `data_module` (microserviço central) interage diretamente com MongoDB para armazenar dados recebidos via APIs HTTP (e.g., POST de agentes) e expor consultas (e.g., GET para frontend).

## 2. Estrutura das Coleções MongoDB

A BD NoSQL organiza-se em coleções independentes, otimizadas para cada tipo de evento. O `data_module` insere documentos via services (e.g., `event_service.py`) e expõe endpoints para leitura/escrita.

### 2.1 detections — Detecções IA

Cada vez que um camião é detetado pela IA ou sensores visuais, um documento é criado. Agentes fazem POST /detections no `data_module`, que insere aqui.

```json
{
  "timestamp": "2025-02-16T10:22:53Z",
  "gate_id": 2,
  "matricula_detectada": "00-AA-11",
  "confidence": 0.93,
  "source": "IA",
  "image_path": "/detections/2025/02/16/abc123.jpg",
  "processed": false,
  "matched_chegada_id": null,
  "alert_generated": false,
  "metadata": {
    "camera_id": "C1",
    "yolo_model": "yolov11",
    "latency_ms": 32
  }
}
```

**Índices recomendados**: timestamp (desc), matricula_detectada, gate_id, processed.

**Integração com data_module**: POST /detections insere; GET /detections consulta (com filtros).

### 2.2 events — Eventos Operacionais

Regista ações humanas/automáticas relacionadas ao fluxo logístico. O `data_module` armazena eventos de decisão/autorização aqui.

```json
{
  "timestamp": "2025-02-16T10:45:00Z",
  "type": "operador_validou",
  "gate_id": 1,
  "user_id": 103,
  "data": {
    "matricula": "AA-00-XY",
    "id_chegada": 332,
    "estado": "autorizada"
  }
}
```

**Índices recomendados**: timestamp (desc), type, gate_id.

**Integração com data_module**: POST /events insere; GET /events consulta.

### 2.3 system_logs — Logs Técnicos

Regista mensagens técnicas provenientes dos microserviços. Microserviços fazem POST /logs no `data_module`, que insere aqui.

```json
{
  "timestamp": "2025-02-16T09:10:00Z",
  "service": "ocr-service",
  "level": "warn",
  "message": "Timeout na câmara 2",
  "context": {
    "camera_id": "C2",
    "retry": 1
  }
}
```

**Índices recomendados**: timestamp (desc), service, level.

**Integração com data_module**: POST /logs insere; GET /logs consulta (para debug).

### 2.4 ocr_failures — Falhas de OCR

```json
{
  "timestamp": "2025-02-16T11:10:00Z",
  "image_path": "/failed/001.jpg",
  "reason": "---",
  "gate_id": 3
}
```

**Índices recomendados**: timestamp (desc), gate_id.

**Integração com data_module**: POST /ocr-failures insere; GET /ocr-failures consulta.

## 3. Integração com o Decision Feed e Data_Module

O Decision Feed é o pipeline de decisão que transforma detecções em ações logísticas.

**Fluxo geral**:
1. Agente deteta camião → POST /detections no `data_module` → Insere em `detections` (MongoDB).
2. `data_module` chama Decision Engine (HTTP) para processar → Recebe decisão.
3. `data_module` insere evento em `events` (MongoDB) e atualiza PostgreSQL (e.g., chegada).
4. Frontend consulta GET /events ou /detections no `data_module` para display.

**APIs do data_module**:
- POST /detections: Recebe deteção, armazena em MongoDB.
- GET /events: Lista eventos (com paginação/filtros).
- GET /detections: Lista detecções não processadas.
- POST /logs: Recebe logs de microserviços.

Isso garante que MongoDB seja acessível via HTTP, mantendo o `data_module` como hub.
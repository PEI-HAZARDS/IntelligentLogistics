*Arquitetura da Base de Dados Não Relacional (MongoDB)*

Projeto: PEI – Intelligent Logistics

A base de dados MongoDB funciona como um sistema de armazenamento orientado a eventos, complementando o modelo relacional do porto em PostgreSQL.

Enquanto o PostgreSQL guarda o estado oficial e validado, o MongoDB captura detecções IA, logs técnicos, eventos operacionais e telemetria, servindo como fonte para o Decision Feed.

# 1. Objetivo do MongoDB

MongoDB é utilizado para armazenar dados não estruturados ou altamente variáveis, tais como:

    - Detecções IA (matrículas, confiança, imagens, metadados)
    - Eventos operacionais (ações do operador, autorizações, workflow)
    - Logs internos de microserviços
    - Dados de sensores / telemetria
    - Falhas de OCR / YOLO
    - Outputs volumosos de IA

# 2. Estrutura das Coleções MongoDB

A BD NoSQL organiza-se em coleções independentes, otimizadas para cada tipo de evento.

## 2.1 detections — Detecções IA

Cada vez que um camião é detetado pela IA ou sensores visuais, um documento é criado.

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

Índices recomendados: timestamp, matricula_detectada, gate_id, processed

## 2.2 events — Eventos Operacionais

Regista ações humanas/automáticas relacionadas ao fluxo logístico.

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

## 2.3 system_logs — Logs Técnicos

Regista mensagens técnicas provenientes dos microserviços.

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

## 2.4 ocr_failures — Falhas de OCR

    {
      "timestamp": "2025-02-16T11:10:00Z",
      "image_path": "/failed/001.jpg",
      "reason": "---",
      "gate_id": 3
    }


Integração com o Decision Feed

O Decision Feed é o pipeline de decisão que transforma detecções em ações logísticas.

Fluxo geral:

    

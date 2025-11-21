# Mudanças para Integração Nginx RTMP

Este documento lista todas as mudanças necessárias para migrar de RTSP direto para RTMP via Nginx.

---

## ✅ **Sim, continuas a usar `RTSPstream.py`!**

O `RTSPstream.py` já suporta RTMP através do OpenCV com backend FFmpeg. Apenas precisas mudar as URLs.

---

## 📋 Mudanças Realizadas

### **1. AgentA.py**

**Antes:**

```python
RTSP_STREAM_LOW = "rtsp://10.255.35.86:554/stream2"
```

**Depois:**

```python
# URL do stream LOW (720p) via Nginx RTMP
RTSP_STREAM_LOW = os.getenv("RTSP_STREAM_LOW", "rtmp://nginx-rtmp/streams_low/gate01")
```

**Comportamento:**

- Agent-A conecta automaticamente ao stream 720p via Nginx RTMP
- Stream está sempre disponível (always-on)
- Nginx faz load balancing se houver múltiplos Agents

---

### **2. AgentB.py**

**Antes:**

```python
RTSP_STREAM_HIGH = "rtsp://10.255.35.86:554/stream1"

def __init__(self):
    # ...
    self.stream = RTSPStream(RTSP_STREAM_HIGH)  # Conecta sempre
```

**Depois:**

```python
# URL do stream HIGH (4K) via Nginx RTMP
RTSP_STREAM_HIGH = os.getenv("RTSP_STREAM_HIGH", "rtmp://nginx-rtmp/streams_high/gate01")

def __init__(self):
    # ...
    self.stream = None  # NÃO conecta no __init__

def _get_frames(self, num_frames=1):
    # Conectar ao stream se não estiver conectado (on-demand)
    if self.stream is None:
        logger.info(f"[AgentB] Connecting to RTMP stream: {RTSP_STREAM_HIGH}")
        self.stream = RTSPStream(RTSP_STREAM_HIGH)
    # ... resto do código
```

**Comportamento:**

- Agent-B NÃO conecta automaticamente
- Só conecta ao stream 4K quando `_get_frames()` é chamado
- Isto acontece quando recebe evento `truck-detected` do Kafka
- Poupa CPU quando não há caminhões

---

### **3. RTSPstream.py**

**Melhorias:**

```python
class RTSPStream:
    """
    Stream reader genérico - suporta RTSP, RTMP e HTTP via FFmpeg.

    Exemplos:
    - RTSP: rtsp://10.255.35.86:554/stream1
    - RTMP: rtmp://nginx-rtmp/streams_low/gate01
    - HTTP: http://nginx-rtmp:8080/hls/low/gate01.m3u8
    """
    def __init__(self, url):
        logger.info(f"[RTSPStream] Starting stream from: {url}")
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        # ...

        if not self.cap.isOpened():
            raise ConnectionError(f"Failed to connect to stream: {url}")
        # ...

    def update(self):
        """Thread que lê frames continuamente"""
        consecutive_failures = 0
        max_failures = 10

        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(f"[RTSPStream] Failed to read frame ({consecutive_failures}/{max_failures})")

                if consecutive_failures >= max_failures:
                    logger.error("[RTSPStream] Too many failures, stopping.")
                    self.running = False
                    break

                time.sleep(0.5)
```

**Melhorias:**

- ✅ Suporte explícito para RTMP/RTSP/HTTP
- ✅ Error handling melhorado (retry com contador)
- ✅ Logs mais informativos
- ✅ Raise exception se falhar conexão inicial
- ✅ Para thread após muitas falhas consecutivas

---

### **4. docker-compose.yml**

**Adicionado serviço Nginx RTMP:**

```yaml
services:
  # ============================================
  # INFRAESTRUTURA - Nginx RTMP
  # ============================================
  nginx-rtmp:
    build: ./streaming_middleware
    container_name: nginx-rtmp
    ports:
      - "1935:1935" # RTMP (para Agents)
      - "8080:8080" # HTTP (HLS para Frontend)
    environment:
      - CAMERA_IP=10.255.35.86
      - RTSP_PORT=554
      - STREAM_LOW_PATH=stream2 # 720p
      - STREAM_HIGH_PATH=stream1 # 4K
      - GATE_ID=gate01
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
```

---

### **5. Variáveis de Ambiente**

**Agent-A:**

```bash
# .env ou docker-compose
RTSP_STREAM_LOW=rtmp://nginx-rtmp/streams_low/gate01
KAFKA_BOOTSTRAP=10.255.32.64:9092
```

**Agent-B:**

```bash
RTSP_STREAM_HIGH=rtmp://nginx-rtmp/streams_high/gate01
KAFKA_BOOTSTRAP=10.255.32.64:9092
```

**Nginx RTMP:**

```bash
CAMERA_IP=10.255.35.86
RTSP_PORT=554
STREAM_LOW_PATH=stream2
STREAM_HIGH_PATH=stream1
GATE_ID=gate01
```

---

## 🔄 Fluxo Completo

### **Antes (RTSP Direto):**

```
Câmara IP
    ├─ RTSP stream2 (720p) → Agent-A (conexão direta)
    └─ RTSP stream1 (4K)   → Agent-B (conexão direta)

Problemas:
❌ Câmara lida com N conexões diretas
❌ Frontend não pode consumir RTSP
❌ Sem load balancing
```

### **Depois (RTMP via Nginx):**

```
Câmara IP
    ├─ RTSP stream2 (720p)
    └─ RTSP stream1 (4K)
    │
    ▼
FFmpeg Ingest (inside Nginx container)
    ├─ Converte RTSP → RTMP
    └─ Publica no Nginx
    │
    ▼
Nginx RTMP Server
    ├─ rtmp://nginx-rtmp/streams_low/gate01  → Agent-A (always-on)
    ├─ rtmp://nginx-rtmp/streams_high/gate01 → Agent-B (on-demand via Kafka)
    └─ http://nginx-rtmp:8080/hls/low/...    → Frontend (HLS/DASH)

Vantagens:
✅ Câmara tem apenas 2 conexões (uma por stream)
✅ Nginx distribui para N consumidores
✅ Frontend consome via HTTP (HLS)
✅ Load balancing automático
✅ Always-on streams (baixa latência de ativação)
```

---

## 🧪 Como Testar

### **1. Subir Nginx RTMP:**

```bash
cd src
docker-compose up nginx-rtmp -d
```

### **2. Verificar logs:**

```bash
docker logs -f nginx-rtmp

# Esperado:
# [Ingest] LOW stream started (PID: 123)
# [Ingest] HIGH stream started (PID: 456)
```

### **3. Testar streams RTMP:**

```bash
# Testar com ffplay (se tiveres instalado)
ffplay rtmp://localhost:1935/streams_low/gate01
ffplay rtmp://localhost:1935/streams_high/gate01
```

### **4. Testar HLS no navegador:**

```
http://localhost:8080/hls/low/gate01.m3u8
http://localhost:8080/hls/high/gate01.m3u8
```

### **5. Ver estatísticas:**

```bash
curl http://localhost:8080/stat
```

### **6. Subir Agent-A:**

```bash
docker-compose up agent-a -d
docker logs -f agent-a

# Esperado:
# [AgentA] Connecting to RTMP stream (via Nginx): rtmp://nginx-rtmp/streams_low/gate01
# [RTSPStream] Stream started successfully.
```

### **7. Subir Agent-B:**

```bash
docker-compose up agent-b -d
docker logs -f agent-b

# Esperado (quando receber evento Kafka):
# [AgentB] Connecting to RTMP stream: rtmp://nginx-rtmp/streams_high/gate01
# [RTSPStream] Stream started successfully.
```

---

## 📊 Comparação: Antes vs Depois

| Aspecto               | RTSP Direto                  | RTMP via Nginx                                 |
| --------------------- | ---------------------------- | ---------------------------------------------- |
| **Conexões à câmara** | N (uma por Agent)            | 2 (uma por stream)                             |
| **Frontend**          | ❌ RTSP não suporta web      | ✅ HLS via HTTP                                |
| **Latência**          | ~500ms                       | ~500ms (RTMP) / ~4-6s (HLS)                    |
| **Load Balancing**    | ❌ Não                       | ✅ Sim                                         |
| **Escalabilidade**    | Baixa (limitada pela câmara) | Alta (Nginx distribui)                         |
| **Código Python**     | `RTSPstream.py`              | **Mesmo `RTSPstream.py`** ✅                   |
| **On-Demand 4K**      | Agent-B liga/desliga         | **Nginx always-on, Agent-B conecta on-demand** |

---

## ✅ Resumo das Mudanças no Código

| Ficheiro               | Tipo de Mudança | Descrição                                       |
| ---------------------- | --------------- | ----------------------------------------------- |
| **AgentA.py**          | URL             | `rtsp://...` → `rtmp://nginx-rtmp/...`          |
| **AgentB.py**          | URL + Lógica    | `rtmp://nginx-rtmp/...` + conexão on-demand     |
| **RTSPstream.py**      | Melhorias       | Logs + error handling + suporte multi-protocolo |
| **docker-compose.yml** | Novo serviço    | Adiciona `nginx-rtmp`                           |
| **Nenhuma mudança**    | -               | YOLO, OCR, Kafka logic (zero mudanças!)         |

---

## 🎯 Conclusão

**Pergunta:** Preciso mudar muito código?  
**Resposta:** **Não!** Apenas URLs (5 linhas) e lógica de conexão on-demand no Agent-B.

**Pergunta:** Ainda uso `RTSPstream.py`?  
**Resposta:** **Sim!** OpenCV com FFmpeg já suporta RTMP nativamente.

**Pergunta:** O que muda na prática?  
**Resposta:** Agents conectam ao Nginx em vez da câmara direta. O resto é **exatamente igual**.

---

## 🚀 Próximos Passos

1. ✅ Nginx RTMP configurado
2. ✅ Scripts de ingest criados
3. ✅ Agent-A e Agent-B atualizados
4. ✅ docker-compose.yml atualizado
5. ⏳ **Testar integração completa**
6. ⏳ **Frontend consumir HLS**

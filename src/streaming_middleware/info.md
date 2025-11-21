# Nginx RTMP Streaming Middleware

Este serviço atua como middleware de streaming entre câmaras IP e a aplicação Intelligent Logistics.

## 🎯 Funcionalidades

- **Ingest RTSP**: Converte streams RTSP das câmaras para RTMP
- **Re-distribuição**: Permite múltiplos consumidores (Agents) sem sobrecarregar câmara
- **Transcoding**: Gera HLS/DASH para consumo web (frontend)
- **Load Balancing**: Distribui streams para vários consumidores
- **Always-On**: Mantém streams 720p e 4K sempre disponíveis

## 📊 Arquitetura

```
Câmara IP (RTSP)
    │
    ├─ rtsp://10.255.35.86:554/stream2 (720p)
    └─ rtsp://10.255.35.86:554/stream1 (4K)
    │
    ▼
FFmpeg Ingest (dentro do container)
    │
    ├─ Converte RTSP → RTMP
    └─ Publica no Nginx local
    │
    ▼
Nginx RTMP Server
    │
    ├─ rtmp://nginx-rtmp/streams_low/gate01  (para Agents)
    ├─ rtmp://nginx-rtmp/streams_high/gate01 (para Agents)
    ├─ http://nginx-rtmp:8080/hls/low/gate01.m3u8  (para Frontend)
    └─ http://nginx-rtmp:8080/hls/high/gate01.m3u8 (para Frontend)
```


## 🔧 Variáveis de Ambiente

| Variável           | Descrição               | Default        |
| ------------------ | ----------------------- | -------------- |
| `CAMERA_IP`        | IP da câmara RTSP       | `10.255.35.86` |
| `RTSP_PORT`        | Porta RTSP da câmara    | `554`          |
| `STREAM_LOW_PATH`  | Path do stream 720p     | `stream2`      |
| `STREAM_HIGH_PATH` | Path do stream 4K       | `stream1`      |
| `GATE_ID`          | Identificador do portão | `gate01`       |

## 📡 Endpoints Disponíveis

### **RTMP (Consumo pelos Agents):**

- `rtmp://nginx-rtmp:1935/streams_low/gate01` - Stream 720p
- `rtmp://nginx-rtmp:1935/streams_high/gate01` - Stream 4K

### **HTTP (Consumo pelo Frontend):**

- `http://nginx-rtmp:8080/hls/low/gate01.m3u8` - HLS 720p
- `http://nginx-rtmp:8080/hls/high/gate01.m3u8` - HLS 4K
- `http://nginx-rtmp:8080/dash/low/gate01.mpd` - DASH 720p (opcional)
- `http://nginx-rtmp:8080/stat` - Estatísticas RTMP
- `http://nginx-rtmp:8080/health` - Health check

## 🧪 Testar

### **1. Verificar se streams estão ativos:**

```bash
curl http://localhost:8080/stat
```

### **2. Consumir HLS no navegador:**

```
http://localhost:8080/hls/low/gate01.m3u8
```

### **3. Testar RTMP com ffplay:**

```bash
ffplay rtmp://localhost:1935/streams_low/gate01
```

### **4. Health check:**

```bash
curl http://localhost:8080/health
# Expected: OK
```

## 🔍 Debug

### **Ver logs do container:**

```bash
docker logs -f nginx-rtmp
```

### **Ver logs apenas do FFmpeg LOW:**

```bash
docker logs nginx-rtmp 2>&1 | grep "FFmpeg-LOW"
```

### **Ver logs apenas do FFmpeg HIGH:**

```bash
docker logs nginx-rtmp 2>&1 | grep "FFmpeg-HIGH"
```

### **Entrar no container:**

```bash
docker exec -it nginx-rtmp bash
```

### **Verificar processos:**

```bash
docker exec nginx-rtmp ps aux | grep ffmpeg
```

## 📊 Estatísticas RTMP

Aceder `http://localhost:8080/stat` para ver:

- Streams ativos
- Bitrate (bw_in/bw_out)
- Número de viewers
- FPS
- Codec info

## 🎯 Fluxo de Dados

### **Agent-A (sempre conectado ao LOW):**

```python
from shared_utils.RTSPstream import RTSPStream

cap = RTSPStream("rtmp://nginx-rtmp/streams_low/gate01")
frame = cap.read()
```

### **Agent-B (conecta ao HIGH quando Kafka manda):**

```python
# Aguarda evento do Kafka
event = consumer.poll()

# Conecta ao stream 4K
cap = RTSPStream("rtmp://nginx-rtmp/streams_high/gate01")
frame = cap.read()

# Processa e desconecta
cap.release()
```

### **Frontend (consome HLS):**

```jsx
import Hls from "hls.js";

const hls = new Hls();
hls.loadSource("http://nginx-rtmp:8080/hls/low/gate01.m3u8");
hls.attachMedia(videoElement);
```

## 🛡️ Segurança

- **Publish**: Apenas `127.0.0.1` pode publicar streams (FFmpeg ingest)
- **Play**: Qualquer endereço pode consumir (Agents, Frontend)
- **CORS**: Habilitado para frontend consumir de domínio diferente

## 📈 Performance

### **Latência:**

- RTMP para Agents: ~500ms-1s
- HLS para Frontend: ~4-6s (devido a fragmentos de 2s)

### **Bandwidth:**

- Stream LOW (720p): ~2-4 Mbps
- Stream HIGH (4K): ~15-25 Mbps

### **CPU:**

- Nginx: ~5-10% (re-transmissão)
- FFmpeg (2 processos): ~15-30% (copy codec, sem transcoding)

## 🔄 Restart Automático

O script `ingest_streams.sh` monitora processos FFmpeg e reinicia automaticamente se falharem:

```bash
[Ingest] HIGH stream died, restarting...
[Ingest] HIGH stream restarted (PID: 12345)
```

## 📝 Notas

- Streams são **always-on** (ambas 720p e 4K sempre ingeridas)
- Kafka gere quando Agent-B deve **consumir** o stream HIGH (não on-demand do Nginx)
- HLS fragmentos são limpos automaticamente (`hls_cleanup on`)
- Container tem health check automático a cada 30s

## 🤝 Integração com Microserviços

Este serviço é **infraestrutura**, não um microserviço. Ele:

- ✅ É configurado via `nginx.conf` + environment variables
- ✅ Serve múltiplos portões (basta adicionar `GATE_ID=gate02`)


## 🚀 Como Usar

### **Build da imagem:**

```bash
docker-compose build
```


```bash
docker-compose up -d
```

# Para Browser
curl http://localhost:8080/hls/low/gate01.m3u8


# Testar latência RTSP direto
time ffmpeg -i rtsp://10.255.35.86:554/stream2 -frames:v 1 -f null - 2>&1 | grep "time="

# Testar latência RTMP via Nginx
time ffmpeg -i rtmp://localhost:1935/streams_low/gate01 -frames:v 1 -f null - 2>&1 | grep "time="
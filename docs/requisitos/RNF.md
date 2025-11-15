

## ⚙️ Requisitos Não Funcionais (RNF)

### **RNF1 - Performance**
- **RNF1.1**: O sistema deve processar stream 720p a mínimo 5 fps
- **RNF1.2**: O sistema deve processar stream 4K a mínimo 2 fps
- **RNF1.3**: A latência end-to-end (detecção → decisão) deve ser < 2 segundos
- **RNF1.4**: Consultas ao PostgreSQL devem ter latência < 20ms (p99)
- **RNF1.5**: Upload de imagens para MinIO deve ter latência < 200ms
- **RNF1.6**: Publicação de eventos no Kafka deve ter latência < 50ms
- **RNF1.7**: API REST deve responder em < 100ms (p95) para queries simples
- **RNF1.8**: WebSocket deve ter latência < 500ms para notificações

### **RNF2 - Escalabilidade**
- **RNF2.1**: O sistema deve suportar múltiplos portões simultaneamente (1 Agent-A por portão)
- **RNF2.2**: O sistema deve suportar múltiplas instâncias de Agent-B/C por portão
- **RNF2.3**: O sistema deve escalar horizontalmente via partições Kafka (mínimo 3)
- **RNF2.4**: O sistema deve suportar pool de conexões PostgreSQL (min 10, max 50)
- **RNF2.5**: O sistema deve suportar mínimo 100 conexões WebSocket simultâneas
- **RNF2.6**: O sistema deve suportar processar 10 caminhões/minuto por portão

### **RNF3 - Disponibilidade**
- **RNF3.1**: O sistema deve ter uptime de 99.5% (SLA)
- **RNF3.2**: Kafka deve reter mensagens por mínimo 7 dias
- **RNF3.3**: O sistema deve continuar operando se FastAPI cair (Decision Engine independente)
- **RNF3.4**: O sistema deve permitir reprocessamento de eventos (replay Kafka)
- **RNF3.5**: PostgreSQL deve ter backup diário automático
- **RNF3.6**: MinIO deve ter replicação de objetos (mínimo 2 cópias)

### **RNF4 - Resiliência**
- **RNF4.1**: O sistema deve reconectar automaticamente a streams RTSP em caso de falha
- **RNF4.2**: O sistema deve ter retry exponencial para falhas de rede (max 3 tentativas)
- **RNF4.3**: O sistema deve ter circuit breaker para chamadas ao PostgreSQL
- **RNF4.4**: O sistema deve validar conexões PostgreSQL antes de usar (pool_pre_ping)
- **RNF4.5**: O sistema deve logar erros em formato estruturado (JSON)
- **RNF4.6**: O sistema deve ter health checks para todos os serviços (HTTP /health)

### **RNF5 - Segurança**
- **RNF5.1**: Todas as comunicações devem usar TLS/SSL
- **RNF5.2**: JWT tokens devem ter expiração de 8 horas
- **RNF5.3**: Presigned URLs do MinIO devem ter expiração configurável (1-24h)
- **RNF5.4**: PostgreSQL deve usar usuários com permissões mínimas (least privilege)
- **RNF5.5**: Senhas devem ser hashadas com bcrypt (cost factor ≥ 12)
- **RNF5.6**: API deve ter rate limiting (10 req/min por IP para endpoints críticos)
- **RNF5.7**: API deve ter CORS configurado (whitelist de origens)
- **RNF5.8**: Audit logs devem ser imutáveis (append-only)
- **RNF5.9**: Streams RTSP devem usar RTSPS (RTSP over TLS) quando disponível

### **RNF6 - Observabilidade**
- **RNF6.1**: Todos os serviços devem ter logging estruturado (JSON)
- **RNF6.2**: O sistema deve expor métricas Prometheus (latência, throughput, erros)
- **RNF6.3**: O sistema deve ter tracing distribuído (event_id correlaciona pipeline completo)
- **RNF6.4**: O sistema deve ter dashboards Grafana para:
  - Latências por componente
  - Taxa de detecções por portão
  - Consumer lag Kafka
  - Taxa de aprovação/rejeição
- **RNF6.5**: O sistema deve ter alertas para:
  - Consumer lag > 1000 mensagens
  - Latência API > 500ms (p99)
  - Taxa de erro > 5%
  - Disco MinIO > 80%

### **RNF7 - Manutenibilidade**
- **RNF7.1**: O código deve seguir PEP 8 (Python)
- **RNF7.2**: O código deve ter cobertura de testes ≥ 70%
- **RNF7.3**: Todos os componentes devem ter documentação API (OpenAPI/Swagger)
- **RNF7.4**: O sistema deve usar versionamento semântico (SemVer)
- **RNF7.5**: Docker images devem ser multi-stage para reduzir tamanho
- **RNF7.6**: Configurações devem estar externalizadas (environment variables)

### **RNF8 - Deploy e CI/CD**
- **RNF8.1**: O sistema deve usar GitHub Actions para CI/CD
- **RNF8.2**: Deploy deve ser automático após push na branch main
- **RNF8.3**: Pipeline CI deve executar testes antes de deploy
- **RNF8.4**: Deploy deve ser via SSH sobre VPN (segurança)
- **RNF8.5**: Deploy deve ter rollback automático em caso de falha
- **RNF8.6**: Docker images devem ser tagueadas com commit SHA
- **RNF8.7**: Deploy deve fazer health check antes de considerar sucesso

### **RNF9 - Infraestrutura**
- **RNF9.1**: Todos os serviços devem rodar em containers Docker
- **RNF9.2**: Kafka deve usar KRaft mode (sem Zookeeper)
- **RNF9.3**: Nginx RTMP deve ter buffer de 10 segundos para streams
- **RNF9.4**: PostgreSQL deve ter índices em:
  - `vehicles.plate_number`
  - `hazard_materials.un_number`
  - `access_decisions.event_id`
  - `access_decisions.gate_id, decided_at`
- **RNF9.5**: MinIO deve ter buckets separados por tipo (license-plates, hazard-placards)
- **RNF9.6**: Todos os volumes Docker devem ser persistentes

### **RNF10 - Modelos de Machine Learning**
- **RNF10.1**: YOLO truck detection deve ter mAP ≥ 0.85 em dataset de teste
- **RNF10.2**: YOLO plate detection deve ter mAP ≥ 0.90 em dataset português
- **RNF10.3**: OCR deve ter accuracy ≥ 95% em placas portuguesas
- **RNF10.4**: Modelos devem ser versionados (MLflow ou DVC)
- **RNF10.5**: Inferência YOLO 720p deve processar em < 100ms (GPU) ou < 500ms (CPU)
- **RNF10.6**: Inferência YOLO 4K deve processar em < 300ms (GPU) ou < 1500ms (CPU)

### **RNF11 - Compliance e Auditoria**
- **RNF11.1**: O sistema deve manter histórico de todas as decisões por mínimo 1 ano
- **RNF11.2**: Imagens devem ser armazenadas por mínimo 30 dias
- **RNF11.3**: Audit logs devem incluir: quem, quando, o quê, IP origem
- **RNF11.4**: O sistema deve permitir exportação de dados para relatórios
- **RNF11.5**: O sistema deve estar em conformidade com GDPR (direito ao esquecimento)

### **RNF12 - Usabilidade**
- **RNF12.1**: Interface web deve ser responsiva (mobile-first)
- **RNF12.2**: Notificações em tempo real devem ser visualmente destacadas
- **RNF12.3**: Visualização de streams deve ter latência < 5 segundos (HLS)
- **RNF12.4**: Imagens de detecção devem carregar em < 2 segundos
- **RNF12.5**: Interface deve suportar múltiplos idiomas (PT, EN)

---

## Para entrega

- **RNF2.1**: O sistema deve suportar múltiplos portões simultaneamente
- **RNF8.3**: Pipeline CI deve garantir a criaçaõ da imagem na VM e execução de testes antes de 
- **RNF11.1**: O sistema deve manter histórico de todas as decisões por mínimo x tempo (dont know)
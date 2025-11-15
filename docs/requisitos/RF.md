
## 📋 Requisitos Funcionais (RF)

### **RF1 - Detecção de Veículos**
- **RF1.1**: O sistema deve detectar caminhões em stream de vídeo 720p em tempo real
- **RF1.2**: O sistema deve manter tracking consistente de veículos (track_id único)
- **RF1.3**: O sistema deve confirmar detecção após N frames consecutivos (ex: 3 frames)
- **RF1.4**: O sistema deve aplicar threshold mínimo de confiança (ex: 0.75) antes de publicar evento

### **RF2 - Detecção de Matrícula**
- **RF2.1**: O sistema deve ativar stream 4K sob demanda quando caminhão for detectado
- **RF2.2**: O sistema deve detectar placas de matrícula em imagens de alta resolução
- **RF2.3**: O sistema deve extrair crops das placas detectadas
- **RF2.4**: O sistema deve executar OCR para reconhecimento de texto da matrícula
- **RF2.5**: O sistema deve validar formato de matrícula portuguesa (XX-XX-XX ou XX-XX-XXX)
- **RF2.6**: O sistema deve armazenar crops em object storage (MinIO)

### **RF3 - Detecção de Placas de Perigo**
- **RF3.1**: O sistema deve detectar placas de materiais perigosos (UN numbers)
- **RF3.2**: O sistema deve reconhecer números UN via OCR especializado
- **RF3.3**: O sistema deve extrair classe de perigo (ex: classe 3 - líquidos inflamáveis)
- **RF3.4**: O sistema deve armazenar crops de placards em object storage

### **RF4 - Decisão de Acesso**
- **RF4.1**: O sistema deve validar matrícula contra whitelist/blacklist em base de dados
- **RF4.2**: O sistema deve validar UN number contra lista de materiais restritos
- **RF4.3**: O sistema deve verificar regras temporais (horários permitidos, dias da semana)
- **RF4.4**: O sistema deve verificar validade de autorizações (expires_at)
- **RF4.5**: O sistema deve gerar decisão: APPROVE, DENY ou MANUAL_REVIEW
- **RF4.6**: O sistema deve incluir razão detalhada na decisão (ex: "unauthorized_plate")
- **RF4.7**: O sistema deve publicar decisão em tópico Kafka

### **RF5 - Persistência de Dados**
- **RF5.1**: O sistema deve persistir todas as decisões em base de dados relacional
- **RF5.2**: O sistema deve manter audit log de todas as ações
- **RF5.3**: O sistema deve armazenar referências (URLs) das imagens em MinIO
- **RF5.4**: O sistema deve manter histórico de detecções para auditoria

### **RF6 - API REST**
- **RF6.1**: O sistema deve expor endpoint para consultar evento por ID
- **RF6.2**: O sistema deve expor endpoint para listar decisões por portão e período
- **RF6.3**: O sistema deve expor endpoint para histórico de matrícula
- **RF6.4**: O sistema deve expor endpoint para revisão manual de decisões
- **RF6.5**: O sistema deve gerar presigned URLs do MinIO com expiração configurável

### **RF7 - Notificações em Tempo Real**
- **RF7.1**: O sistema deve notificar operadores via WebSocket quando houver nova decisão
- **RF7.2**: O sistema deve permitir conexão WebSocket autenticada por portão
- **RF7.3**: O sistema deve enviar payload completo da decisão (Imagens)

### **RF8 - Streaming de Vídeo**
- **RF8.1**: O sistema deve receber streams RTSP de câmaras IP
- **RF8.2**: O sistema deve redistribuir streams via Nginx RTMP para múltiplos consumidores
- **RF8.3**: O sistema deve suportar dual-stream (720p always-on + 4K on-demand)
- **RF8.4**: O sistema deve converter RTSP para HLS/DASH para visualização web

### **RF9 - Autenticação e Autorização**
- **RF9.1**: O sistema deve autenticar utilizadores via JWT (JSON Web Tokens)
- **RF9.2**: O sistema deve implementar RBAC (Role-Based Access Control)
- **RF9.3**: O sistema deve suportar roles: operador, supervisor, admin
- **RF9.4**: O sistema deve validar permissões por portão (user_permissions table)
- **RF9.5**: O sistema deve permitir apenas supervisores fazer manual review
- **RF9.6**: O sistema deve registrar todos os acessos em audit log

### **RF10 - Gestão de Veículos e Regras**
- **RF10.1**: O sistema deve permitir cadastrar veículos autorizados
- **RF10.2**: O sistema deve permitir cadastrar materiais perigosos restritos
- **RF10.3**: O sistema deve permitir configurar regras temporais de acesso
- **RF10.4**: O sistema deve permitir definir validade de autorizações



## Para apresentação
- **RF1.4**: O sistema deve aplicar threshold mínimo de confiança (ex: 0.75) antes de publicar evento
- **RF4.5**: O sistema deve gerar decisão: APPROVE, DENY ou MANUAL_REVIEW
- **RF5.3**: O sistema deve armazenar referências (URLs) das imagens em MinIO
- **RF9.3**: O sistema deve suportar roles: operador, supervisor, admin





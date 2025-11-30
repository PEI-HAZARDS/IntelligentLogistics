Endpoints do Data_Module

## Visão Geral
O `data_module` expõe APIs REST para interação com PostgreSQL (dados oficiais), MongoDB (eventos/notificações) e Redis (cache). Endpoints internos suportam o Decision Engine; externos, o frontend.

- **Base URL**: `http://data-module:8000/api/v1`
- **Autenticação**: Futura (JWT).
- **Formato**: JSON.

## 1. Endpoints Internos (Decision Engine ↔ Data_Module)
Usados pelo Decision Engine para consultar/atualizar PostgreSQL (decisões, chegadas). Focam em persistência e validação.

### Chegadas (PostgreSQL)
- **GET /arrivals**  
  Consulta chegadas (para matching de matrículas).  
  *Query Params*: `matricula` (filtro).  
  *Response*: Lista de chegadas.  
  *Uso*: DE compara matrícula detetada.

- **PUT /arrivals/{id}**  
  Atualiza chegada (e.g., estado_entrega).  
  *Body*: `{"estado_entrega": "concluida"}`.  
  *Response*: Chegada atualizada.  
  *Uso*: DE persiste decisão.

### Eventos (MongoDB - Interno)
- **POST /events**  
  Insere evento de decisão.  
  *Body*: `{"type": "autorizado", "data": {"id_chegada": 123}}`.  
  *Response*: Sucesso.  
  *Uso*: DE armazena eventos pós-decisão.

## 2. Endpoints Externos (Frontend ↔ Data_Module)
Usados pelo frontend para consultas em tempo real. PostgreSQL para listas/detalhes; MongoDB para notificações instantâneas.

### Chegadas (PostgreSQL - Externas)
- **GET /arrivals**  
  Lista chegadas para display.  
  *Query Params*: `page`, `limit`, `estado`.  
  *Response*: Lista paginada.  
  *Uso*: Frontend mostra tabela de chegadas.

- **GET /arrivals/{id}**  
  Detalhes de uma chegada.  
  *Response*: Objeto chegada.  
  *Uso*: Frontend mostra modal de detalhes.

### Eventos/Notificações (MongoDB - Externas)
- **GET /events**  
  Lista eventos recentes (para notificações).  
  *Query Params*: `type` (e.g., "autorizado"), `limit`.  
  *Response*: Lista de eventos.  
  *Uso*: Frontend busca notificações ("Camião autorizado").

- **GET /detections**  
  Lista detecções não processadas.  
  *Response*: Lista.  
  *Uso*: Frontend para debug ou display.

### Deteções (MongoDB - Externas/Internas)
- **POST /detections**  
  Recebe deteção de agentes.  
  *Body*: Detecção JSON.  
  *Response*: Processado.  
  *Uso*: Agentes enviam; DE consulta via interno.

## 3. Futuros Endpoints
### Agregados (Gestor Logístico)
- **GET /dashboard/summary**  
  Dados agregados (e.g., chegadas por dia).  
  *Uso*: Relatórios para gestor.

### Admin
- **POST /admin/reset**  
  Reset dados (admin only).  
  *Uso*: Manutenção.

---

**Notas**:
- Prioriza internos primeiro (para integração com DE).
- Testa com Postman/Swagger.
- Adiciona paginação/filtros conforme cresce.
openapi: 3.0.3
info:
  title: Intelligent Logistics - Data Module API
  version: 1.0.0
  description: |
    API para gestão de chegadas, motoristas e decisões.
    Source of Truth para o Porto de Aveiro.
    
    **Consumidores:**
    - Frontend Operador (Web) - Dashboard, controle manual
    - App Mobile Motorista - Login, reclamação de cargas
    - Decision Engine (Microserviço) - Queries, decisões
    - Agents (A/B/C) - Registar detecções

servers:
  - url: /api/v1
    description: Production

tags:
  - name: Arrivals
    description: Gestão de chegadas diárias (PostgreSQL)
  - name: Drivers
    description: Autenticação mobile e gestão de motoristas
  - name: Decisions
    description: Processamento de decisões do Decision Engine
  - name: Alerts
    description: Alertas e ocorrências (ADR, delays, etc.)
  - name: Workers
    description: Gestão de operadores e gestores (backoffice)
  - name: Events
    description: Histórico de eventos (MongoDB)

paths:

  ######################################
  # ARRIVALS
  ######################################
  /arrivals:
    get:
      tags:
        - Arrivals
      summary: Lista chegadas com filtros
      description: Obtém lista de chegadas com filtros opcionais. Usado pelo operador.
      parameters:
        - name: skip
          in: query
          schema:
            type: integer
            default: 0
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            maximum: 500
        - name: id_gate
          in: query
          description: Filtra por gate de entrada
          schema:
            type: integer
        - name: id_turno
          in: query
          description: Filtra por turno
          schema:
            type: integer
        - name: estado_entrega
          in: query
          description: Estado da entrega
          schema:
            type: string
            enum: [in_transit, delayed, unloading, completed]
        - name: data_prevista
          in: query
          description: Data prevista (YYYY-MM-DD)
          schema:
            type: string
            format: date
      responses:
        "200":
          description: Lista de chegadas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Chegada"

  /arrivals/stats:
    get:
      tags:
        - Arrivals
      summary: Estatísticas de chegadas
      description: Conta chegadas agrupadas por estado (últimas 24h)
      parameters:
        - name: id_gate
          in: query
          schema:
            type: integer
        - name: data
          in: query
          schema:
            type: string
            format: date
      responses:
        "200":
          description: Estatísticas
          content:
            application/json:
              schema:
                type: object
                properties:
                  in_transit:
                    type: integer
                  delayed:
                    type: integer
                  unloading:
                    type: integer
                  completed:
                    type: integer
                  total:
                    type: integer

  /arrivals/next/{id_gate}:
    get:
      tags:
        - Arrivals
      summary: Próximas chegadas
      description: Próximas chegadas previstas para um gate (painel lateral operador)
      parameters:
        - name: id_gate
          in: path
          required: true
          schema:
            type: integer
        - name: limit
          in: query
          schema:
            type: integer
            default: 5
            maximum: 20
      responses:
        "200":
          description: Próximas chegadas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Chegada"

  /arrivals/{id_chegada}:
    get:
      tags:
        - Arrivals
      summary: Obter chegada por ID
      parameters:
        - name: id_chegada
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Detalhes da chegada
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Chegada"
        "404":
          description: Chegada não encontrada

  /arrivals/pin/{pin_acesso}:
    get:
      tags:
        - Arrivals
      summary: Obter chegada por PIN
      description: Consulta chegada pelo PIN de acesso (app motorista)
      parameters:
        - name: pin_acesso
          in: path
          required: true
          schema:
            type: string
            example: "PRT-0001"
      responses:
        "200":
          description: Chegada encontrada
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Chegada"
        "404":
          description: PIN inválido ou chegada não encontrada

  /arrivals/query/matricula/{matricula}:
    get:
      tags:
        - Arrivals
      summary: Consultar chegadas por matrícula
      description: Usado pelo Decision Engine para encontrar chegadas candidatas
      parameters:
        - name: matricula
          in: path
          required: true
          schema:
            type: string
            example: "XX-XX-XX"
        - name: id_turno
          in: query
          schema:
            type: integer
        - name: estado_entrega
          in: query
          schema:
            type: string
        - name: data_prevista
          in: query
          schema:
            type: string
            format: date
      responses:
        "200":
          description: Chegadas encontradas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Chegada"

  /arrivals/decision/candidates/{id_gate}/{matricula}:
    get:
      tags:
        - Arrivals
      summary: Obter candidatas para decisão
      description: Retorna chegadas enriquecidas (carga ADR, cais, etc.) para Decision Engine
      parameters:
        - name: id_gate
          in: path
          required: true
          schema:
            type: integer
        - name: matricula
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Candidatas enriquecidas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/DecisionCandidate"

  /arrivals/{id_chegada}/status:
    patch:
      tags:
        - Arrivals
      summary: Atualizar estado de chegada
      description: Atualiza manualmente o estado (operador ou sistema)
      parameters:
        - name: id_chegada
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/ArrivalStatusUpdate"
      responses:
        "200":
          description: Chegada atualizada
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Chegada"
        "404":
          description: Chegada não encontrada

  /arrivals/{id_chegada}/decision:
    post:
      tags:
        - Arrivals
      summary: Processar decisão do Decision Engine
      description: Atualiza chegada e cria alertas conforme decisão
      parameters:
        - name: id_chegada
          in: path
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/ArrivalDecisionUpdate"
      responses:
        "200":
          description: Decisão processada
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Chegada"
        "404":
          description: Chegada não encontrada

  ######################################
  # DRIVERS
  ######################################
  /drivers/login:
    post:
      tags:
        - Drivers
      summary: Login do motorista (app mobile)
      description: Autentica motorista e retorna token
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/DriverLoginRequest"
      responses:
        "200":
          description: Login bem-sucedido
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/DriverLoginResponse"
        "401":
          description: Credenciais inválidas ou conta desativada

  /drivers/claim:
    post:
      tags:
        - Drivers
      summary: Reclamar chegada com PIN
      description: Motorista usa PIN para associar-se a uma chegada
      parameters:
        - name: num_carta_cond
          in: query
          required: true
          description: Número da carta de condução (do JWT)
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/ClaimChegadaRequest"
      responses:
        "200":
          description: Chegada reclamada com sucesso
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ClaimChegadaResponse"
        "404":
          description: PIN inválido ou chegada não disponível

  /drivers/me/active:
    get:
      tags:
        - Drivers
      summary: Obter chegada ativa do motorista
      parameters:
        - name: num_carta_cond
          in: query
          required: true
          description: Número da carta (do JWT)
          schema:
            type: string
      responses:
        "200":
          description: Chegada ativa ou null
          content:
            application/json:
              schema:
                oneOf:
                  - $ref: "#/components/schemas/Chegada"
                  - type: "null"

  /drivers/me/today:
    get:
      tags:
        - Drivers
      summary: Entregas de hoje do motorista
      parameters:
        - name: num_carta_cond
          in: query
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Lista de entregas de hoje
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Chegada"

  /drivers:
    get:
      tags:
        - Drivers
      summary: Listar motoristas (backoffice)
      parameters:
        - name: skip
          in: query
          schema:
            type: integer
            default: 0
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            maximum: 500
        - name: only_active
          in: query
          schema:
            type: boolean
            default: true
      responses:
        "200":
          description: Lista de motoristas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Condutor"

  /drivers/{num_carta_cond}:
    get:
      tags:
        - Drivers
      summary: Obter dados de um motorista
      parameters:
        - name: num_carta_cond
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Dados do motorista
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Condutor"
        "404":
          description: Motorista não encontrado

  /drivers/{num_carta_cond}/arrivals:
    get:
      tags:
        - Drivers
      summary: Histórico de chegadas de um motorista
      parameters:
        - name: num_carta_cond
          in: path
          required: true
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 50
            maximum: 200
      responses:
        "200":
          description: Histórico de chegadas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Chegada"

  ######################################
  # DECISIONS
  ######################################
  /decisions/process:
    post:
      tags:
        - Decisions
      summary: Processar decisão do Decision Engine
      description: |
        Endpoint principal do Decision Engine.
        - Verifica duplicado (Redis)
        - Atualiza PostgreSQL
        - Cria alertas
        - Persiste em MongoDB
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/DecisionIncomingRequest"
      responses:
        "200":
          description: Decisão processada
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: "processed"
                  decision:
                    type: string
                  id_chegada:
                    type: integer
                  event_id:
                    type: string

  /decisions/query-arrivals:
    post:
      tags:
        - Decisions
      summary: Consultar chegadas candidatas
      description: Decision Engine consulta chegadas após deteção de matrícula
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/QueryArrivalsRequest"
      responses:
        "200":
          description: Resultado da consulta
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/DecisionResponse"

  /decisions/detection-event:
    post:
      tags:
        - Decisions
      summary: Registar evento de deteção
      description: Agents (A/B/C) registam detecções (placa, hazmat, camião)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/DetectionEventRequest"
      responses:
        "200":
          description: Evento registado
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: "ok"
                  event_id:
                    type: string

  /decisions/events/detections:
    get:
      tags:
        - Decisions
      summary: Histórico de detecções
      parameters:
        - name: matricula
          in: query
          schema:
            type: string
        - name: gate_id
          in: query
          schema:
            type: integer
        - name: event_type
          in: query
          schema:
            type: string
            enum: [license_plate_detection, hazmat_detection, truck_detection]
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            maximum: 500
      responses:
        "200":
          description: Eventos de deteção
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object

  /decisions/events/decisions:
    get:
      tags:
        - Decisions
      summary: Histórico de decisões
      parameters:
        - name: matricula
          in: query
          schema:
            type: string
        - name: gate_id
          in: query
          schema:
            type: integer
        - name: decision
          in: query
          schema:
            type: string
            enum: [approved, rejected, manual_review, not_found]
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            maximum: 500
      responses:
        "200":
          description: Eventos de decisão
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object

  /decisions/events/{event_id}:
    get:
      tags:
        - Decisions
      summary: Obter evento por ID
      parameters:
        - name: event_id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Evento encontrado
          content:
            application/json:
              schema:
                type: object
        "404":
          description: Evento não encontrado

  /decisions/manual-review/{id_chegada}:
    post:
      tags:
        - Decisions
      summary: Revisão manual pelo operador
      parameters:
        - name: id_chegada
          in: path
          required: true
          schema:
            type: integer
        - name: decision
          in: query
          required: true
          schema:
            type: string
            enum: [approved, rejected]
        - name: observacoes
          in: query
          schema:
            type: string
      responses:
        "200":
          description: Revisão processada

  ######################################
  # ALERTS
  ######################################
  /alerts/active:
    get:
      tags:
        - Alerts
      summary: Alertas ativos (últimas 24h)
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 50
            maximum: 200
      responses:
        "200":
          description: Alertas ativos ordenados por severidade
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Alerta"

  /alerts/stats:
    get:
      tags:
        - Alerts
      summary: Estatísticas de alertas
      responses:
        "200":
          description: Contagem por tipo
          content:
            application/json:
              schema:
                type: object
                additionalProperties:
                  type: integer

  /alerts/reference/adr-codes:
    get:
      tags:
        - Alerts
      summary: Códigos ADR/UN de referência
      responses:
        "200":
          description: Dicionário de códigos UN
          content:
            application/json:
              schema:
                type: object
                example:
                  "1203":
                    descricao: "Gasolina"
                    classe: "3"
                    perigo: "Líquido inflamável"

  /alerts/reference/kemler-codes:
    get:
      tags:
        - Alerts
      summary: Códigos Kemler de referência
      responses:
        "200":
          description: Dicionário de códigos Kemler
          content:
            application/json:
              schema:
                type: object
                example:
                  "33": "Líquido muito inflamável"
                  "80": "Corrosivo"

  /alerts/{id_alerta}:
    get:
      tags:
        - Alerts
      summary: Obter alerta por ID
      parameters:
        - name: id_alerta
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Detalhes do alerta
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Alerta"
        "404":
          description: Alerta não encontrado

  /alerts:
    get:
      tags:
        - Alerts
      summary: Listar alertas
      parameters:
        - name: skip
          in: query
          schema:
            type: integer
            default: 0
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            maximum: 500
        - name: tipo
          in: query
          schema:
            type: string
            example: "ADR"
        - name: severidade_min
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 5
        - name: id_carga
          in: query
          schema:
            type: integer
      responses:
        "200":
          description: Lista de alertas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Alerta"
    post:
      tags:
        - Alerts
      summary: Criar alerta manualmente
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateAlertRequest"
      responses:
        "201":
          description: Alerta criado
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Alerta"

  /alerts/adr:
    post:
      tags:
        - Alerts
      summary: Criar alerta ADR/hazmat
      description: Cria alerta específico com códigos UN/Kemler
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateADRAlertRequest"
      responses:
        "201":
          description: Alerta ADR criado
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Alerta"
        "404":
          description: Chegada não encontrada

  /alerts/historico/{id_historico}:
    get:
      tags:
        - Alerts
      summary: Alertas de um histórico de ocorrência
      parameters:
        - name: id_historico
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Lista de alertas
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/Alerta"

  ######################################
  # WORKERS
  ######################################
  /workers/login:
    post:
      tags:
        - Workers
      summary: Login de operador/gestor
      description: Autentica trabalhador (operador ou gestor)
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/WorkerLoginRequest"
      responses:
        "200":
          description: Login bem-sucedido
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/WorkerLoginResponse"
        "401":
          description: Credenciais inválidas

  /workers:
    get:
      tags:
        - Workers
      summary: Listar trabalhadores
      parameters:
        - name: skip
          in: query
          schema:
            type: integer
            default: 0
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
            maximum: 500
        - name: only_active
          in: query
          schema:
            type: boolean
            default: true
      responses:
        "200":
          description: Lista de trabalhadores
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/WorkerInfo"

    post:
      tags:
        - Workers
      summary: Criar novo trabalhador
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateWorkerRequest"
      responses:
        "201":
          description: Trabalhador criado
          content:
            application/json:
              schema:
                type: object
        "400":
          description: Email já em uso

  /workers/{num_trabalhador}:
    get:
      tags:
        - Workers
      summary: Obter dados de um trabalhador
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Dados do trabalhador
          content:
            application/json:
              schema:
                type: object
        "404":
          description: Trabalhador não encontrado

    delete:
      tags:
        - Workers
      summary: Desativar trabalhador
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Trabalhador desativado
        "404":
          description: Trabalhador não encontrado

  /workers/{num_trabalhador}/promote:
    post:
      tags:
        - Workers
      summary: Promover operador a gestor
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
        - name: nivel_acesso
          in: query
          schema:
            type: string
            enum: [basic, admin]
            default: basic
      responses:
        "200":
          description: Operador promovido
        "400":
          description: Não é operador ou não encontrado

  /workers/operators:
    get:
      tags:
        - Workers
      summary: Listar operadores
      parameters:
        - name: skip
          in: query
          schema:
            type: integer
            default: 0
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
      responses:
        "200":
          description: Lista de operadores
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/WorkerInfo"

  /workers/operators/me:
    get:
      tags:
        - Workers
      summary: Meus dados (operador)
      parameters:
        - name: num_trabalhador
          in: query
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Dados do operador
          content:
            application/json:
              schema:
                type: object

  /workers/operators/{num_trabalhador}:
    get:
      tags:
        - Workers
      summary: Obter dados de operador
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Dados do operador
          content:
            application/json:
              schema:
                type: object

  /workers/operators/{num_trabalhador}/current-shift/{id_gate}:
    get:
      tags:
        - Workers
      summary: Turno atual do operador
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
        - name: id_gate
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Turno atual ou null
          content:
            application/json:
              schema:
                type: object
                nullable: true

  /workers/operators/{num_trabalhador}/shifts:
    get:
      tags:
        - Workers
      summary: Turnos de um operador
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
        - name: id_gate
          in: query
          schema:
            type: integer
        - name: limit
          in: query
          schema:
            type: integer
            default: 50
      responses:
        "200":
          description: Lista de turnos
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object

  /workers/operators/{num_trabalhador}/dashboard/{id_gate}:
    get:
      tags:
        - Workers
      summary: Dashboard do operador
      description: Próximas chegadas, alertas, estatísticas para um gate
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
        - name: id_gate
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Dashboard do operador
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OperatorDashboard"

  /workers/managers:
    get:
      tags:
        - Workers
      summary: Listar gestores
      parameters:
        - name: skip
          in: query
          schema:
            type: integer
            default: 0
        - name: limit
          in: query
          schema:
            type: integer
            default: 100
      responses:
        "200":
          description: Lista de gestores
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: "#/components/schemas/WorkerInfo"

  /workers/managers/me:
    get:
      tags:
        - Workers
      summary: Meus dados (gestor)
      parameters:
        - name: num_trabalhador
          in: query
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Dados do gestor
          content:
            application/json:
              schema:
                type: object

  /workers/managers/{num_trabalhador}:
    get:
      tags:
        - Workers
      summary: Obter dados de gestor
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Dados do gestor
          content:
            application/json:
              schema:
                type: object

  /workers/managers/{num_trabalhador}/shifts:
    get:
      tags:
        - Workers
      summary: Turnos supervisionados
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
        - name: limit
          in: query
          schema:
            type: integer
            default: 50
      responses:
        "200":
          description: Lista de turnos
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object

  /workers/managers/{num_trabalhador}/overview:
    get:
      tags:
        - Workers
      summary: Visão geral do gestor
      description: Gates, turnos, alertas, performance
      parameters:
        - name: num_trabalhador
          in: path
          required: true
          schema:
            type: integer
      responses:
        "200":
          description: Visão geral
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ManagerOverview"

  /workers/password:
    post:
      tags:
        - Workers
      summary: Alterar password
      parameters:
        - name: num_trabalhador
          in: query
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/UpdatePasswordRequest"
      responses:
        "200":
          description: Password alterada
        "401":
          description: Password atual incorreta

  /workers/email:
    post:
      tags:
        - Workers
      summary: Alterar email
      parameters:
        - name: num_trabalhador
          in: query
          required: true
          schema:
            type: integer
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/UpdateEmailRequest"
      responses:
        "200":
          description: Email alterado
        "400":
          description: Email já em uso

components:
  schemas:

    ######################################
    # Chegada (Arrival)
    ######################################
    Chegada:
      type: object
      properties:
        id_chegada:
          type: integer
        id_gate_entrada:
          type: integer
        id_gate_saida:
          type: integer
          nullable: true
        id_cais:
          type: integer
        id_turno:
          type: integer
        matricula_pesado:
          type: string
        id_carga:
          type: integer
        data_prevista:
          type: string
          format: date
        hora_prevista:
          type: string
          format: time
        data_hora_chegada:
          type: string
          format: date-time
          nullable: true
        observacoes:
          type: string
          nullable: true
        pin_acesso:
          type: string
          example: "PRT-0001"
        estado_entrega:
          type: string
          enum: [in_transit, delayed, unloading, completed]
        carga:
          $ref: "#/components/schemas/Carga"
        cais:
          $ref: "#/components/schemas/Cais"

    ######################################
    # Decision Candidate
    ######################################
    DecisionCandidate:
      type: object
      properties:
        id_chegada:
          type: integer
        matricula_pesado:
          type: string
        id_gate_entrada:
          type: integer
        id_cais:
          type: integer
        id_turno:
          type: integer
        hora_prevista:
          type: string
          format: time
        estado_entrega:
          type: string
        carga:
          type: object
          properties:
            id_carga:
              type: integer
            descricao:
              type: string
            adr:
              type: boolean
            tipo_carga:
              type: string
        cais:
          type: object
          properties:
            id_cais:
              type: integer
            localizacao_gps:
              type: string

    ######################################
    # ArrivalStatusUpdate
    ######################################
    ArrivalStatusUpdate:
      type: object
      properties:
        estado_entrega:
          type: string
          enum: [in_transit, delayed, unloading, completed]
        data_hora_chegada:
          type: string
          format: date-time
          nullable: true
        id_gate_saida:
          type: integer
          nullable: true
        observacoes:
          type: string
          nullable: true

    ######################################
    # ArrivalDecisionUpdate
    ######################################
    ArrivalDecisionUpdate:
      type: object
      properties:
        decision:
          type: string
          enum: [approved, rejected, manual_review]
        estado_entrega:
          type: string
        data_hora_chegada:
          type: string
          format: date-time
          nullable: true
        observacoes:
          type: string
          nullable: true
        alertas:
          type: array
          items:
            $ref: "#/components/schemas/AlertPayload"
      required:
        - decision
        - estado_entrega

    ######################################
    # Alert Payloads
    ######################################
    AlertPayload:
      type: object
      properties:
        tipo:
          type: string
          example: "ADR"
        severidade:
          type: integer
          minimum: 1
          maximum: 5
        descricao:
          type: string

    CreateAlertRequest:
      type: object
      properties:
        id_historico_ocorrencia:
          type: integer
        id_carga:
          type: integer
        tipo:
          type: string
        severidade:
          type: integer
          minimum: 1
          maximum: 5
        descricao:
          type: string
      required:
        - id_historico_ocorrencia
        - id_carga
        - tipo
        - severidade
        - descricao

    CreateADRAlertRequest:
      type: object
      properties:
        id_chegada:
          type: integer
        un_code:
          type: string
          example: "1203"
        kemler_code:
          type: string
          example: "33"
        detected_hazmat:
          type: string
      required:
        - id_chegada

    Alerta:
      type: object
      properties:
        id_alerta:
          type: integer
        id_historico_ocorrencia:
          type: integer
        id_carga:
          type: integer
        tipo:
          type: string
        severidade:
          type: integer
          minimum: 1
          maximum: 5
        descricao:
          type: string
        data_hora:
          type: string
          format: date-time

    ######################################
    # Driver Auth
    ######################################
    DriverLoginRequest:
      type: object
      properties:
        num_carta_cond:
          type: string
        password:
          type: string
      required:
        - num_carta_cond
        - password

    DriverLoginResponse:
      type: object
      properties:
        token:
          type: string
        num_carta_cond:
          type: string
        nome:
          type: string
        id_empresa:
          type: integer
        empresa_nome:
          type: string

    ClaimChegadaRequest:
      type: object
      properties:
        pin_acesso:
          type: string
          example: "PRT-0001"
      required:
        - pin_acesso

    ClaimChegadaResponse:
      type: object
      properties:
        id_chegada:
          type: integer
        id_cais:
          type: integer
        cais_localizacao:
          type: string
        matricula_veiculo:
          type: string
        carga_descricao:
          type: string
        carga_adr:
          type: boolean
        navegacao_url:
          type: string
          nullable: true

    ######################################
    # Decision Engine
    ######################################
    DecisionIncomingRequest:
      type: object
      properties:
        matricula:
          type: string
        gate_id:
          type: integer
        id_chegada:
          type: integer
        decision:
          type: string
          enum: [approved, rejected, manual_review]
        estado_entrega:
          type: string
        observacoes:
          type: string
          nullable: true
        alertas:
          type: array
          items:
            $ref: "#/components/schemas/AlertPayload"
          nullable: true
        extra_data:
          type: object
          nullable: true
      required:
        - matricula
        - gate_id
        - id_chegada
        - decision
        - estado_entrega

    QueryArrivalsRequest:
      type: object
      properties:
        matricula:
          type: string
        gate_id:
          type: integer
      required:
        - matricula
        - gate_id

    DecisionResponse:
      type: object
      properties:
        found:
          type: boolean
        candidates:
          type: array
          items:
            $ref: "#/components/schemas/DecisionCandidate"
        message:
          type: string

    DetectionEventRequest:
      type: object
      properties:
        type:
          type: string
          enum: [license_plate_detection, hazmat_detection, truck_detection]
        matricula:
          type: string
          nullable: true
        gate_id:
          type: integer
        confidence:
          type: number
          nullable: true
        agent:
          type: string
          example: "AgentB"
        raw_data:
          type: object
          nullable: true
      required:
        - type
        - gate_id
        - agent

    ######################################
    # Data Models
    ######################################
    Condutor:
      type: object
      properties:
        num_carta_cond:
          type: string
        nome:
          type: string
        contacto:
          type: string
          nullable: true
        id_empresa:
          type: integer
          nullable: true
        ativo:
          type: boolean

    Carga:
      type: object
      properties:
        id_carga:
          type: integer
        peso:
          type: number
        descricao:
          type: string
          nullable: true
        adr:
          type: boolean
        tipo_carga:
          type: string
        estado_fisico:
          type: string


    Cais:
      type: object
      properties:
        id_cais:
          type: integer
        estado:
          type: string
          enum: [manutencao, operacional, fechado]
        capacidade_max:
          type: integer
          nullable: true
        localizacao_gps:
          type: string
          nullable: true

    ######################################
    # Workers
    ######################################
    WorkerLoginRequest:
      type: object
      properties:
        email:
          type: string
        password:
          type: string
      required:
        - email
        - password

    WorkerLoginResponse:
      type: object
      properties:
        token:
          type: string
        num_trabalhador:
          type: integer
        nome:
          type: string
        email:
          type: string
        role:
          type: string
          enum: [operador, gestor]
        ativo:
          type: boolean

    WorkerInfo:
      type: object
      properties:
        num_trabalhador:
          type: integer
        nome:
          type: string
        email:
          type: string
        role:
          type: string
          enum: [operador, gestor]
        ativo:
          type: boolean

    CreateWorkerRequest:
      type: object
      properties:
        nome:
          type: string
        email:
          type: string
        password:
          type: string
        role:
          type: string
          enum: [operador, gestor]
        nivel_acesso:
          type: string
          enum: [basic, admin]
          nullable: true
      required:
        - nome
        - email
        - password
        - role

    UpdatePasswordRequest:
      type: object
      properties:
        current_password:
          type: string
        new_password:
          type: string
      required:
        - current_password
        - new_password

    UpdateEmailRequest:
      type: object
      properties:
        new_email:
          type: string
      required:
        - new_email

    OperatorDashboard:
      type: object
      properties:
        operador:
          type: integer
        gate:
          type: integer
        data:
          type: string
          format: date
        proximas_chegadas:
          type: array
          items:
            type: object
            properties:
              id_chegada:
                type: integer
              matricula:
                type: string
              hora_prevista:
                type: string
              cais:
                type: integer
              carga_adr:
                type: boolean
              estado:
                type: string
        stats:
          type: object
          properties:
            in_transit:
              type: integer
            delayed:
              type: integer
            unloading:
              type: integer
            completed:
              type: integer

    ManagerOverview:
      type: object
      properties:
        gestor:
          type: integer
        data:
          type: string
          format: date
        gates_ativos:
          type: integer
        turnos_hoje:
          type: integer
        alertas_recentes:
          type: integer
        estatisticas:
          type: object
          additionalProperties:
            type: integer


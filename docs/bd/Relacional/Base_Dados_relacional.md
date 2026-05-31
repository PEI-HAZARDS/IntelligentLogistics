# Modelo Base de Dados — Intelligent Logistics (Base de Dados Relacional)

## Objetivo
Representar a base de dados relacional **PostgreSQL** do Data Module — a **fonte de verdade**
(ACID) do sistema do Porto Inteligente. Gere infraestrutura portuária, empresas/condutores/camiões,
staff e turnos, marcações (appointments), execução (visits), alertas e os mecanismos de
consistência event-driven (Inbox/Outbox). Complementa-se com **MongoDB** (event log + read models
CQRS) e **Redis** (cache + contadores + dedup) — ver `docs/bd/Nao_Relacional/`.

> **Fonte de verdade deste documento:** `src/V_APP/Data_Module/infrastructure/persistence/sql_models.py`
> e `inbox_outbox_models.py`, mais as migrações `scripts/migrationDBv3..v5.sql` e `triggers.sql`.
> Referência coluna-a-coluna completa: `code_documentation/V_APP/Data_Module/SCHEMA_REFERENCE.md`.

---

## Normalização
Modelo estruturado até à **3ª Forma Normal (3FN)**:

| Forma Normal | Condição Cumprida |
|---|---|
| **1FN** | Todos os atributos são atómicos |
| **2FN** | Atributos dependem da chave primária completa (incl. PKs compostas) |
| **3FN** | Sem dependências transitivas entre atributos não-chave |
| **Relações M:N** | Resolvidas com tabelas associativas (`driver_vehicle`) |
| **Herança (Manager/Operator)** | Especialização disjunta via FK para `worker` |

---

## Tipos enumerados (PG ENUM)

| Enum | Valores | Usado em |
|---|---|---|
| `appointment_status` | `scheduled`, `in_transit`, `in_process`, `completed`, `canceled` | `appointment.status` (fluxo **armazenado**) |
| `delivery_status` | `in_port`, `unloading`, `done` | `visit.state` |
| `physical_state` | `liquid`, `solid`, `gaseous`, `hybrid` | `cargo.state` |
| `direction` | `inbound`, `outbound` | `booking.direction` |
| `operational_status` | `maintenance`, `operational`, `closed` | `dock.current_usage` |
| `access_level` | `admin`, `basic` | `manager.access_level` |
| `type_alert` | `generic`, `safety`, `problem`, `operational` | `alert.type` |
| `ShiftType` | `MORNING`, `AFTERNOON`, `NIGHT` | `shift.shift_type`, `visit.shift_type` |
| `pending_review_status` | `PENDING`, `APPROVED`, `REJECTED` | `pending_reviews.status` |

> **Sub-estados computados (nunca armazenados):** `delayed`, `unloading`, `in_port`, `leaving_port`
> são derivados em tempo de leitura a partir de `appointment.status` + `visit.state` + tempo
> (`computed_status` no ORM). Só os 5 valores de `appointment_status` são persistidos (refactor v4).

---

## Entidades

### Infraestrutura

#### `terminal`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `name` | VARCHAR(200) | | Nome do terminal |
| `latitude` / `longitude` | DECIMAL(10,8)/(11,8) | | Coordenadas |
| `hazmat_approved` | BOOLEAN | | Aprovado para mercadoria perigosa |

#### `dock`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `terminal_id` | INTEGER | **PK**, FK → `terminal.id` | PK composta |
| `bay_number` | VARCHAR(50) | **PK** | PK composta |
| `latitude` / `longitude` | DECIMAL | | Coordenadas |
| `current_usage` | `operational_status` | | Estado operacional |
| `estado` | VARCHAR(10) | CHECK {Ativo,Inativo} | BR-13 |

#### `gate`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `label` | VARCHAR(100) | NOT NULL | Designação |
| `latitude` / `longitude` | DECIMAL | | Coordenadas |
| `estado` | VARCHAR(10) | CHECK {Ativo,Inativo} | BR-14 |

### Entidades externas

#### `company`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `nif` | VARCHAR(20) | PK | NIF (identificador) |
| `name` | VARCHAR(200) | NOT NULL | Nome |
| `contact` | VARCHAR(50) | | Telefone/email |

#### `driver`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `drivers_license` | VARCHAR(50) | PK | Nº carta de condução |
| `company_nif` | VARCHAR(20) | FK → `company.nif` | Empregador |
| `name` | VARCHAR(100) | NOT NULL | Nome |
| `password_hash` | TEXT | | bcrypt |
| `mobile_device_token` | TEXT (encriptado) | | **RGPD** — AES-256-GCM em repouso (push) |
| `active` | BOOLEAN | DEFAULT TRUE | Soft-delete |
| `current_appointment_id` | INTEGER | | Entrega ativa (acesso sequencial) |
| `created_at` | TIMESTAMP | DEFAULT now() | |

#### `truck`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `license_plate` | VARCHAR(20) | PK | Matrícula (AA-00-BB) |
| `company_nif` | VARCHAR(20) | FK → `company.nif` | Proprietário |
| `brand` | VARCHAR(100) | | Marca |

### Staff e turnos

#### `worker` (superclasse)
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `num_worker` | VARCHAR(20) | PK | Identificador |
| `name` | VARCHAR(200) | NOT NULL | Nome |
| `phone` | TEXT (encriptado) | | **RGPD** — AES-256-GCM (nonce aleatório, não pesquisável) |
| `email` | TEXT (encriptado) | UNIQUE | **RGPD** — AES-256-GCM (nonce determinístico, pesquisável; chave de login) |
| `password_hash` | TEXT | | bcrypt |
| `active` | BOOLEAN | DEFAULT TRUE | |
| `created_at` | TIMESTAMP | DEFAULT now() | |

#### `manager` / `operator` (especialização disjunta de `worker`)
| Tabela | Coluna | Tipo | PK/FK |
|---|---|---|---|
| `manager` | `num_worker` | VARCHAR(20) | PK, FK → `worker.num_worker` |
| `manager` | `access_level` | `access_level` | DEFAULT 'basic' |
| `operator` | `num_worker` | VARCHAR(20) | PK, FK → `worker.num_worker` |

#### `shift`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `gate_id` | INTEGER | **PK**, FK → `gate.id` | PK composta |
| `shift_type` | `ShiftType` | **PK** | PK composta (MORNING/AFTERNOON/NIGHT) |
| `date` | DATE | **PK** | PK composta |
| `operator_num_worker` | VARCHAR(20) | FK → `operator.num_worker` | Operador da cancela |
| `manager_num_worker` | VARCHAR(20) | FK → `manager.num_worker` | Gestor responsável |

> Horas derivadas do enum (`start_time`/`end_time`), não armazenadas.

### Reserva e carga

#### `booking`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `reference` | VARCHAR(50) | PK | Ex.: `BOOK-0001` |
| `direction` | `direction` | | `inbound` / `outbound` |
| `created_at` | TIMESTAMP | DEFAULT now() | |

#### `cargo`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `booking_reference` | VARCHAR(50) | NOT NULL, FK → `booking.reference` | Reserva |
| `quantity` | DECIMAL(10,2) | NOT NULL | Quantidade |
| `state` | `physical_state` | NOT NULL | Estado físico |
| `description` | TEXT | | Detalhes |

### Planeamento — `appointment` (agregado central)
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `arrival_id` | VARCHAR(50) | INDEX | PIN `PRT-XXXX` (gerado por trigger/sequência) |
| `booking_reference` | VARCHAR(50) | NOT NULL, FK → `booking.reference` | |
| `driver_license` | VARCHAR(50) | **NULLABLE**, FK → `driver.drivers_license` | Nullable desde **v5** (import CSV / desacoplamento RGPD; condutor reclama por PIN) |
| `truck_license_plate` | VARCHAR(20) | NOT NULL, FK → `truck.license_plate` | |
| `terminal_id` | INTEGER | NOT NULL, FK → `terminal.id` | |
| `gate_in_id` / `gate_out_id` | INTEGER | FK → `gate.id` | Cancela entrada/saída |
| `scheduled_start_time` | TIMESTAMP | | Hora planeada |
| `expected_duration` | INTEGER | | Duração prevista (min) |
| `status` | `appointment_status` | DEFAULT 'scheduled' | Fluxo armazenado |
| `version` | INTEGER | NOT NULL, DEFAULT 1 | **Concorrência otimista** (Guardrail 6) |
| `notes` | TEXT | | Notas |
| `highway_infraction` | BOOLEAN | DEFAULT FALSE | Camião hazmat em rota restrita (BR-42) |
| `reviewed_at` / `reviewed_by` / `review_note` | TIMESTAMP / VARCHAR(50) / TEXT | NULLABLE | Revisão da infração pelo gestor (v4) |

### Execução — `visit` (1:1 com appointment)
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `appointment_id` | INTEGER | **PK = FK** → `appointment.id` | Relação 1:1 |
| `shift_gate_id` / `shift_type` / `shift_date` | INTEGER / `ShiftType` / DATE | FK composta → `shift` | Turno em que ocorreu |
| `entry_time` / `out_time` | TIMESTAMP | | Tempos reais |
| `state` | `delivery_status` | DEFAULT 'in_port' | `in_port → unloading → done` |

### Alertas e histórico

#### `alert`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `visit_id` | INTEGER | FK → `visit.appointment_id` | Nullable (alerta pode preceder a visita) |
| `appointment_id` | INTEGER | FK → `appointment.id` | Ligação direta (alertas pré-visita) |
| `timestamp` | TIMESTAMP | DEFAULT now() | |
| `image_url` | TEXT | | Blob MinIO |
| `type` | `type_alert` | DEFAULT 'generic' | Categoria |
| `severity` | SMALLINT | CHECK 1–5, DEFAULT 3 | **1 (baixa) – 5 (crítica)** (BR-11) |
| `description` | TEXT | | |

#### `shift_alert_history`
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `shift_gate_id` / `shift_type` / `shift_date` | — | FK composta → `shift` | Turno |
| `alert_id` | INTEGER | NOT NULL, FK → `alert.id` | Alerta |
| `last_update` | TIMESTAMP | DEFAULT now() | Criado por trigger no insert do alerta |

### Histórico condutor↔veículo — `driver_vehicle` (BR-52)
| Coluna | Tipo | PK/FK | Descrição |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador |
| `driver_license` | VARCHAR(50) | FK → `driver` (RESTRICT) | Condutor |
| `truck_license_plate` | VARCHAR(20) | FK → `truck` (RESTRICT) | Camião |
| `start_date` | DATE | NOT NULL | Início da afetação |
| `end_date` | DATE | | Fim (NULL = atual) |

> Resolve a relação **M:N** Condutor↔Camião com histórico temporal.
> `CHECK end_date >= start_date`; `UNIQUE(driver_license, truck_license_plate, start_date)`.

### Tabelas operacionais / infraestrutura de eventos

| Tabela | Chave | Propósito |
|---|---|---|
| `pending_reviews` | `event_id` (UUID) PK | Fila durável de revisão do operador (PD-01); `status` PENDING→APPROVED\|REJECTED; cache em Redis. |
| `inbox_events` | `id` PK, `event_id` UNIQUE | **Inbox idempotente** de eventos Kafka consumidos (Guardrail 1); `status` RECEIVED→PROCESSING→PROCESSED\|FAILED\|DEAD_LETTER. |
| `outbox_events` | `id` PK, `event_id` UNIQUE | **Transactional Outbox** (Guardrail 3) — efeitos persistidos na mesma transação PG; relay publica em Kafka; `status` PENDING→PUBLISHED\|FAILED\|DEAD_LETTER, com `retry_count`/`next_retry_at`. |
| `schema_migrations` | — | Registo de migrações aplicadas. |

> Colunas detalhadas de `inbox_events`/`outbox_events`: ver `SCHEMA_REFERENCE.md`.

---

## Relações e cardinalidades

| Entidade A | Relação | Entidade B | Cardinalidade |
|---|---|---|---|
| `manager` / `operator` | is-a | `worker` | 1:1 (especialização disjunta) |
| `company` | emprega | `driver` | 1:N |
| `company` | possui | `truck` | 1:N |
| `driver` ↔ `truck` | afetação (histórico) | via `driver_vehicle` | M:N |
| `booking` | contém | `cargo` | 1:N |
| `booking` | origina | `appointment` | 1:N |
| `truck` | realiza | `appointment` | 1:N |
| `driver` | (opcional) conduz | `appointment` | 0..1:N |
| `terminal` | destino de | `appointment` | 1:N |
| `gate` | entrada/saída de | `appointment` | 1:N (gate_in / gate_out) |
| `appointment` | executa | `visit` | 1:0..1 |
| `gate` | tem | `shift` | 1:N |
| `manager` / `operator` | afetos a | `shift` | 1:N |
| `shift` | enquadra | `visit` | 1:N |
| `visit` | gera | `alert` | 1:N |
| `appointment` | (direta) gera | `alert` | 1:N |
| `shift` ↔ `alert` | histórico | via `shift_alert_history` | M:N |

---

## Integridade e mecanismos

- **Triggers** (`scripts/triggers.sql`): `trg_generate_arrival_id` (gera `arrival_id = PRT-XXXX` via
  `appointment_arrival_seq`, concorrência-segura), `trg_check_visit_completion` (auto-conclusão da
  visita ao definir `out_time`), `shift_alert_history` automático, timestamps `created_at`.
- **Concorrência otimista** em `appointment` via coluna `version` (`WHERE version = <lido>`) — Guardrail 6.
- **RGPD**: `worker.phone`/`worker.email` e `driver.mobile_device_token` cifrados em repouso
  (AES-256-GCM); `email` usa nonce determinístico para ser pesquisável (login).
- **Consistência polyglot**: sem 2PC — Transactional Outbox + Inbox idempotente. O outbox worker
  projeta para Mongo/Redis (read models CQRS).
- Migrações idempotentes (`IF NOT EXISTS` / blocos `DO $$ ... EXCEPTION`).

---

## Notas técnicas
- SGBD: **PostgreSQL 15**; encoding `UTF-8`.
- PKs geradas por `SERIAL`/sequência ou identificadores de negócio (NIF, matrícula, nº carta).
- FKs garantem integridade referencial; `driver_vehicle` usa `ON DELETE RESTRICT`.
- Integração não-relacional: **MongoDB** (`agent_detections`, `decision_events`, read models,
  `statistics_*`, `notifications`) e **Redis** (cache/contadores/dedup) — ver `docs/bd/Nao_Relacional/`.

---

**Versão:** 2.0
**Atualização:** Maio 2026
**Equipa:** Porto Inteligente — Engenharia Informática @ UA

**Changelog v2.0:**
- Reescrita completa para o schema **implementado** (identificadores em inglês), alinhada com
  `sql_models.py`/`inbox_outbox_models.py` e migrações v3–v5.
- Substituído o modelo conceptual antigo (EMPRESA/CHEGADAS_DIARIAS/DETEÇÃO/CAIS/session_token).
- Adicionados: `terminal`, `booking`/`cargo`, PKs compostas (`dock`, `shift`, `visit`),
  `driver_vehicle` (M:N), `pending_reviews`, `inbox_events`, `outbox_events`.
- Estado-máquina v4 (`appointment_status` 5 valores + sub-estados computados; `delivery_status`
  `in_port/unloading/done`), `driver_license` nullable (v5), colunas de revisão de infração,
  `version` (concorrência otimista), encriptação RGPD.

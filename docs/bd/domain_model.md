# Domain Model — Data Module (PostgreSQL)

> Modelo de domínio da base de dados relacional (fonte de verdade ACID).
> **Fonte:** `src/V_APP/Data_Module/infrastructure/persistence/sql_models.py` (+ `inbox_outbox_models.py`).
> Detalhe coluna-a-coluna: [`Relacional/Base_Dados_relacional.md`](Relacional/Base_Dados_relacional.md)
> e `code_documentation/V_APP/Data_Module/SCHEMA_REFERENCE.md`.
>
> Diagrama em **Mermaid `erDiagram`** — renderiza diretamente no GitHub/GitLab/VS Code.
> Para exportar imagem (ex.: relatório LaTeX): colar em <https://mermaid.live> ou `mmdc -i domain_model.md -o domain_model.png`.

```mermaid
erDiagram
    WORKER ||--o| OPERATOR : "is-a"
    WORKER ||--o| MANAGER : "is-a"
    COMPANY ||--o{ DRIVER : employs
    COMPANY ||--o{ TRUCK : owns
    TERMINAL ||--o{ DOCK : has
    TERMINAL ||--o{ APPOINTMENT : targets
    DRIVER |o--o{ APPOINTMENT : drives
    TRUCK ||--o{ APPOINTMENT : performs
    BOOKING ||--o{ CARGO : contains
    BOOKING ||--o{ APPOINTMENT : schedules
    GATE ||--o{ APPOINTMENT : "entry (gate_in)"
    GATE ||--o{ APPOINTMENT : "exit (gate_out)"
    GATE ||--o{ SHIFT : hosts
    OPERATOR ||--o{ SHIFT : staffs
    MANAGER ||--o{ SHIFT : supervises
    APPOINTMENT ||--o| VISIT : executes
    SHIFT ||--o{ VISIT : frames
    VISIT ||--o{ ALERT : raises
    APPOINTMENT ||--o{ ALERT : "may raise"
    SHIFT ||--o{ SHIFT_ALERT_HISTORY : logs
    ALERT ||--o{ SHIFT_ALERT_HISTORY : "history of"
    DRIVER ||--o{ DRIVER_VEHICLE : assigned
    TRUCK ||--o{ DRIVER_VEHICLE : assigned

    WORKER {
        string num_worker PK
        string name
        string phone "AES-256-GCM (RGPD)"
        string email UK "encrypted, searchable"
        text password_hash "bcrypt"
        boolean active
        timestamp created_at
    }
    OPERATOR {
        string num_worker PK,FK
    }
    MANAGER {
        string num_worker PK,FK
        enum access_level "admin | basic"
    }
    GATE {
        int id PK
        string label
        decimal latitude
        decimal longitude
        string estado "Ativo | Inativo"
    }
    TERMINAL {
        int id PK
        string name
        decimal latitude
        decimal longitude
        boolean hazmat_approved
    }
    DOCK {
        int terminal_id PK,FK
        string bay_number PK
        decimal latitude
        decimal longitude
        enum current_usage "operational_status"
        string estado "Ativo | Inativo"
    }
    COMPANY {
        string nif PK
        string name
        string contact
    }
    DRIVER {
        string drivers_license PK
        string company_nif FK
        string name
        text password_hash "bcrypt"
        string mobile_device_token "AES-256-GCM (RGPD)"
        boolean active
        int current_appointment_id
        timestamp created_at
    }
    TRUCK {
        string license_plate PK
        string company_nif FK
        string brand
    }
    BOOKING {
        string reference PK
        enum direction "inbound | outbound"
        timestamp created_at
    }
    CARGO {
        int id PK
        string booking_reference FK
        decimal quantity
        enum state "physical_state"
        text description
    }
    SHIFT {
        int gate_id PK,FK
        enum shift_type PK "MORNING | AFTERNOON | NIGHT"
        date date PK
        string operator_num_worker FK
        string manager_num_worker FK
    }
    APPOINTMENT {
        int id PK
        string arrival_id "PIN PRT-XXXX (trigger)"
        string booking_reference FK
        string driver_license FK "nullable since v5"
        string truck_license_plate FK
        int terminal_id FK
        int gate_in_id FK
        int gate_out_id FK
        timestamp scheduled_start_time
        int expected_duration
        enum status "appointment_status"
        int version "optimistic concurrency"
        text notes
        boolean highway_infraction
        timestamp reviewed_at
        string reviewed_by
        text review_note
    }
    VISIT {
        int appointment_id PK,FK
        int shift_gate_id FK
        enum shift_type FK
        date shift_date FK
        timestamp entry_time
        timestamp out_time
        enum state "in_port | unloading | done"
    }
    ALERT {
        int id PK
        int visit_id FK
        int appointment_id FK
        timestamp timestamp
        text image_url
        enum type "type_alert"
        smallint severity "1 (low) - 5 (critical)"
        text description
    }
    SHIFT_ALERT_HISTORY {
        int id PK
        int shift_gate_id FK
        enum shift_type FK
        date shift_date FK
        int alert_id FK
        timestamp last_update
    }
    DRIVER_VEHICLE {
        int id PK
        string driver_license FK
        string truck_license_plate FK
        date start_date
        date end_date
    }
```

## Notas
- **Sub-estados computados** (nunca armazenados): `delayed`, `unloading`, `in_port`, `leaving_port`
  derivam de `appointment.status` + `visit.state` + tempo (`computed_status` no ORM).
- **DRIVER_VEHICLE** materializa a relação M:N Condutor↔Camião com histórico temporal (BR-52).
- Tabelas de infraestrutura de eventos (`inbox_events`, `outbox_events`, `pending_reviews`,
  `schema_migrations`) não fazem parte do modelo de domínio — ver `SCHEMA_REFERENCE.md`.

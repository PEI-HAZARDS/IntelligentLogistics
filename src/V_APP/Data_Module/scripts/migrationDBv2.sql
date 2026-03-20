-- ============================================================
-- Migration DB v2 — Data Module Refactor
-- From: pre-refactor schema (v1 baseline)
-- To:   current schema with inbox/outbox, optimistic concurrency,
--       arrival_id sequence, and all triggers/indexes
--
-- Safe to re-run: uses IF NOT EXISTS, OR REPLACE, and
--   DO $$ blocks with column-existence checks.
--
-- Usage:
--   psql -U <user> -d <database> -f scripts/migrationDBv2.sql
--
-- Date: 2026-03-20
-- ============================================================

BEGIN;

-- ============================================================
-- 1. NEW COLUMN: appointment.version (Optimistic Concurrency)
--    Iteration A4 — prevents lost-update races on status change
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'appointment' AND column_name = 'version'
    ) THEN
        ALTER TABLE appointment
            ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
        RAISE NOTICE 'Added appointment.version column';
    ELSE
        RAISE NOTICE 'appointment.version already exists — skipping';
    END IF;
END $$;


-- ============================================================
-- 2. NEW TABLE: inbox_events (Idempotent Kafka consumer inbox)
--    Iteration A2 — Guardrail 1 & 4
--    State machine: RECEIVED → PROCESSING → PROCESSED | FAILED | DEAD_LETTER
-- ============================================================

CREATE TABLE IF NOT EXISTS inbox_events (
    id              SERIAL PRIMARY KEY,
    event_id        VARCHAR(64)   NOT NULL,
    topic           VARCHAR(255)  NOT NULL,
    partition       INTEGER       NOT NULL,
    "offset"        INTEGER       NOT NULL,
    aggregate_type  VARCHAR(128)  NOT NULL,
    aggregate_id    VARCHAR(128)  NOT NULL,
    event_type      VARCHAR(128)  NOT NULL,
    event_version   INTEGER       NOT NULL,
    status          VARCHAR(20)   NOT NULL DEFAULT 'RECEIVED',
    retry_count     INTEGER       NOT NULL DEFAULT 0,
    last_error      TEXT,
    payload_hash    VARCHAR(64),
    payload         JSONB,
    received_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,

    CONSTRAINT uq_inbox_event_id UNIQUE (event_id)
);

-- Index for dedup lookups (covered by UNIQUE but explicit for clarity)
CREATE INDEX IF NOT EXISTS idx_inbox_event_id
    ON inbox_events (event_id);

-- Index for consumer polling: fetch RECEIVED rows ordered by id
CREATE INDEX IF NOT EXISTS idx_inbox_status_id
    ON inbox_events (status, id)
    WHERE status IN ('RECEIVED', 'PROCESSING', 'FAILED');


-- ============================================================
-- 3. NEW TABLE: outbox_events (Transactional Outbox)
--    Iteration A2 + B1 — Guardrail 3 & 8
--    State machine: PENDING → PUBLISHED | FAILED | DEAD_LETTER
-- ============================================================

CREATE TABLE IF NOT EXISTS outbox_events (
    id              SERIAL PRIMARY KEY,
    event_id        VARCHAR(64)   NOT NULL,
    topic           VARCHAR(255)  NOT NULL,
    partition_key   VARCHAR(255)  NOT NULL,
    aggregate_type  VARCHAR(128)  NOT NULL,
    aggregate_id    VARCHAR(128)  NOT NULL,
    event_type      VARCHAR(128)  NOT NULL,
    event_version   INTEGER       NOT NULL,
    payload         JSONB         NOT NULL,
    status          VARCHAR(20)   NOT NULL DEFAULT 'PENDING',
    retry_count     INTEGER       NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ,
    next_retry_at   TIMESTAMPTZ,

    CONSTRAINT uq_outbox_event_id UNIQUE (event_id)
);

-- Index for dedup lookups
CREATE INDEX IF NOT EXISTS idx_outbox_event_id
    ON outbox_events (event_id);

-- Index for worker polling: PENDING + retryable FAILED rows
CREATE INDEX IF NOT EXISTS idx_outbox_status_retry
    ON outbox_events (status, id)
    WHERE status IN ('PENDING', 'FAILED');

-- Index for retry scheduling: next_retry_at lookup
CREATE INDEX IF NOT EXISTS idx_outbox_next_retry
    ON outbox_events (next_retry_at)
    WHERE status = 'FAILED' AND next_retry_at IS NOT NULL;


-- ============================================================
-- 4. SEQUENCE + TRIGGER: arrival_id auto-generation
--    Iteration A1 — replaces ORM max()+1 (race-condition fix)
--    Generates PRT-XXXX format using a PG sequence
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS appointment_arrival_seq START 1;

-- Re-sync sequence to max existing arrival_id
SELECT setval(
    'appointment_arrival_seq',
    COALESCE(
        (SELECT MAX(CAST(SUBSTRING(arrival_id FROM 'PRT-([0-9]+)') AS INTEGER))
         FROM appointment
         WHERE arrival_id LIKE 'PRT-%'),
        0
    ),
    true
);

CREATE OR REPLACE FUNCTION fn_generate_arrival_id()
RETURNS TRIGGER AS $$
DECLARE
    new_id TEXT;
    seq_num INTEGER;
BEGIN
    IF COALESCE(NEW.arrival_id, '') = '' THEN
        seq_num := nextval('appointment_arrival_seq');
        new_id := 'PRT-' || LPAD(seq_num::TEXT, 4, '0');
        NEW.arrival_id := new_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_generate_arrival_id ON appointment;
CREATE TRIGGER trg_generate_arrival_id
    BEFORE INSERT ON appointment
    FOR EACH ROW
    EXECUTE FUNCTION fn_generate_arrival_id();


-- ============================================================
-- 5. TRIGGERS: Status validation & auto-completion
--    (Safe to re-run — OR REPLACE + DROP IF EXISTS)
-- ============================================================

-- 5a. Prevent reverting from completed/canceled
CREATE OR REPLACE FUNCTION fn_validate_status_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IN ('completed', 'canceled') AND NEW.status != OLD.status THEN
        RAISE EXCEPTION 'Cannot change status from % to %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validate_status_transition ON appointment;
CREATE TRIGGER trg_validate_status_transition
    BEFORE UPDATE ON appointment
    FOR EACH ROW
    EXECUTE FUNCTION fn_validate_status_transition();

-- 5b. Auto-complete visit + appointment when out_time is set
CREATE OR REPLACE FUNCTION fn_check_visit_completion()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.out_time IS NOT NULL
       AND OLD.out_time IS NULL
       AND NEW.state = 'unloading' THEN
        NEW.state := 'completed';
        UPDATE appointment SET status = 'completed'
        WHERE id = NEW.appointment_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_visit_completion ON visit;
CREATE TRIGGER trg_visit_completion
    BEFORE UPDATE ON visit
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_visit_completion();

-- 5c. Auto-set entry_time on visit insert
CREATE OR REPLACE FUNCTION fn_set_visit_entry_time()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.entry_time IS NULL THEN
        NEW.entry_time := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_visit_entry_time ON visit;
CREATE TRIGGER trg_visit_entry_time
    BEFORE INSERT ON visit
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_visit_entry_time();

-- 5d. Auto-set alert timestamp
CREATE OR REPLACE FUNCTION fn_set_alert_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.timestamp IS NULL THEN
        NEW.timestamp := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_alert_timestamp ON alert;
CREATE TRIGGER trg_alert_timestamp
    BEFORE INSERT ON alert
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_alert_timestamp();

-- 5e. Auto-create shift_alert_history on alert insert
CREATE OR REPLACE FUNCTION fn_create_shift_alert_history()
RETURNS TRIGGER AS $$
DECLARE
    v_shift_gate_id INTEGER;
    v_shift_type TEXT;
    v_shift_date DATE;
BEGIN
    IF NEW.visit_id IS NOT NULL THEN
        SELECT shift_gate_id, shift_type::TEXT, shift_date
        INTO v_shift_gate_id, v_shift_type, v_shift_date
        FROM visit
        WHERE appointment_id = NEW.visit_id;

        IF v_shift_gate_id IS NOT NULL THEN
            INSERT INTO shift_alert_history (
                shift_gate_id, shift_type, shift_date, alert_id, last_update
            ) VALUES (
                v_shift_gate_id, v_shift_type::shifttype, v_shift_date, NEW.id, NOW()
            );
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_create_shift_alert_history ON alert;
CREATE TRIGGER trg_create_shift_alert_history
    AFTER INSERT ON alert
    FOR EACH ROW
    EXECUTE FUNCTION fn_create_shift_alert_history();

-- 5f. Auto-set timestamps on insert
CREATE OR REPLACE FUNCTION fn_set_booking_created_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_at IS NULL THEN NEW.created_at := NOW(); END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_booking_created_at ON booking;
CREATE TRIGGER trg_booking_created_at
    BEFORE INSERT ON booking FOR EACH ROW
    EXECUTE FUNCTION fn_set_booking_created_at();

CREATE OR REPLACE FUNCTION fn_set_worker_created_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_at IS NULL THEN NEW.created_at := NOW(); END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_worker_created_at ON worker;
CREATE TRIGGER trg_worker_created_at
    BEFORE INSERT ON worker FOR EACH ROW
    EXECUTE FUNCTION fn_set_worker_created_at();

CREATE OR REPLACE FUNCTION fn_set_driver_created_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_at IS NULL THEN NEW.created_at := NOW(); END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_driver_created_at ON driver;
CREATE TRIGGER trg_driver_created_at
    BEFORE INSERT ON driver FOR EACH ROW
    EXECUTE FUNCTION fn_set_driver_created_at();

-- 5g. Delayed sync function (optional, for analytics)
CREATE OR REPLACE FUNCTION fn_sync_delayed_appointments()
RETURNS TABLE(updated_count INTEGER, appointments_updated INTEGER[]) AS $$
DECLARE
    affected_ids INTEGER[];
BEGIN
    WITH updated AS (
        UPDATE appointment
        SET status = 'delayed'
        WHERE status = 'in_transit'
          AND scheduled_start_time IS NOT NULL
          AND scheduled_start_time + INTERVAL '5 minutes' < NOW()
        RETURNING id
    )
    SELECT ARRAY_AGG(id) INTO affected_ids FROM updated;

    RETURN QUERY SELECT
        COALESCE(array_length(affected_ids, 1), 0),
        COALESCE(affected_ids, ARRAY[]::INTEGER[]);
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 6. INDEXES (performance optimization)
--    All use IF NOT EXISTS — safe to re-run
-- ============================================================

-- Appointment
CREATE INDEX IF NOT EXISTS idx_appointment_gate_in_id       ON appointment(gate_in_id);
CREATE INDEX IF NOT EXISTS idx_appointment_status            ON appointment(status);
CREATE INDEX IF NOT EXISTS idx_appointment_scheduled_date    ON appointment(DATE(scheduled_start_time));
CREATE INDEX IF NOT EXISTS idx_appointment_gate_status_date  ON appointment(gate_in_id, status, DATE(scheduled_start_time));
CREATE INDEX IF NOT EXISTS idx_appointment_truck_plate       ON appointment(truck_license_plate);
CREATE INDEX IF NOT EXISTS idx_appointment_driver            ON appointment(driver_license);
CREATE INDEX IF NOT EXISTS idx_appointment_booking           ON appointment(booking_reference);
CREATE INDEX IF NOT EXISTS idx_appointment_terminal          ON appointment(terminal_id);
CREATE INDEX IF NOT EXISTS idx_appointment_gate_out_id       ON appointment(gate_out_id);

-- Visit
CREATE INDEX IF NOT EXISTS idx_visit_shift_composite  ON visit(shift_gate_id, shift_type, shift_date);
CREATE INDEX IF NOT EXISTS idx_visit_state            ON visit(state);
CREATE INDEX IF NOT EXISTS idx_visit_entry_time       ON visit(entry_time);
CREATE INDEX IF NOT EXISTS idx_visit_out_time         ON visit(out_time);

-- Shift
CREATE INDEX IF NOT EXISTS idx_shift_operator   ON shift(operator_num_worker);
CREATE INDEX IF NOT EXISTS idx_shift_manager    ON shift(manager_num_worker);
CREATE INDEX IF NOT EXISTS idx_shift_gate_date  ON shift(gate_id, date);

-- Alert
CREATE INDEX IF NOT EXISTS idx_alert_visit_id        ON alert(visit_id);
CREATE INDEX IF NOT EXISTS idx_alert_type            ON alert(type);
CREATE INDEX IF NOT EXISTS idx_alert_timestamp       ON alert(timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_type_timestamp  ON alert(type, timestamp);

-- Worker
CREATE INDEX IF NOT EXISTS idx_worker_email_active  ON worker(email, active);
CREATE INDEX IF NOT EXISTS idx_worker_active        ON worker(active);

-- Driver
CREATE INDEX IF NOT EXISTS idx_driver_license_active  ON driver(drivers_license, active);
CREATE INDEX IF NOT EXISTS idx_driver_active          ON driver(active);
CREATE INDEX IF NOT EXISTS idx_driver_company         ON driver(company_nif);

-- Booking / Cargo
CREATE INDEX IF NOT EXISTS idx_cargo_booking      ON cargo(booking_reference);
CREATE INDEX IF NOT EXISTS idx_booking_direction   ON booking(direction);

-- Shift Alert History
CREATE INDEX IF NOT EXISTS idx_shift_alert_history_alert  ON shift_alert_history(alert_id);
CREATE INDEX IF NOT EXISTS idx_shift_alert_history_shift  ON shift_alert_history(shift_gate_id, shift_type, shift_date);


COMMIT;

-- ============================================================
-- MIGRATION SUMMARY
-- ============================================================
--
-- New tables:
--   inbox_events   — idempotent Kafka consumer inbox (Guardrail 1 & 4)
--   outbox_events  — transactional outbox with retry/DLQ (Guardrail 3 & 8)
--
-- New columns:
--   appointment.version — optimistic concurrency control (default 1)
--
-- New sequence:
--   appointment_arrival_seq — race-safe arrival_id generation
--
-- New triggers (10):
--   trg_generate_arrival_id        — PRT-XXXX auto-generation
--   trg_validate_status_transition — prevent invalid state changes
--   trg_visit_completion           — auto-complete visit + appointment
--   trg_visit_entry_time           — auto-set entry_time
--   trg_alert_timestamp            — auto-set alert timestamp
--   trg_create_shift_alert_history — auto-link alerts to shift history
--   trg_booking_created_at         — auto-set booking timestamp
--   trg_worker_created_at          — auto-set worker timestamp
--   trg_driver_created_at          — auto-set driver timestamp
--
-- New indexes:
--   3 on inbox_events  (event_id, status+id partial, status polling)
--   3 on outbox_events (event_id, status+id partial, next_retry_at)
--   26 on existing tables (appointment, visit, shift, alert, etc.)
--
-- ============================================================

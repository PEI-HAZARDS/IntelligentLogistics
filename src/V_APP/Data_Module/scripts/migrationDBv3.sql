-- ============================================================
-- Migration DB v3 — Data Module Polyglot Architecture Phase 3
-- From: v2 schema (inbox/outbox, optimistic concurrency)
-- To:   v3 with BR constraints, driver_vehicle, pending_reviews,
--       auth session columns removed from driver table
--
-- Safe to re-run: every change is guarded by IF NOT EXISTS /
--   column-existence checks inside DO $$ blocks.
--
-- Usage:
--   psql -U <user> -d <database> -f scripts/migrationDBv3.sql
--
-- Tracked in schema_migrations table (version 3).
-- Date: 2026-04-21
-- ============================================================

BEGIN;

-- ============================================================
-- 0. VERSION TRACKING TABLE
--    One row per applied migration; idempotent insert at end.
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER     PRIMARY KEY,
    description TEXT        NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Backfill v1 and v2 if not already tracked
INSERT INTO schema_migrations (version, description, applied_at)
VALUES
    (1, 'Baseline schema', NOW()),
    (2, 'inbox/outbox, optimistic concurrency, arrival_id sequence, triggers/indexes', NOW())
ON CONFLICT (version) DO NOTHING;


-- ============================================================
-- 1. BR-11: alert.severity  SMALLINT CHECK 1–5 (default 3)
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'alert' AND column_name = 'severity'
    ) THEN
        ALTER TABLE alert
            ADD COLUMN severity SMALLINT NOT NULL DEFAULT 3
                CONSTRAINT chk_alert_severity CHECK (severity BETWEEN 1 AND 5);
        RAISE NOTICE 'Added alert.severity column (BR-11)';
    ELSE
        RAISE NOTICE 'alert.severity already exists — skipping (BR-11)';
    END IF;
END $$;


-- ============================================================
-- 2. BR-14: gate.estado  VARCHAR CHECK {Ativo, Inativo}
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'gate' AND column_name = 'estado'
    ) THEN
        ALTER TABLE gate
            ADD COLUMN estado VARCHAR(10) NOT NULL DEFAULT 'Ativo' -- NOSONAR
                CONSTRAINT chk_gate_estado CHECK (estado IN ('Ativo', 'Inativo'));
        RAISE NOTICE 'Added gate.estado column (BR-14)';
    ELSE
        RAISE NOTICE 'gate.estado already exists — skipping (BR-14)';
    END IF;
END $$;


-- ============================================================
-- 3. BR-13: dock.estado  VARCHAR CHECK {Ativo, Inativo}
--    Kept alongside current_usage (operational_status enum)
--    for backward compatibility until frontend migrates.
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'dock' AND column_name = 'estado'
    ) THEN
        ALTER TABLE dock
            ADD COLUMN estado VARCHAR(10) NOT NULL DEFAULT 'Ativo'
                CONSTRAINT chk_dock_estado CHECK (estado IN ('Ativo', 'Inativo'));
        RAISE NOTICE 'Added dock.estado column (BR-13)';
    ELSE
        RAISE NOTICE 'dock.estado already exists — skipping (BR-13)';
    END IF;
END $$;


-- ============================================================
-- 4. BR-52: driver_vehicle — temporal driver↔truck history
-- ============================================================

CREATE TABLE IF NOT EXISTS driver_vehicle (
    id                  SERIAL          PRIMARY KEY,
    driver_license      VARCHAR(50)     NOT NULL REFERENCES driver(drivers_license) ON DELETE RESTRICT,
    truck_license_plate VARCHAR(20)     NOT NULL REFERENCES truck(license_plate)    ON DELETE RESTRICT,
    start_date          DATE            NOT NULL,
    end_date            DATE,

    CONSTRAINT chk_dv_dates CHECK (end_date IS NULL OR end_date >= start_date),
    CONSTRAINT uq_dv_assignment UNIQUE (driver_license, truck_license_plate, start_date)
);

CREATE INDEX IF NOT EXISTS idx_driver_vehicle_driver ON driver_vehicle(driver_license);
CREATE INDEX IF NOT EXISTS idx_driver_vehicle_truck  ON driver_vehicle(truck_license_plate);
CREATE INDEX IF NOT EXISTS idx_driver_vehicle_active ON driver_vehicle(driver_license)
    WHERE end_date IS NULL;


-- ============================================================
-- 5. PD-01 PREP: pending_reviews — durable operator review queue
--    Replaces the Redis-only pending_review:{truck_id} key.
--    Redis caches this projection; PG is source of truth.
-- ============================================================

CREATE TABLE IF NOT EXISTS pending_reviews (
    event_id        UUID            PRIMARY KEY,
    truck_id        VARCHAR(20)     NOT NULL,
    gate_id         INTEGER         NOT NULL,
    license_plate   VARCHAR(20)     NOT NULL,
    payload         JSONB           NOT NULL DEFAULT '{}',
    status          VARCHAR(20)     NOT NULL DEFAULT 'PENDING' -- NOSONAR
                        CONSTRAINT chk_pr_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolved_by     VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_pending_reviews_status    ON pending_reviews(status) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_pending_reviews_truck     ON pending_reviews(truck_id);
CREATE INDEX IF NOT EXISTS idx_pending_reviews_gate      ON pending_reviews(gate_id);
CREATE INDEX IF NOT EXISTS idx_pending_reviews_created   ON pending_reviews(created_at);


-- ============================================================
-- 6. BR-20: appointment.arrival_id UNIQUE
--    Fill any NULL arrival_ids first via the v2 sequence trigger
--    (trg_generate_arrival_id fires on INSERT; here we UPDATE
--     NULLs by reinserting into a temp table via the trigger).
--    Safe: trigger was created in v2; sequence already seeded.
-- ============================================================

DO $$
DECLARE
    seq_num  INTEGER;
    new_id   TEXT;
    rec      RECORD;
BEGIN
    -- Fill NULL arrival_ids using the same PRT-XXXX sequence
    FOR rec IN
        SELECT id FROM appointment WHERE arrival_id IS NULL ORDER BY id
    LOOP
        seq_num := nextval('appointment_arrival_seq');
        new_id  := 'PRT-' || LPAD(seq_num::TEXT, 4, '0');
        UPDATE appointment SET arrival_id = new_id WHERE id = rec.id;
    END LOOP;

    -- Now add the UNIQUE constraint if it does not exist
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'appointment'
          AND constraint_name = 'uq_appointment_arrival_id'
          AND constraint_type = 'UNIQUE'
    ) THEN
        ALTER TABLE appointment
            ADD CONSTRAINT uq_appointment_arrival_id UNIQUE (arrival_id);
        RAISE NOTICE 'Added UNIQUE constraint on appointment.arrival_id (BR-20)';
    ELSE
        RAISE NOTICE 'appointment.arrival_id UNIQUE already exists — skipping (BR-20)';
    END IF;
END $$;


-- ============================================================
-- 7. DROP driver session columns
--    Auth sessions moved to Redis (Phase 2).
--    Guarded: only drop if column still exists.
-- ============================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'driver' AND column_name = 'session_token'
    ) THEN
        ALTER TABLE driver DROP COLUMN session_token;
        RAISE NOTICE 'Dropped driver.session_token';
    ELSE
        RAISE NOTICE 'driver.session_token already gone — skipping';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'driver' AND column_name = 'session_expires_at'
    ) THEN
        ALTER TABLE driver DROP COLUMN session_expires_at;
        RAISE NOTICE 'Dropped driver.session_expires_at';
    ELSE
        RAISE NOTICE 'driver.session_expires_at already gone — skipping';
    END IF;
END $$;


-- ============================================================
-- 8. REGISTER v3
-- ============================================================

INSERT INTO schema_migrations (version, description)
VALUES (3, 'BR-11 alert.severity, BR-14 gate.estado, BR-13 dock.estado, BR-52 driver_vehicle, PD-01 pending_reviews, BR-20 arrival_id UNIQUE, drop driver session cols')
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- ============================================================
-- MIGRATION SUMMARY
-- ============================================================
--
-- New tables:
--   schema_migrations  — version tracking (safe to re-run)
--   driver_vehicle     — BR-52 temporal driver↔truck history
--   pending_reviews    — PD-01 durable operator review queue
--
-- New columns:
--   alert.severity     — BR-11 SMALLINT 1–5 CHECK
--   gate.estado        — BR-14 VARCHAR {Ativo,Inativo} CHECK
--   dock.estado        — BR-13 VARCHAR {Ativo,Inativo} CHECK
--
-- New constraints:
--   appointment.uq_appointment_arrival_id  — BR-20 UNIQUE
--   driver_vehicle.uq_dv_assignment        — unique assignment window
--   driver_vehicle.chk_dv_dates            — end_date >= start_date
--
-- Dropped columns:
--   driver.session_token      — auth moved to Redis
--   driver.session_expires_at — auth moved to Redis
--
-- ============================================================

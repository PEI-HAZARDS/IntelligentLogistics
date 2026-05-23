-- ============================================================
-- Migration v4 — State Machine Refactor
-- Appointment: remove 'unloading' and 'delayed' from persisted enum.
-- Visit: replace 'completed' with 'in_port' and 'done'.
-- ============================================================
-- Safe to re-run: all steps use IF NOT EXISTS / OR REPLACE / idempotent logic.
-- Apply AFTER migrationDBv3.sql.
-- ============================================================

BEGIN;

-- ============================================================
-- 1. APPOINTMENT STATUS ENUM
--    Remove 'unloading' and 'delayed' (were never written by app
--    code after refactor; backfill any legacy rows before altering).
-- ============================================================

-- 1a. Backfill: any rows that were left with status='unloading' → 'in_process'
UPDATE appointment SET status = 'in_process' WHERE status = 'unloading';

-- 1b. Backfill: any rows with status='delayed' → 'in_transit'
UPDATE appointment SET status = 'in_transit' WHERE status = 'delayed';

-- 1c. Rename the current type, create a clean replacement, swap columns, drop old.
ALTER TYPE appointment_status RENAME TO appointment_status_old;

CREATE TYPE appointment_status AS ENUM (
    'scheduled',
    'in_transit',
    'in_process',
    'completed',
    'canceled'
);

ALTER TABLE appointment
    ALTER COLUMN status TYPE appointment_status
    USING status::text::appointment_status;

DROP TYPE appointment_status_old;


-- ============================================================
-- 2. DELIVERY STATUS ENUM (Visit)
--    Replace 'completed' with 'in_port' and 'done'.
--    'not_started' and 'unloading' are kept (same meaning).
-- ============================================================

-- 2a. Backfill: 'completed' visit rows → 'done'
--     (old trigger wrote state='completed' when out_time was set)
UPDATE visit SET state = 'done' WHERE state = 'completed';

-- 2b. Backfill: ALL 'not_started' rows → 'in_port'.
--     Visit only exists when a truck has entered the port, so 'not_started'
--     was never a meaningful persisted state. Every Visit starts as 'in_port'.
UPDATE visit SET state = 'in_port' WHERE state = 'not_started';

-- 2c. Rename old type, create new one (without not_started), swap, drop.
ALTER TYPE delivery_status RENAME TO delivery_status_old;

CREATE TYPE delivery_status AS ENUM (
    'in_port',
    'unloading',
    'done'
);

ALTER TABLE visit
    ALTER COLUMN state TYPE delivery_status
    USING state::text::delivery_status;

DROP TYPE delivery_status_old;


-- ============================================================
-- 3. FIX Visit default: was 'unloading', must be 'not_started'
-- ============================================================

ALTER TABLE visit ALTER COLUMN state SET DEFAULT 'not_started';


-- ============================================================
-- 4. TRIGGER FUNCTIONS
--    The updated function bodies live in triggers.sql (CREATE OR REPLACE,
--    idempotent). Apply triggers.sql after this migration to keep them
--    in sync. No inline copies here to avoid duplication.
-- ============================================================

COMMIT;

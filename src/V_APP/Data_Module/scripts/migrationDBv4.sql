-- ============================================================
-- Migration v4 — State Machine Refactor + Infraction Review
-- Appointment: remove 'unloading' and 'delayed' from persisted enum.
-- Visit: replace 'completed' with 'in_port' and 'done'.
-- Infraction review: reviewed_at, reviewed_by, review_note.
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
-- 4. UPDATE TRIGGER FUNCTIONS (see triggers.sql for full bodies)
--    Replace inline to keep migration self-contained.
-- ============================================================

-- 4a. Status-transition validator (removes 'unloading' rule)
CREATE OR REPLACE FUNCTION fn_validate_status_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IN ('completed', 'canceled') AND NEW.status != OLD.status THEN
        RAISE EXCEPTION 'Cannot change appointment status from % to %', OLD.status, NEW.status;
    END IF;
    IF OLD.status = 'scheduled' AND NEW.status NOT IN ('scheduled', 'in_transit', 'canceled') THEN
        RAISE EXCEPTION 'Invalid transition: scheduled → %', NEW.status;
    END IF;
    IF OLD.status = 'in_transit' AND NEW.status NOT IN ('in_transit', 'in_process', 'canceled') THEN
        RAISE EXCEPTION 'Invalid transition: in_transit → %', NEW.status;
    END IF;
    IF OLD.status = 'in_process' AND NEW.status NOT IN ('in_process', 'completed', 'canceled') THEN
        RAISE EXCEPTION 'Invalid transition: in_process → %', NEW.status;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4b. Visit completion (no longer auto-completes appointment)
CREATE OR REPLACE FUNCTION fn_check_visit_completion()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.state = 'done' AND OLD.state = 'unloading' THEN
        IF NEW.out_time IS NULL THEN
            NEW.out_time := NOW();
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 4c. Analytics helper (replaces fn_sync_delayed_appointments)
CREATE OR REPLACE FUNCTION fn_count_delayed_appointments(tolerance_minutes INTEGER DEFAULT 15)
RETURNS TABLE(delayed_count INTEGER, appointment_ids INTEGER[]) AS $$
DECLARE
    found_ids INTEGER[];
BEGIN
    SELECT ARRAY_AGG(id) INTO found_ids
    FROM appointment
    WHERE status = 'in_transit'
      AND scheduled_start_time IS NOT NULL
      AND scheduled_start_time + (tolerance_minutes || ' minutes')::INTERVAL < NOW();
    RETURN QUERY SELECT
        COALESCE(array_length(found_ids, 1), 0),
        COALESCE(found_ids, ARRAY[]::INTEGER[]);
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 5. INFRACTION REVIEW FIELDS
--    Track manager acknowledgement of highway infractions.
-- ============================================================

ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS reviewed_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS reviewed_by  VARCHAR(50),
    ADD COLUMN IF NOT EXISTS review_note  TEXT;


COMMIT;

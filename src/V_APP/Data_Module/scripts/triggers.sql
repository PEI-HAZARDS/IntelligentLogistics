-- ============================================================
-- Triggers for Intelligent Logistics - Data Module
-- PostgreSQL functions and triggers for automatic operations
-- ============================================================
-- NOTE: 'delayed' status is now computed dynamically in the application
-- layer (sql_models.py computed_status property). These triggers handle
-- definitive state transitions and auto-generation of IDs/timestamps.
-- ============================================================

-- ============================================================
-- 1. COUNT DELAYED APPOINTMENTS (read-only, for analytics)
-- 'delayed' is never stored in the DB — it is computed dynamically
-- in Python (Appointment.is_delayed property). This function only
-- counts how many in_transit appointments are currently past their
-- scheduled_start_time + 15 minutes tolerance.
-- ============================================================

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
-- 2. PREVENT INVALID STATUS TRANSITIONS
-- Only allow valid state transitions
-- ============================================================

CREATE OR REPLACE FUNCTION fn_validate_status_transition()
RETURNS TRIGGER AS $$
BEGIN
    -- Cannot revert from terminal states
    IF OLD.status IN ('completed', 'canceled') AND NEW.status != OLD.status THEN
        RAISE EXCEPTION 'Cannot change appointment status from % to %', OLD.status, NEW.status;
    END IF;

    -- Valid forward transitions only:
    --   scheduled  → in_transit | canceled
    --   in_transit → in_process | canceled
    --   in_process → completed  | canceled
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

DROP TRIGGER IF EXISTS trg_validate_status_transition ON appointment;
CREATE TRIGGER trg_validate_status_transition
    BEFORE UPDATE ON appointment
    FOR EACH ROW
    EXECUTE FUNCTION fn_validate_status_transition();


-- ============================================================
-- 4. VISIT COMPLETION TRIGGER
-- Auto-completes visits after out_time is set
-- ============================================================

CREATE OR REPLACE FUNCTION fn_check_visit_completion()
RETURNS TRIGGER AS $$
BEGIN
    -- When the driver marks unloading as done, transition visit state to 'done'.
    -- The appointment itself is NOT auto-completed here — the driver must explicitly
    -- confirm departure via the app (PATCH /appointments/{id}/status → completed).
    IF NEW.state = 'done' AND OLD.state = 'unloading' THEN
        -- Record out_time if not already set
        IF NEW.out_time IS NULL THEN
            NEW.out_time := NOW();
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_visit_completion ON visit;
CREATE TRIGGER trg_visit_completion
    BEFORE UPDATE ON visit
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_visit_completion();


-- ============================================================
-- 5. VISIT ENTRY TIME AUTO-SET
-- Sets entry_time when visit is created if not provided
-- ============================================================

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


-- ============================================================
-- 6. ALERT TIMESTAMP AUTO-SET
-- Ensures timestamp is always set on alert creation
-- ============================================================

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


-- ============================================================
-- 7. AUTO-GENERATE ARRIVAL ID (PIN)
-- Generates unique arrival_id in format PRT-XXXX if not provided
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS appointment_arrival_seq START 1;

SELECT setval(
    'appointment_arrival_seq',
    GREATEST(
        COALESCE(
            (SELECT MAX(CAST(SUBSTRING(arrival_id FROM 'PRT-([0-9]+)') AS INTEGER))
             FROM appointment
             WHERE arrival_id LIKE 'PRT-%'),
            0
        ),
        1
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
        new_id := 'PRT-' || LPAD(nextval('appointment_arrival_seq')::TEXT, 4, '0');
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
-- 8. AUTO-CREATE SHIFT ALERT HISTORY
-- When alert is created with visit_id, link to shift via history
-- ============================================================

CREATE OR REPLACE FUNCTION fn_create_shift_alert_history()
RETURNS TRIGGER AS $$
DECLARE
    v_shift_gate_id INTEGER;
    v_shift_type TEXT;
    v_shift_date DATE;
BEGIN
    -- Only create history if alert has a visit_id
    IF NEW.visit_id IS NOT NULL THEN
        -- Get shift info from the visit
        SELECT shift_gate_id, shift_type::TEXT, shift_date
        INTO v_shift_gate_id, v_shift_type, v_shift_date
        FROM visit
        WHERE appointment_id = NEW.visit_id;
        
        -- If visit found, create history entry
        IF v_shift_gate_id IS NOT NULL THEN
            INSERT INTO shift_alert_history (
                shift_gate_id,
                shift_type,
                shift_date,
                alert_id,
                last_update
            ) VALUES (
                v_shift_gate_id,
                v_shift_type::shifttype,
                v_shift_date,
                NEW.id,
                NOW()
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


-- ============================================================
-- 9. CREATED_AT AUTO-SET (booking / worker / driver)
-- Single shared function; each table gets its own trigger.
-- ============================================================

CREATE OR REPLACE FUNCTION fn_set_created_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_at IS NULL THEN
        NEW.created_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_booking_created_at ON booking;
CREATE TRIGGER trg_booking_created_at
    BEFORE INSERT ON booking
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_created_at();

DROP TRIGGER IF EXISTS trg_worker_created_at ON worker;
CREATE TRIGGER trg_worker_created_at
    BEFORE INSERT ON worker
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_created_at();

DROP TRIGGER IF EXISTS trg_driver_created_at ON driver;
CREATE TRIGGER trg_driver_created_at
    BEFORE INSERT ON driver
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_created_at();


-- ============================================================
-- USAGE NOTES:
-- ============================================================
--
-- APPOINTMENT STATUS FLOW (persisted enum values only):
--   scheduled → in_transit → in_process → completed | canceled
--
-- VISIT STATE FLOW:
--   not_started → in_port → unloading → done
--   (driver drives to dock → inside port → unloading cargo → unloading done)
--   After 'done', the driver explicitly marks the appointment as 'completed' via app.
--
-- DELAYED STATUS:
-- 'delayed' is never stored. Computed in Python (Appointment.is_delayed) and
-- surfaced as display_status='delayed' in API responses.
-- For analytics counts: SELECT * FROM fn_count_delayed_appointments(15);
--
-- ARRIVAL ID:
-- Auto-generated as PRT-XXXX on appointment insert.
--
-- VISIT COMPLETION:
-- Transitioning visit state to 'done' auto-sets out_time.
-- Appointment completion is explicit (driver confirms departure in app).
--
-- ALERTS:
-- Automatically linked to shift history when created with visit_id.
--
-- ============================================================

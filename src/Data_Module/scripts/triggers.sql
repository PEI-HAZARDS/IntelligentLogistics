-- ============================================================
-- Triggers for Intelligent Logistics - Data Module
-- PostgreSQL functions and triggers for automatic operations
-- ============================================================
-- NOTE: 'delayed' status is now computed dynamically in the application
-- layer (sql_models.py computed_status property). These triggers handle
-- definitive state transitions and auto-generation of IDs/timestamps.
-- ============================================================

-- ============================================================
-- 1. SYNC STATUS TO DB (OPTIONAL - for reports/analytics)
-- Call periodically to persist computed 'delayed' status to DB
-- This is optional since computed_status handles real-time display
-- ============================================================

CREATE OR REPLACE FUNCTION fn_sync_delayed_appointments()
RETURNS TABLE(updated_count INTEGER, appointments_updated INTEGER[]) AS $$
DECLARE
    affected_ids INTEGER[];
BEGIN
    -- Sync appointments that should be marked as delayed in DB
    -- Uses 5 minute tolerance (matching DELAY_TOLERANCE_MINUTES in Python)
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
-- 2. PREVENT INVALID STATUS TRANSITIONS
-- Only allow valid state transitions
-- ============================================================

CREATE OR REPLACE FUNCTION fn_validate_status_transition()
RETURNS TRIGGER AS $$
BEGIN
    -- Cannot revert from completed or canceled
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


-- ============================================================
-- 4. VISIT COMPLETION TRIGGER
-- Auto-completes visits after out_time is set
-- ============================================================

CREATE OR REPLACE FUNCTION fn_check_visit_completion()
RETURNS TRIGGER AS $$
BEGIN
    -- If out_time is being set and state is still 'unloading', mark as completed
    IF NEW.out_time IS NOT NULL 
       AND OLD.out_time IS NULL 
       AND NEW.state = 'unloading' THEN
        NEW.state := 'completed';
        
        -- Also update appointment status to completed
        UPDATE appointment 
        SET status = 'completed'
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

CREATE OR REPLACE FUNCTION fn_generate_arrival_id()
RETURNS TRIGGER AS $$
DECLARE
    new_id TEXT;
    seq_num INTEGER;
BEGIN
    IF COALESCE(NEW.arrival_id, '') = '' THEN
        -- Get next sequence number based on existing max
        SELECT COALESCE(
            MAX(CAST(SUBSTRING(arrival_id FROM 'PRT-([0-9]+)') AS INTEGER)),
            0
        ) + 1 INTO seq_num
        FROM appointment
        WHERE arrival_id LIKE 'PRT-%';
        
        -- Format as PRT-XXXX (4 digits, zero-padded)
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
-- 9. BOOKING CREATED_AT AUTO-SET
-- Sets created_at timestamp on booking creation if not provided
-- ============================================================

CREATE OR REPLACE FUNCTION fn_set_booking_created_at()
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
    EXECUTE FUNCTION fn_set_booking_created_at();


-- ============================================================
-- 10. WORKER CREATED_AT AUTO-SET
-- Sets created_at timestamp on worker creation if not provided
-- ============================================================

CREATE OR REPLACE FUNCTION fn_set_worker_created_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_at IS NULL THEN
        NEW.created_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_worker_created_at ON worker;
CREATE TRIGGER trg_worker_created_at
    BEFORE INSERT ON worker
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_worker_created_at();


-- ============================================================
-- 11. DRIVER CREATED_AT AUTO-SET
-- Sets created_at timestamp on driver creation if not provided
-- ============================================================

CREATE OR REPLACE FUNCTION fn_set_driver_created_at()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.created_at IS NULL THEN
        NEW.created_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_driver_created_at ON driver;
CREATE TRIGGER trg_driver_created_at
    BEFORE INSERT ON driver
    FOR EACH ROW
    EXECUTE FUNCTION fn_set_driver_created_at();


-- ============================================================
-- USAGE NOTES:
-- ============================================================
-- 
-- DELAYED STATUS:
-- The 'delayed' status is now computed dynamically in Python using
-- the Appointment.computed_status property. This provides real-time
-- status without relying on cron jobs or triggers.
--
-- For analytics/reporting, you can optionally call:
--   SELECT * FROM fn_sync_delayed_appointments();
-- This syncs the computed status to the DB for historical queries.
--
-- ARRIVAL ID:
-- Auto-generated as PRT-XXXX on appointment insert
--
-- VISIT COMPLETION:
-- Setting out_time on visit auto-completes both visit and appointment
--
-- ALERTS:
-- Automatically linked to shift history when created with visit_id
--
-- ============================================================

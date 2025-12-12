-- ============================================================
-- Triggers for Intelligent Logistics - Data Module
-- PostgreSQL functions and triggers for automatic status updates
-- ============================================================

-- ============================================================
-- 1. SCHEDULED STATUS UPDATE FUNCTION
-- Call this periodically via pg_cron, crontab, or application scheduler
-- Marks all in_transit appointments as 'delayed' when past their time
-- ============================================================

CREATE OR REPLACE FUNCTION fn_update_delayed_appointments()
RETURNS TABLE(updated_count INTEGER, appointments_updated INTEGER[]) AS $$
DECLARE
    affected_ids INTEGER[];
BEGIN
    -- Update appointments that are past their scheduled time + 15 min tolerance
    WITH updated AS (
        UPDATE appointment
        SET status = 'delayed'
        WHERE status = 'in_transit'
          AND scheduled_start_time IS NOT NULL
          AND scheduled_start_time + INTERVAL '15 minutes' < NOW()
        RETURNING id
    )
    SELECT ARRAY_AGG(id) INTO affected_ids FROM updated;
    
    RETURN QUERY SELECT 
        COALESCE(array_length(affected_ids, 1), 0),
        COALESCE(affected_ids, ARRAY[]::INTEGER[]);
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 2. TRIGGER ON UPDATE - Prevent reverting delayed back to in_transit
-- ============================================================

CREATE OR REPLACE FUNCTION fn_check_appointment_delay_on_update()
RETURNS TRIGGER AS $$
BEGIN
    -- If appointment is already delayed and time hasn't changed, keep it delayed
    IF OLD.status = 'delayed' 
       AND NEW.status = 'in_transit'
       AND NEW.scheduled_start_time IS NOT NULL
       AND NEW.scheduled_start_time + INTERVAL '15 minutes' < NOW() THEN
        NEW.status := 'delayed';
    END IF;
    
    -- Also check if currently in_transit should become delayed
    IF NEW.status = 'in_transit' 
       AND NEW.scheduled_start_time IS NOT NULL
       AND NEW.scheduled_start_time + INTERVAL '15 minutes' < NOW() THEN
        NEW.status := 'delayed';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_appointment_delay_check ON appointment;
CREATE TRIGGER trg_appointment_delay_check
    BEFORE UPDATE ON appointment
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_appointment_delay_on_update();


-- ============================================================
-- 3. ON INSERT - Check if new appointment should be delayed
-- ============================================================

CREATE OR REPLACE FUNCTION fn_check_appointment_delay_on_insert()
RETURNS TRIGGER AS $$
BEGIN
    -- If inserting an in_transit that's already past time, mark delayed
    IF NEW.status = 'in_transit' 
       AND NEW.scheduled_start_time IS NOT NULL
       AND NEW.scheduled_start_time + INTERVAL '15 minutes' < NOW() THEN
        NEW.status := 'delayed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_appointment_delay_insert ON appointment;
CREATE TRIGGER trg_appointment_delay_insert
    BEFORE INSERT ON appointment
    FOR EACH ROW
    EXECUTE FUNCTION fn_check_appointment_delay_on_insert();


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
-- USAGE NOTES:
-- ============================================================
-- To run the scheduled update (call every 5 minutes via cron):
--   SELECT * FROM fn_update_delayed_appointments();
--
-- Example with pg_cron (if installed):
--   SELECT cron.schedule('update-delayed-appointments', '*/5 * * * *', 
--     'SELECT fn_update_delayed_appointments()');
--
-- Or call from Python with APScheduler or similar
-- ============================================================

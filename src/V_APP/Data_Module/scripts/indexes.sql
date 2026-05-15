-- ============================================================
-- Database Indexes for Intelligent Logistics
-- PostgreSQL indexes to optimize query performance
-- Generated based on frontend and backend query patterns
-- ============================================================

-- ============================================================
-- 1. APPOINTMENT TABLE INDEXES (High Priority - Most Queries)
-- ============================================================

-- Index for filtering arrivals by entry gate (operator dashboard)
CREATE INDEX IF NOT EXISTS idx_appointment_gate_in_id 
ON appointment(gate_in_id);

-- Index for filtering by appointment status
CREATE INDEX IF NOT EXISTS idx_appointment_status 
ON appointment(status);

-- Index for filtering by scheduled date (functional index)
CREATE INDEX IF NOT EXISTS idx_appointment_scheduled_date 
ON appointment(DATE(scheduled_start_time));

-- Composite index for dashboard queries (gate + status + date)
CREATE INDEX IF NOT EXISTS idx_appointment_gate_status_date 
ON appointment(gate_in_id, status, DATE(scheduled_start_time));

-- Index for Decision Engine lookup by license plate
CREATE INDEX IF NOT EXISTS idx_appointment_truck_plate 
ON appointment(truck_license_plate);

-- Index for driver's appointments lookup
CREATE INDEX IF NOT EXISTS idx_appointment_driver 
ON appointment(driver_license);

-- Index for booking relationship
CREATE INDEX IF NOT EXISTS idx_appointment_booking 
ON appointment(booking_reference);

-- Index for terminal relationship
CREATE INDEX IF NOT EXISTS idx_appointment_terminal 
ON appointment(terminal_id);

-- Index for exit gate
CREATE INDEX IF NOT EXISTS idx_appointment_gate_out_id 
ON appointment(gate_out_id);


-- ============================================================
-- 2. VISIT TABLE INDEXES
-- ============================================================

-- Composite index for shift composite FK queries
CREATE INDEX IF NOT EXISTS idx_visit_shift_composite 
ON visit(shift_gate_id, shift_type, shift_date);

-- Index for delivery state filtering
CREATE INDEX IF NOT EXISTS idx_visit_state 
ON visit(state);

-- Index for entry time sorting/filtering
CREATE INDEX IF NOT EXISTS idx_visit_entry_time 
ON visit(entry_time);

-- Index for exit time filtering
CREATE INDEX IF NOT EXISTS idx_visit_out_time 
ON visit(out_time);


-- ============================================================
-- 3. SHIFT TABLE INDEXES
-- ============================================================

-- Index for operator's shifts lookup
CREATE INDEX IF NOT EXISTS idx_shift_operator 
ON shift(operator_num_worker);

-- Index for manager's shifts lookup
CREATE INDEX IF NOT EXISTS idx_shift_manager 
ON shift(manager_num_worker);

-- Composite index for current shift lookup (gate + date)
CREATE INDEX IF NOT EXISTS idx_shift_gate_date 
ON shift(gate_id, date);


-- ============================================================
-- 4. ALERT TABLE INDEXES
-- ============================================================

-- Index for alerts associated with a visit
CREATE INDEX IF NOT EXISTS idx_alert_visit_id 
ON alert(visit_id);

-- Index for filtering by alert type
CREATE INDEX IF NOT EXISTS idx_alert_type 
ON alert(type);

-- Index for recent alerts sorting
CREATE INDEX IF NOT EXISTS idx_alert_timestamp 
ON alert(timestamp);

-- Composite index for type + timestamp queries
CREATE INDEX IF NOT EXISTS idx_alert_type_timestamp 
ON alert(type, timestamp);


-- ============================================================
-- 5. WORKER/AUTHENTICATION INDEXES
-- ============================================================

-- Composite index for authentication (email + active)
CREATE INDEX IF NOT EXISTS idx_worker_email_active 
ON worker(email, active);

-- Index for active workers filtering
CREATE INDEX IF NOT EXISTS idx_worker_active 
ON worker(active);


-- ============================================================
-- 6. DRIVER INDEXES
-- ============================================================

-- Composite index for driver authentication
CREATE INDEX IF NOT EXISTS idx_driver_license_active 
ON driver(drivers_license, active);

-- Index for active drivers filtering
CREATE INDEX IF NOT EXISTS idx_driver_active 
ON driver(active);

-- Index for drivers by company
CREATE INDEX IF NOT EXISTS idx_driver_company 
ON driver(company_nif);


-- ============================================================
-- 7. BOOKING/CARGO INDEXES
-- ============================================================

-- Index for cargos by booking
CREATE INDEX IF NOT EXISTS idx_cargo_booking 
ON cargo(booking_reference);

-- Index for booking direction filtering
CREATE INDEX IF NOT EXISTS idx_booking_direction 
ON booking(direction);


-- ============================================================
-- 8. SHIFT ALERT HISTORY INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_shift_alert_history_alert
ON shift_alert_history(alert_id);

CREATE INDEX IF NOT EXISTS idx_shift_alert_history_shift
ON shift_alert_history(shift_gate_id, shift_type, shift_date);


-- ============================================================
-- 9. DRIVER VEHICLE INDEXES (BR-52)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_driver_vehicle_driver ON driver_vehicle(driver_license);
CREATE INDEX IF NOT EXISTS idx_driver_vehicle_truck  ON driver_vehicle(truck_license_plate);
CREATE INDEX IF NOT EXISTS idx_driver_vehicle_active ON driver_vehicle(driver_license)
    WHERE end_date IS NULL;


-- ============================================================
-- 10. PENDING REVIEWS INDEXES (PD-01)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_pending_reviews_status  ON pending_reviews(status) WHERE status = 'PENDING';
CREATE INDEX IF NOT EXISTS idx_pending_reviews_truck   ON pending_reviews(truck_id);
CREATE INDEX IF NOT EXISTS idx_pending_reviews_gate    ON pending_reviews(gate_id);
CREATE INDEX IF NOT EXISTS idx_pending_reviews_created ON pending_reviews(created_at);


-- ============================================================
-- 11. INBOX / OUTBOX WORKER POLLING INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_inbox_event_id   ON inbox_events(event_id);
CREATE INDEX IF NOT EXISTS idx_inbox_status_id  ON inbox_events(status, id)
    WHERE status IN ('RECEIVED', 'PROCESSING', 'FAILED');

CREATE INDEX IF NOT EXISTS idx_outbox_event_id    ON outbox_events(event_id);
CREATE INDEX IF NOT EXISTS idx_outbox_status_retry ON outbox_events(status, id)
    WHERE status IN ('PENDING', 'FAILED');
CREATE INDEX IF NOT EXISTS idx_outbox_next_retry  ON outbox_events(next_retry_at)
    WHERE status = 'FAILED' AND next_retry_at IS NOT NULL;


-- ============================================================
-- 12. COMPOSITE INDEXES — hot query paths (stress-test identified)
-- ============================================================

-- /arrivals/query/license-plate: plate + status + ORDER BY time in one scan
CREATE INDEX IF NOT EXISTS idx_appointment_plate_status_time
    ON appointment(truck_license_plate, status, scheduled_start_time DESC);

-- get_appointments_for_decision: timestamp range (.between) + status + gate
-- (the DATE functional index on gate_status_date does not help for timestamp ranges)
CREATE INDEX IF NOT EXISTS idx_appointment_gate_status_time
    ON appointment(gate_in_id, status, scheduled_start_time);

-- /drivers/claim: full WHERE (booking_reference, arrival_id, status) in one index scan
CREATE INDEX IF NOT EXISTS idx_appointment_claim
    ON appointment(booking_reference, arrival_id, status);

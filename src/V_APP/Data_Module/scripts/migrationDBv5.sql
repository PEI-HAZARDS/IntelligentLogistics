-- ============================================================
-- Migration v5 — CSV Appointments + RGPD Driver Decoupling
-- appointment.driver_license: NOT NULL → NULL
-- Allows appointments to be imported via CSV without a driver;
-- driver associates later via claim PIN (arrival_id + booking_reference).
-- ============================================================
-- Safe to re-run: idempotent (DO $$ ... EXCEPTION WHEN).
-- Apply AFTER migrationDBv4.sql.
-- ============================================================

BEGIN;

-- 1. Drop NOT NULL constraint from appointment.driver_license
--    Wrapped in a DO block so re-runs are safe even if already nullable.
DO $$
BEGIN
    ALTER TABLE appointment ALTER COLUMN driver_license DROP NOT NULL;
EXCEPTION
    WHEN others THEN
        -- Already nullable — nothing to do.
        NULL;
END $$;

COMMIT;

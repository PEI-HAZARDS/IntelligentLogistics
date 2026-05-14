-- Migration: Add 'unloading' to appointment_status enum
-- Date: 2026-03-21
-- Reversible: Yes (see rollback at bottom)
--
-- This adds 'unloading' as a valid appointment status between 'in_process' and 'completed'.
-- The transition path is: in_transit -> in_process -> unloading -> completed

-- Add the new enum value (idempotent — IF NOT EXISTS)
ALTER TYPE appointment_status ADD VALUE IF NOT EXISTS 'unloading' AFTER 'in_process';

-- Update the status validation trigger to enforce valid transitions
-- (Applied via triggers.sql — re-run triggers.sql after this migration)

-- Rollback:
-- PostgreSQL does not support removing enum values directly.
-- To rollback: ensure no rows use 'unloading' status, then recreate the enum type.
-- UPDATE appointment SET status = 'in_process' WHERE status = 'unloading';
-- (Full enum recreation would require table column drop/recreate — avoid in production)

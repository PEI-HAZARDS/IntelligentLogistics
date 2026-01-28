-- Migration: Add session management fields to driver table
-- Date: 2025-12-26
-- Purpose: OAuth 2.0 + JWT Authentication (planned: January 2025)
-- Description: Adds session_token, session_expires_at for JWT session management
--              and current_appointment_id for sequential delivery tracking

-- Add session token column with index for fast lookups
ALTER TABLE driver ADD COLUMN IF NOT EXISTS session_token VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_driver_session_token ON driver(session_token);

-- Add session expiration timestamp
ALTER TABLE driver ADD COLUMN IF NOT EXISTS session_expires_at TIMESTAMP;

-- Add current appointment tracking (for sequential delivery access)
ALTER TABLE driver ADD COLUMN IF NOT EXISTS current_appointment_id INTEGER;

-- Optional: Add foreign key constraint to appointment table
-- Note: Not adding FK to avoid issues with appointment deletion
-- ALTER TABLE driver ADD CONSTRAINT fk_driver_current_appointment 
--     FOREIGN KEY (current_appointment_id) REFERENCES appointment(id) ON DELETE SET NULL;

-- Verification query
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'driver' 
AND column_name IN ('session_token', 'session_expires_at', 'current_appointment_id');

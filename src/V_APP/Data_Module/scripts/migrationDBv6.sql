-- ============================================================
-- Migration v6 — Recurring shift templates
-- Adds `shift_template`: rules the shift scheduler expands into
-- concrete `shift` rows for upcoming dates (idempotent generation).
-- ============================================================
-- Safe to re-run: IF NOT EXISTS guards throughout.
-- Apply AFTER migrationDBv5.sql.
-- The `shifttype` enum is created by SQLAlchemy (Base.metadata.create_all);
-- this migration assumes it already exists (it backs `shift.shift_type`).
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS shift_template (
    id                  SERIAL PRIMARY KEY,
    gate_id             INTEGER   NOT NULL REFERENCES gate(id),
    shift_type          shifttype NOT NULL,
    -- 7-char '0'/'1' weekday mask, index 0 = Monday … 6 = Sunday.
    weekdays            VARCHAR(7) NOT NULL DEFAULT '1111100',
    operator_num_worker VARCHAR(20) REFERENCES operator(num_worker),
    manager_num_worker  VARCHAR(20) REFERENCES manager(num_worker),
    valid_from          DATE      NOT NULL DEFAULT CURRENT_DATE,
    valid_until         DATE,
    active              BOOLEAN   NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT now(),
    CONSTRAINT chk_shift_template_weekdays CHECK (weekdays ~ '^[01]{7}$'),
    CONSTRAINT uq_shift_template
        UNIQUE (gate_id, shift_type, operator_num_worker, valid_from)
);

-- Fast lookup of active templates during generation.
CREATE INDEX IF NOT EXISTS idx_shift_template_active
    ON shift_template (active, gate_id);

COMMIT;

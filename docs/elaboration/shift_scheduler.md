# Recurring Shift Scheduler

Lets managers define **recurring shift rules** once and have concrete `shift`
rows created automatically for upcoming dates, instead of adding repeating shifts
by hand.

## Model — `shift_template`

| Field | Meaning |
|-------|---------|
| `gate_id` | Gate the shift belongs to (must be active / `estado = 'Ativo'`). |
| `shift_type` | `MORNING` / `AFTERNOON` / `NIGHT`. |
| `weekdays` | 7-char `'0'/'1'` mask. Index **0 = Monday … 6 = Sunday** (matches `date.weekday()`). e.g. `1111100` = Mon–Fri. |
| `operator_num_worker` | Optional default operator (NULL → generated shift is unstaffed / `inactive`). |
| `manager_num_worker` | Optional supervising manager. |
| `valid_from` / `valid_until` | Validity window (`valid_until` NULL = open-ended). |
| `active` | When false the template is ignored by the generator. |

Created by `migrationDBv6.sql` (or `Base.metadata.create_all` on a fresh seed).

## Generation rules

`application/use_cases/shift_scheduler.py :: generate_shifts_from_templates(horizon_days)`:

- expands only **active** templates whose **gate is active**;
- produces a shift on date `d` only when `ShiftTemplate.covers(d)` (weekday mask
  ∧ validity window ∧ active);
- **idempotent** — never overwrites an existing `(gate, shift_type, date)` shift
  (relies on the `Shift` composite PK), so repeated/overlapping runs are safe;
- **no operator double-booking** — if the template's operator is already assigned
  another shift that day, the generated shift is left unstaffed for a manager to
  fill rather than creating a conflict.

PostgreSQL-only (shifts are not projected to Mongo); emits no domain events.

## Flow

```
ShiftTemplate (manager creates / seed)
        │   POST /workers/shifts/generate   ┌────────────────────────┐
        ├──────────────────────────────────▶│ generate_shifts_from_  │
        │                                   │ templates(horizon)     │
   shift-scheduler worker (daily) ─────────▶└──────────┬─────────────┘
                                                       ▼
                                              concrete `shift` rows
                                                       ▼
                              Manager ShiftsPage calendar + "Active Shifts" widget
```

## Operations

- **On-demand**: `POST /api/workers/shifts/generate?horizon_days=14` (manager role).
- **Automatic**: the `shift-scheduler` container (`scripts/shift_scheduler.py`)
  runs the generator on start and then every `SHIFT_SCHEDULER_INTERVAL_SECONDS`
  (default 86400 = daily), materialising `SHIFT_SCHEDULER_HORIZON_DAYS` (default 14)
  days ahead. Idempotency makes a missed or duplicate run harmless.
- **Demo**: `data_init_demo.py` seeds 4 templates and generates 3 weeks ahead so
  the calendar is populated immediately after seeding.

## Related

- Midnight-aware "active shift" resolution: `utils/shift_utils.py ::
  active_shift_window` (the NIGHT shift spanning 22:00–06:00 belongs to its start
  date) — used by `GET /workers/shifts/active` and the dashboard widget.

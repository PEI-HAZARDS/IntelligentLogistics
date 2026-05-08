#!/usr/bin/env python3
"""
PEI 2025 Demo data initializer — Porto de Aveiro.

Populates a rich dataset so the logistics manager dashboard has data on
first load: completed appointments with visits, historical days, alerts,
and multiple companies for per-company statistics.

Gate / camera assignment:
  Video1 plates → Gate 1 (Decision Engine / port entry)
  Video2 plates → Gate 2 (Infraction Engine / highway approach)

Plate lists are overridable via env vars:
  DEMO_VIDEO1_PLATES — JSON array of plate strings
  DEMO_VIDEO2_PLATES — JSON array of plate strings
  MAX_ARRIVALS       — cap on appointments per gate (default: all)

Run with:
    DATABASE_URL=postgresql://... python scripts/data_init_demo.py
"""

import json as _json
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from Data_Module.models.sql_models import (
        Alert, Appointment, Base, Booking, Cargo, Company, Dock, Driver,
        Gate, Manager, Operator, Shift, ShiftAlertHistory, ShiftType,
        Terminal, Truck, Visit, Worker,
    )
except Exception:
    try:
        from infrastructure.persistence.sql_models import (
            Alert, Appointment, Base, Booking, Cargo, Company, Dock, Driver,
            Gate, Manager, Operator, Shift, ShiftAlertHistory, ShiftType,
            Terminal, Truck, Visit, Worker,
        )
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ── Demo plate configuration (overridable via env vars) ──────────────────────
_DEFAULT_VIDEO1 = ["87AX60", "68BSH8", "PEI2025", "LN67OIZGB", "92BLN3", "82BTN5"]
_DEFAULT_VIDEO2 = ["321BI13", "GGAB425", "SLJP1523", "CA93896"]

VIDEO1_PLATES: list = _json.loads(
    os.environ.get("DEMO_VIDEO1_PLATES", _json.dumps(_DEFAULT_VIDEO1))
)
VIDEO2_PLATES: list = _json.loads(
    os.environ.get("DEMO_VIDEO2_PLATES", _json.dumps(_DEFAULT_VIDEO2))
)

_raw_max = os.environ.get("MAX_ARRIVALS", "")
MAX_ARRIVALS: int = (
    int(_raw_max) if _raw_max.isdigit() else max(len(VIDEO1_PLATES), len(VIDEO2_PLATES))
)

VIDEO1_PLATES = VIDEO1_PLATES[:MAX_ARRIVALS]
VIDEO2_PLATES = VIDEO2_PLATES[:MAX_ARRIVALS]

# ── Reference data ────────────────────────────────────────────────────────────

COMPANIES = [
    ("PT509123456", "Transportes Aveiro Lda", "+351 234 567 890"),
    ("PT509234567", "Iberian Logistics SA", "+351 234 678 901"),
    ("PT509345678", "EuroTrans Portugal", "+351 234 789 012"),
    ("ES-B12345678", "Transportes Garcia SL", "+34 91 234 5678"),
    ("DE123456789", "Schmidt Spedition GmbH", "+49 30 1234567"),
    ("FR12345678901", "Transports Dupont SARL", "+33 1 23 45 67 89"),
]

# (license, name, company_idx)
DRIVERS = [
    ("PT12345678", "Oscar Almeida", 0),
    ("PT23456789", "Sofia Rodrigues", 0),
    ("PT34567890", "Miguel Santos", 1),
    ("PT45678901", "Ana Ferreira", 1),
    ("PT56789012", "Bruno Costa", 2),
    ("ES87654321", "Carlos Garcia Lopez", 3),
    ("ES76543210", "Maria Fernandez", 3),
    ("DE11223344", "Hans Mueller", 4),
    ("FR99887766", "Pierre Dubois", 5),
    ("FR88776655", "Jean-Luc Martin", 5),
]

# Extra historical trucks (supplement the demo plates)
# (plate, brand, company_idx)
_BRAND_SCANIA = "Scania R500"
_BRAND_MAN = "MAN TGX"
_BRAND_MERCEDES = "Mercedes Actros"
_BRAND_DAF = "DAF XF"
_BRAND_VOLVO = "Volvo FH16"

EXTRA_TRUCKS = [
    ("AA00AA", _BRAND_SCANIA, 0),
    ("BB11BB", _BRAND_MAN, 1),
    ("CC22CC", _BRAND_MERCEDES, 2),
    ("DD33DD", _BRAND_DAF, 3),
    ("12AB34", _BRAND_VOLVO, 0),
    ("56CD78", _BRAND_SCANIA, 1),
    ("90EF12", _BRAND_MAN, 2),
    ("34GH56", _BRAND_MERCEDES, 0),
    ("78IJ90", _BRAND_DAF, 1),
    ("23LM45", _BRAND_VOLVO, 0),
    ("67NP89", _BRAND_SCANIA, 1),
    ("45ST67", _BRAND_VOLVO, 0),
    ("89UV01", _BRAND_SCANIA, 1),
    ("23WX45", _BRAND_MAN, 2),
]

# (desc, state, weight_kg, is_hazmat, un_code, kemler)
CARGO_TYPES = [
    ("Sulfuric acid (fuming)", "liquid", 22000, True, "1831", "X886"),
    ("Gasoline ADR", "liquid", 24000, True, "1203", "33"),
    ("Propane cylinders", "gaseous", 8000, True, "1978", "23"),
    ("Industrial chemicals", "liquid", 15000, True, "1830", "80"),
    ("Ammonium nitrate fert.", "solid", 22000, True, "1942", "50"),
    ("Ceramic tiles", "solid", 24000, False, None, None),
    ("Cork products", "solid", 8000, False, None, None),
    ("Paper pulp", "solid", 28000, False, None, None),
    ("Salt (Salinas Aveiro)", "solid", 26000, False, None, None),
    ("Fish (fresh catch)", "solid", 12000, False, None, None),
    ("Wine (Bairrada DOC)", "liquid", 18000, False, None, None),
    ("Timber (eucalyptus)", "solid", 30000, False, None, None),
    ("Auto parts", "solid", 16000, False, None, None),
    ("Construction steel", "solid", 28000, False, None, None),
    ("Olive oil (bulk)", "liquid", 20000, False, None, None),
    ("Cement bags", "solid", 25000, False, None, None),
    ("Plastic granules", "solid", 15000, False, None, None),
    ("Machinery parts", "solid", 12000, False, None, None),
    ("Canned fish", "solid", 8000, False, None, None),
    ("General cargo", "solid", 10000, False, None, None),
]

_ALERT_DESCS = {
    "safety": "Hazardous cargo safety check triggered",
    "operational": "Dock assignment delay — manual reassignment needed",
    "problem": "Weight discrepancy detected — cargo exceeds declared weight",
    "generic": "Documentation check — CMR waybill verified",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_booking(db: Session, ref: str, direction: str = "inbound") -> Booking:
    bk = Booking(reference=ref, direction=direction)
    db.add(bk)
    db.flush()
    return bk


def _make_cargo(db: Session, bk_ref: str, cargo_def: tuple) -> Cargo:
    desc, st, weight, is_hazmat, un, kemler = cargo_def
    label = (
        f"{desc} [UN:{un}, Kemler:{kemler}]" if is_hazmat else desc
    )
    c = Cargo(booking_reference=bk_ref, quantity=Decimal(str(weight)), state=st, description=label)
    db.add(c)
    db.flush()
    return c


def _make_appointment(
    db: Session, bk_ref, driver, truck, terminal, gate_in, gate_out,
    sched_time, status, notes, expected_duration=45, highway_infraction=False,
) -> Appointment:
    appt = Appointment(
        booking_reference=bk_ref,
        driver_license=driver.drivers_license,
        truck_license_plate=truck.license_plate,
        terminal_id=terminal.id,
        gate_in_id=gate_in.id,
        gate_out_id=gate_out.id if status == "completed" else None,
        scheduled_start_time=sched_time,
        expected_duration=expected_duration,
        status=status,
        notes=notes,
        highway_infraction=highway_infraction,
    )
    db.add(appt)
    db.flush()
    return appt


def _make_visit(db: Session, appt, shift, entry_time, duration_min=None) -> Visit:
    v = Visit(
        appointment_id=appt.id,
        shift_gate_id=shift.gate_id,
        shift_type=shift.shift_type,
        shift_date=shift.date,
        entry_time=entry_time,
        out_time=entry_time + timedelta(minutes=duration_min) if duration_min else None,
        state="completed" if duration_min else "unloading",
    )
    db.add(v)
    db.flush()
    return v


def _make_alert(db: Session, visit, appt, shift, timestamp, alert_type) -> Alert:
    a = Alert(
        visit_id=visit.appointment_id,
        appointment_id=appt.id,
        timestamp=timestamp,
        type=alert_type,
        description=f"{_ALERT_DESCS.get(alert_type, 'Alert')} — {appt.truck_license_plate}",
    )
    db.add(a)
    db.flush()
    db.add(ShiftAlertHistory(
        shift_gate_id=shift.gate_id,
        shift_type=shift.shift_type,
        shift_date=shift.date,
        alert_id=a.id,
    ))
    db.flush()
    return a


def _generate_historical_day(
    db, day_date, trucks, drivers, terminal, gate_in, gate_out,
    shifts_morning, shifts_afternoon, num_appts, ref_prefix
):
    """Generate a full completed day for volume / statistics data."""
    for h in range(num_appts):
        ref = f"{ref_prefix}-{day_date.strftime('%Y%m%d')}-{h+1:04d}"
        bk = _make_booking(db, ref, "inbound" if h % 4 != 0 else "outbound")

        cidx = (h + 5) % len(CARGO_TYPES)
        _make_cargo(db, bk.reference, CARGO_TYPES[cidx])

        hour_offset = random.choice([7, 8, 8, 9, 9, 10, 10, 11, 12, 13, 14, 14, 15, 16, 17])
        sched = datetime.combine(day_date, time(hour_offset, random.randint(0, 55)))

        tidx = h % len(trucks)
        didx = h % len(drivers)
        dur = random.choice([20, 25, 30, 35, 38, 42, 45, 50, 55, 60, 70, 80])
        delay = random.choice([0, 0, 0, 5, 10, 15, 20, 30])

        appt = Appointment(
            booking_reference=bk.reference,
            driver_license=drivers[didx].drivers_license,
            truck_license_plate=trucks[tidx].license_plate,
            terminal_id=terminal.id,
            gate_in_id=gate_in.id,
            gate_out_id=gate_out.id,
            scheduled_start_time=sched,
            expected_duration=45,
            status="completed",
            notes=f"Historical — {CARGO_TYPES[cidx][0]}",
        )
        db.add(appt)
        db.flush()

        entry = sched + timedelta(minutes=delay + random.randint(1, 5))
        shift = shifts_morning if entry.hour < 14 else shifts_afternoon
        v = _make_visit(db, appt, shift, entry, dur)

        if random.random() < 0.25:
            at = random.choice(["safety", "operational", "problem", "generic"])
            _make_alert(db, v, appt, shift, entry + timedelta(minutes=random.randint(2, 15)), at)


# ── Main seeder ───────────────────────────────────────────────────────────────

def init_demo_data(db: Session):
    print("=" * 60)
    print("  PEI 2025 — PORTO DE AVEIRO DEMO DATA INITIALIZER")
    print("=" * 60)

    if db.query(Worker).first():
        print("\n  Data already exists — skipping initialization.")
        print("  To reset: docker compose down -v && docker compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ── Workers ──────────────────────────────────────────────────────────
        print("\n  Creating workers...")
        manager_w = Worker(
            num_worker="MGR001", name="João Silva",
            email="manager@example.pt", phone="+351 910 000 001",
            password_hash=_hash("password123"), active=True,
        )
        manager2_w = Worker(
            num_worker="MGR002", name="Teresa Lopes",
            email="teresa.lopes@portodeaveiro.pt", phone="+351 910 000 004",
            password_hash=_hash("password123"), active=True,
        )
        operator_w = Worker(
            num_worker="OPR001", name="Maria Santos",
            email="worker@porto.pt", phone="+351 910 000 002",
            password_hash=_hash("password123"), active=True,
        )
        operator2_w = Worker(
            num_worker="OPR002", name="António Ferreira",
            email="antonio.ferreira@portodeaveiro.pt", phone="+351 910 000 003",
            password_hash=_hash("password123"), active=True,
        )
        db.add_all([manager_w, manager2_w, operator_w, operator2_w])
        db.flush()
        db.add_all([
            Manager(num_worker="MGR001", access_level="admin"),
            Manager(num_worker="MGR002", access_level="basic"),
            Operator(num_worker="OPR001"),
            Operator(num_worker="OPR002"),
        ])
        db.flush()

        # ── Companies ─────────────────────────────────────────────────────────
        print("  Creating companies...")
        companies = []
        for nif, name, contact in COMPANIES:
            c = Company(nif=nif, name=name, contact=contact)
            companies.append(c)
        db.add_all(companies)
        db.flush()

        # ── Drivers ───────────────────────────────────────────────────────────
        print("  Creating drivers...")
        drivers = []
        for license_num, name, cidx in DRIVERS:
            d = Driver(
                drivers_license=license_num, name=name,
                company_nif=companies[cidx].nif,
                password_hash=_hash("driver123"), active=True,
            )
            drivers.append(d)
        db.add_all(drivers)
        db.flush()
        main_driver = drivers[0]  # Oscar Almeida — demo star

        # ── Trucks ────────────────────────────────────────────────────────────
        all_demo_plates = VIDEO1_PLATES + VIDEO2_PLATES
        print(f"  Creating trucks: {len(all_demo_plates)} demo + {len(EXTRA_TRUCKS)} historical...")
        trucks_by_plate: dict = {}
        all_trucks_list = []

        for i, plate in enumerate(all_demo_plates):
            t = Truck(
                license_plate=plate,
                brand=["Volvo", "Scania", "MAN", "Mercedes", "DAF"][i % 5],
                company_nif=companies[i % len(companies)].nif,
            )
            db.add(t)
            trucks_by_plate[plate] = t
            all_trucks_list.append(t)
        db.flush()

        for plate, brand, cidx in EXTRA_TRUCKS:
            if plate not in trucks_by_plate:
                t = Truck(license_plate=plate, brand=brand, company_nif=companies[cidx].nif)
                db.add(t)
                trucks_by_plate[plate] = t
                all_trucks_list.append(t)
        db.flush()

        # Extra trucks (not in demo plate lists) for historical variety
        hist_trucks = [t for t in all_trucks_list if t.license_plate not in set(all_demo_plates)]

        # ── Terminals (real Porto de Aveiro) ──────────────────────────────────
        print("  Creating terminals (Terminal Norte, Granéis Sólidos, Granéis Líquidos)...")
        terminal_norte = Terminal(
            name="Terminal Norte - Porto de Aveiro",
            latitude=Decimal("40.6520"), longitude=Decimal("-8.7430"),
            hazmat_approved=False,
        )
        terminal_solidos = Terminal(
            name="Terminal de Granéis Sólidos - Porto de Aveiro",
            latitude=Decimal("40.6446"), longitude=Decimal("-8.7490"),
            hazmat_approved=False,
        )
        terminal_liquidos = Terminal(
            name="Terminal de Granéis Líquidos - Porto de Aveiro",
            latitude=Decimal("40.6360"), longitude=Decimal("-8.7520"),
            hazmat_approved=True,
        )
        db.add_all([terminal_norte, terminal_solidos, terminal_liquidos])
        db.flush()

        # ── Docks ─────────────────────────────────────────────────────────────
        print("  Creating docks...")
        docks = [
            Dock(terminal_id=terminal_norte.id, bay_number="TN-CAIS-1",
                 latitude=Decimal("40.6522"), longitude=Decimal("-8.7428"), current_usage="operational"),
            Dock(terminal_id=terminal_norte.id, bay_number="TN-CAIS-2",
                 latitude=Decimal("40.6524"), longitude=Decimal("-8.7426"), current_usage="operational"),
            Dock(terminal_id=terminal_norte.id, bay_number="TN-RORO",
                 latitude=Decimal("40.6518"), longitude=Decimal("-8.7432"), current_usage="operational"),
            Dock(terminal_id=terminal_solidos.id, bay_number="TGS-CAIS-A",
                 latitude=Decimal("40.6448"), longitude=Decimal("-8.7492"), current_usage="operational"),
            Dock(terminal_id=terminal_solidos.id, bay_number="TGS-CAIS-B",
                 latitude=Decimal("40.6450"), longitude=Decimal("-8.7494"), current_usage="operational"),
            Dock(terminal_id=terminal_solidos.id, bay_number="TGS-SILO",
                 latitude=Decimal("40.6444"), longitude=Decimal("-8.7488"), current_usage="operational"),
            Dock(terminal_id=terminal_liquidos.id, bay_number="TGL-CAIS-1",
                 latitude=Decimal("40.6362"), longitude=Decimal("-8.7522"), current_usage="operational"),
            Dock(terminal_id=terminal_liquidos.id, bay_number="TGL-CAIS-2",
                 latitude=Decimal("40.6364"), longitude=Decimal("-8.7524"), current_usage="operational"),
            Dock(terminal_id=terminal_liquidos.id, bay_number="TGL-HAZMAT",
                 latitude=Decimal("40.6358"), longitude=Decimal("-8.7518"), current_usage="operational"),
        ]
        db.add_all(docks)
        db.flush()

        # ── Gates ─────────────────────────────────────────────────────────────
        print("  Creating gates...")
        gate_entry = Gate(
            label="Portaria 1 — Entrada Principal",
            latitude=Decimal("40.6460"), longitude=Decimal("-8.7470"),
        )
        gate_out = Gate(
            label="Portaria 2 — Saída",
            latitude=Decimal("40.6430"), longitude=Decimal("-8.7440"),
        )
        gate_highway = Gate(
            label="Gate 2 — Abordagem A25",
            latitude=Decimal("40.6500"), longitude=Decimal("-8.7500"),
        )
        db.add_all([gate_entry, gate_out, gate_highway])
        db.flush()

        # ── Shifts (today + 5 historical days) ───────────────────────────────
        print("  Creating shifts (today + 5 historical days)...")
        shift_map: dict = {}
        operators_cycle = ["OPR001", "OPR002", "OPR001", "OPR002"]
        for day_offset in range(6):
            d = today - timedelta(days=day_offset)
            configs = [
                (gate_entry.id,  ShiftType.MORNING,   d, operators_cycle[0], "MGR001"),
                (gate_entry.id,  ShiftType.AFTERNOON, d, operators_cycle[1], "MGR001"),
                (gate_entry.id,  ShiftType.NIGHT,     d, operators_cycle[2], "MGR002"),
                (gate_highway.id, ShiftType.MORNING,  d, operators_cycle[3], "MGR002"),
                (gate_highway.id, ShiftType.AFTERNOON, d, operators_cycle[0], "MGR002"),
            ]
            for gid, stype, sdate, opr, mgr in configs:
                s = Shift(gate_id=gid, shift_type=stype, date=sdate,
                          operator_num_worker=opr, manager_num_worker=mgr)
                db.add(s)
                shift_map[(gid, stype, sdate)] = s
        db.flush()

        morning_shift   = shift_map[(gate_entry.id, ShiftType.MORNING,   today)]
        afternoon_shift = shift_map[(gate_entry.id, ShiftType.AFTERNOON, today)]
        night_shift     = shift_map[(gate_entry.id, ShiftType.NIGHT,     today)]

        ref_counter = [0]

        def _next_ref(prefix="AVR"):
            ref_counter[0] += 1
            return f"{prefix}-{today.strftime('%Y%m%d')}-{ref_counter[0]:04d}"

        def _shift_for(dt: datetime):
            h = dt.hour
            if 6 <= h < 14:
                return morning_shift
            if 14 <= h < 22:
                return afternoon_shift
            return night_shift

        def _auto_status(sched_dt: datetime, dur_min) -> str:
            """Compute realistic appointment status relative to now."""
            elapsed = (now - sched_dt).total_seconds() / 60
            if elapsed < -5:
                return "scheduled"
            if dur_min is None or elapsed < dur_min:
                return "in_process"
            return "completed"

        def _sched(h: int, m: int = 0) -> datetime:
            """Absolute time today; if in the future keep as-is (scheduled)."""
            return datetime.combine(today, time(h, m))

        # ── Video1 appointments — Gate 1, spread across all 3 shifts ─────────
        # Times chosen so each shift has ≥1 demo plate regardless of script time.
        print(f"\n  Creating {len(VIDEO1_PLATES)} Video1 appointments (Gate 1)...")
        _VIDEO1_TIMES = [
            time(7, 30),   # morning
            time(9, 0),    # morning
            time(11, 30),  # morning
            time(14, 30),  # afternoon
            time(16, 0),   # afternoon
            time(22, 15),  # night
        ]
        # Plates at index 1 and 4 get highway infraction at Gate 1
        _VIDEO1_INFRACTION_INDICES = {1, 4}
        for i, plate in enumerate(VIDEO1_PLATES):
            cargo_def = CARGO_TYPES[i % len(CARGO_TYPES)]
            desc, _, _, is_hazmat, un_code, kemler = cargo_def
            bk = _make_booking(db, _next_ref())
            _make_cargo(db, bk.reference, cargo_def)
            slot_time = _VIDEO1_TIMES[i % len(_VIDEO1_TIMES)]
            sched_time = datetime.combine(today, slot_time)
            status = _auto_status(sched_time, 45)
            has_infraction = i in _VIDEO1_INFRACTION_INDICES
            # Infraction only makes sense once the truck has been detected on the road
            detected_infraction = has_infraction and status != "scheduled"
            notes = (
                f"HAZMAT: {desc} [UN:{un_code}, Kemler:{kemler}]"
                if is_hazmat else f"Cargo: {desc}"
            )
            if detected_infraction:
                notes += " — INFRAÇÃO DETECTADA A25"
            appt = _make_appointment(
                db, bk.reference, main_driver, trucks_by_plate[plate],
                terminal_liquidos if is_hazmat else terminal_norte,
                gate_entry, gate_out, sched_time, status, notes,
                highway_infraction=detected_infraction,
            )
            if status in ("completed", "in_process"):
                entry = sched_time + timedelta(minutes=random.randint(2, 8))
                dur = 45 if status == "completed" else None
                v = _make_visit(db, appt, _shift_for(entry), entry, dur)

        # ── Video2 appointments — Gate highway, spread across all 3 shifts ────
        print(f"  Creating {len(VIDEO2_PLATES)} Video2 appointments (Gate 2 / highway)...")
        _VIDEO2_TIMES = [
            time(8, 0),    # morning
            time(15, 30),  # afternoon
            time(18, 0),   # afternoon
            time(22, 45),  # night
        ]
        for i, plate in enumerate(VIDEO2_PLATES):
            cargo_def = CARGO_TYPES[i % len(CARGO_TYPES)]
            desc, _, _, is_hazmat, un_code, kemler = cargo_def
            bk = _make_booking(db, _next_ref("HWY"))
            _make_cargo(db, bk.reference, cargo_def)
            slot_time = _VIDEO2_TIMES[i % len(_VIDEO2_TIMES)]
            sched_time = datetime.combine(today, slot_time)
            status = _auto_status(sched_time, 40)
            # Hazmat trucks on the highway gate are an infraction only once detected
            highway_infraction = is_hazmat and status != "scheduled"
            notes = f"Highway — {'HAZMAT: ' + desc if is_hazmat else 'Cargo: ' + desc}"
            if highway_infraction:
                notes += " — INFRAÇÃO DETECTADA A25"
            appt = _make_appointment(
                db, bk.reference, drivers[i % len(drivers)], trucks_by_plate[plate],
                terminal_liquidos if is_hazmat else terminal_solidos,
                gate_highway, gate_out, sched_time, status, notes,
                highway_infraction=highway_infraction,
            )
            if status in ("completed", "in_process"):
                entry = sched_time + timedelta(minutes=random.randint(2, 8))
                dur = 40 if status == "completed" else None
                v = _make_visit(db, appt, _shift_for(entry), entry, dur)

        # ── Bonus appointments distributed across all 3 shifts ────────────────
        # Each entry: (truck_idx, cargo_idx, hour, min, dur_min|None, alert_type)
        # Status is computed dynamically so the demo is always realistic.
        print("  Creating bonus today appointments distributed across shifts...")
        bonus_configs = [
            # Morning shift (6–14h)
            (0,  1,   6, 45,  35,   "operational"),
            (1,  6,   7, 30,  28,   None),
            (2,  7,   8, 10,  42,   None),
            (3,  8,   8, 50,  31,   "safety"),
            (4,  9,  10, 30,  None, None),        # in_process if still before 12:00
            (5,  5,  11,  0,  55,   "problem"),
            (6, 10,  12, 15,  38,   None),
            (7, 11,  13,  0,  60,   None),
            # Afternoon shift (14–22h)
            (8, 12,  14, 30,  70,   None),
            (9, 13,  15, 45,  45,   "generic"),
            (10, 14, 16,  0,  30,   None),
            (11, 15, 17, 30, None,  "operational"),  # in_process if still afternoon
            (12, 16, 18,  0,  85,   None),
            (13, 17, 19, 30,  48,   None),
            # Night shift (22–6h)
            (0,  18, 22, 30,  40,   None),
            (1,  19, 23,  0,  35,   None),
        ]

        for bidx, (tidx, cidx, bh, bm, dur, alert_t) in enumerate(bonus_configs):
            truck = hist_trucks[tidx % len(hist_trucks)]
            cargo_def = CARGO_TYPES[cidx % len(CARGO_TYPES)]
            desc, _, _, is_hazmat, _, _ = cargo_def

            bk = _make_booking(db, _next_ref("BON"), "inbound" if bidx % 3 != 0 else "outbound")
            _make_cargo(db, bk.reference, cargo_def)

            sched_time = _sched(bh, bm)
            status = _auto_status(sched_time, dur)
            appt_terminal = terminal_liquidos if is_hazmat else terminal_norte
            appt = _make_appointment(
                db, bk.reference, drivers[bidx % len(drivers)], truck,
                appt_terminal, gate_entry, gate_out, sched_time, status,
                f"Cargo: {desc}",
            )
            if status in ("completed", "in_process"):
                entry = sched_time + timedelta(minutes=random.randint(2, 10))
                visit_dur = dur if status == "completed" else None
                v = _make_visit(db, appt, _shift_for(entry), entry, visit_dur)
                if alert_t:
                    _make_alert(db, v, appt, _shift_for(entry),
                                entry + timedelta(minutes=random.randint(3, 12)), alert_t)

        # ── Peak hour cluster (9–10 AM) for congestion simulation ─────────────
        peak_configs = [
            (9, 10, 50), (9, 25, 42), (9, 40, 38), (9, 55, 55), (10, 5, 35), (10, 20, 45),
        ]
        for ph, pm, dur in peak_configs:
            tidx = ref_counter[0] % len(hist_trucks)
            truck = hist_trucks[tidx]
            cargo_def = CARGO_TYPES[ref_counter[0] % len(CARGO_TYPES)]
            bk = _make_booking(db, _next_ref("PEAK"))
            _make_cargo(db, bk.reference, cargo_def)
            sched = _sched(ph, pm)
            status = _auto_status(sched, dur)
            appt = _make_appointment(
                db, bk.reference, drivers[ref_counter[0] % len(drivers)], truck,
                terminal_norte, gate_entry, gate_out, sched, status,
                f"Peak-hour — {cargo_def[0]}",
            )
            if status in ("completed", "in_process"):
                entry = sched + timedelta(minutes=random.randint(2, 8))
                visit_dur = dur if status == "completed" else None
                v = _make_visit(db, appt, _shift_for(entry), entry, visit_dur)
                if random.random() < 0.3:
                    at = random.choice(["operational", "generic"])
                    _make_alert(db, v, appt, _shift_for(entry), entry + timedelta(minutes=5), at)

        # ── Historical data (5 previous days) ─────────────────────────────────
        print("  Creating 5 days of historical data...")
        historical_appts_per_day = [12, 10, 14, 11, 13]
        hist_terminals_cycle = [
            terminal_norte, terminal_solidos, terminal_liquidos,
            terminal_norte, terminal_solidos,
        ]

        for day_offset in range(1, 6):
            d = today - timedelta(days=day_offset)
            sm = shift_map[(gate_entry.id, ShiftType.MORNING, d)]
            sa = shift_map[(gate_entry.id, ShiftType.AFTERNOON, d)]
            _generate_historical_day(
                db, d, hist_trucks, drivers,
                hist_terminals_cycle[day_offset - 1],
                gate_entry, gate_out, sm, sa,
                historical_appts_per_day[day_offset - 1],
                f"HIST-D{day_offset}",
            )
            print(f"    Day -{day_offset} ({d}): {historical_appts_per_day[day_offset-1]} appointments")

        # ── Commit ────────────────────────────────────────────────────────────
        print("\n  Saving to database...")
        db.commit()

        # ── Summary ───────────────────────────────────────────────────────────
        total_hist = sum(historical_appts_per_day)
        print("\n" + "=" * 70)
        print("  DATABASE INITIALIZED — PEI 2025 PORTO DE AVEIRO DEMO")
        print("=" * 70)

        print("""
┌─────────────────────────────────────────────────────────────────────┐
│                        LOGIN CREDENTIALS                             │
├─────────────────────────────────────────────────────────────────────┤
│  WEB PORTAL:                                                         │
│    worker@porto.pt            │ password123  │ Operator              │
│    manager@example.pt         │ password123  │ Manager               │
│    teresa.lopes@portodeaveiro.pt │ password123 │ Manager             │
├─────────────────────────────────────────────────────────────────────┤
│  MOBILE APP (Drivers):                                               │
│    PT12345678  Oscar Almeida      │ driver123                       │
│    PT23456789  Sofia Rodrigues    │ driver123                       │
│    ES87654321  Carlos Garcia      │ driver123                       │
│    DE11223344  Hans Mueller       │ driver123                       │
│    FR99887766  Pierre Dubois      │ driver123                       │
└─────────────────────────────────────────────────────────────────────┘
""")

        print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│  VIDEO1 → Gate 1:  {len(VIDEO1_PLATES)} plates  (07:30 · 09:00 · 11:30 · 14:30 · 16:00 · 22:15) │
│  VIDEO2 → Gate 2:  {len(VIDEO2_PLATES)} plates  (08:00 · 15:30 · 18:00 · 22:45)              │
│  Bonus: {len(bonus_configs)} appts across Morning/Afternoon/Night + {len(peak_configs)} peak-hour │
│  Historical appointments (5 days):  {total_hist}                       │
│  Companies: {len(COMPANIES)} │ Drivers: {len(DRIVERS)} │ Trucks: {len(all_trucks_list)} (demo+hist)              │
├─────────────────────────────────────────────────────────────────────┤
│  Status computed dynamically — always valid for any run date/time    │
├─────────────────────────────────────────────────────────────────────┤
│  TERMINALS (Porto de Aveiro real coordinates):                       │
│    Terminal Norte           (40.6520N, 8.7430W) — general cargo     │
│    Terminal Granéis Sólidos (40.6446N, 8.7490W) — bulk solids      │
│    Terminal Granéis Líquidos (40.6360N, 8.7520W) — HAZMAT liquid   │
└─────────────────────────────────────────────────────────────────────┘
""")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        db.rollback()
        raise


def _sync_to_keycloak(db) -> None:
    """
    Provision Keycloak users for all active workers and drivers.

    Uses the SQLAlchemy session so EncryptedString / SearchableEncryptedString
    columns (Worker.email, Worker.phone) are decrypted automatically.
    No-op when KEYCLOAK_URL or KC_ADMIN_PASSWORD are absent.
    """
    kc_url = os.getenv("KEYCLOAK_URL", "")
    kc_admin_pw = os.getenv("KC_ADMIN_PASSWORD", "")
    if not kc_url or not kc_admin_pw:
        print("\n  [KC-SYNC] KEYCLOAK_URL / KC_ADMIN_PASSWORD not set — skipping."
              "\n  Run 'docker-compose run --rm keycloak-sync' manually after seeding.")
        return

    try:
        import httpx as _httpx
    except ImportError:
        print("\n  [KC-SYNC] httpx not installed — skipping Keycloak sync.")
        return

    kc_realm = os.getenv("KEYCLOAK_REALM", "intelligent-logistics")
    kc_admin_user = os.getenv("KC_ADMIN_USER", "admin")
    worker_pw = os.getenv("DEFAULT_WORKER_PASSWORD", "password123")
    driver_pw = os.getenv("DEFAULT_DRIVER_PASSWORD", "driver123")

    print(f"\n  [KC-SYNC] Syncing users to {kc_url} realm '{kc_realm}'...")

    try:
        r = _httpx.post(
            f"{kc_url}/realms/master/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli",
                  "username": kc_admin_user, "password": kc_admin_pw},
            timeout=15.0,
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    except Exception as exc:
        print(f"\n  [KC-SYNC] Cannot reach Keycloak ({exc}) — skipping sync.")
        return

    admin_base = f"{kc_url}/admin/realms/{kc_realm}"
    headers = {"Authorization": f"Bearer {token}"}
    synced = 0

    def _assign_realm_roles(user_id: str, role_names: list) -> None:
        r2 = _httpx.get(f"{admin_base}/roles", headers=headers, timeout=10.0)
        role_map = {ro["name"]: ro for ro in r2.json()}
        roles = [role_map[rn] for rn in role_names if rn in role_map]
        if roles:
            _httpx.post(f"{admin_base}/users/{user_id}/role-mappings/realm",
                        json=roles, headers=headers, timeout=10.0)

    def _upsert(username: str, password: str, email: str | None = None,
                first_name: str | None = None, realm_roles: list | None = None) -> None:
        nonlocal synced
        body: dict = {"username": username, "enabled": True, "emailVerified": True}
        if email:
            body["email"] = email
        if first_name:
            body["firstName"] = first_name

        r2 = _httpx.post(f"{admin_base}/users", json=body, headers=headers, timeout=10.0)
        if r2.status_code == 409:
            return  # already exists — idempotent

        if r2.status_code not in (200, 201):
            print(f"  [KC-SYNC] Failed to create '{username}': {r2.status_code} {r2.text[:80]}")
            return

        r3 = _httpx.get(f"{admin_base}/users", params={"username": username, "exact": "true"},
                        headers=headers, timeout=10.0)
        users = r3.json()
        if not users:
            return
        user_id = users[0]["id"]

        _httpx.put(f"{admin_base}/users/{user_id}/reset-password",
                   json={"type": "password", "value": password, "temporary": False},
                   headers=headers, timeout=10.0)

        if realm_roles:
            _assign_realm_roles(user_id, realm_roles)

        synced += 1

    # Workers — SQLAlchemy decrypts Worker.email (SearchableEncryptedString) transparently
    for w in db.query(Worker).filter_by(active=True).all():
        role = "manager" if w.manager else "operator"
        _upsert(w.email, worker_pw, email=w.email, first_name=w.name, realm_roles=[role])

    # Drivers — drivers_license is plaintext (PK, not encrypted)
    for d in db.query(Driver).filter_by(active=True).all():
        _upsert(d.drivers_license, driver_pw, first_name=d.name, realm_roles=["driver"])

    print(f"  [KC-SYNC] Done — {synced} user(s) provisioned in Keycloak.")


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_demo_data(db)
        _sync_to_keycloak(db)
    finally:
        db.close()


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    print(f"\n  Connecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)

#!/usr/bin/env python3
"""
PEI 2025 Demo data initializer — Porto de Aveiro.

Populates a rich dataset:
  - 12 months of completed historical appointments (sustainability CO₂ trend)
  - Today: 87AX60 in_transit (only), mix of scheduled/in_process/completed/canceled
  - Multiple companies, terminals, and drivers for per-company statistics

Gate / camera assignment:
  Video1 plates → Gate 1 (Decision Engine / port entry)
  Video2 plates → Gate 2 (Infraction Engine / highway approach)

Run with:
    DATABASE_URL=postgresql://... python scripts/data_init_demo.py
    # or via the shared entry point:
    DATABASE_URL=postgresql://... python scripts/data_init_base.py --mode demo
"""

import json as _json
import os
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from Data_Module.models.sql_models import (
        Alert, Appointment, Booking, Cargo, Company, Dock, Driver,
        Gate, Manager, Operator, Shift, ShiftAlertHistory, ShiftType,
        Terminal, Truck, Visit, Worker,
    )
except Exception:
    try:
        from infrastructure.persistence.sql_models import (
            Alert, Appointment, Booking, Cargo, Company, Dock, Driver,
            Gate, Manager, Operator, Shift, ShiftAlertHistory, ShiftType,
            Terminal, Truck, Visit, Worker,
        )
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)

from data_init_base import _hash  # noqa: E402


# ── Plate configuration ──────────────────────────────────────────────────────
_DEFAULT_VIDEO1 = ["87AX60", "68BSH8", "PEI2025", "LN67OIZGB", "92BLN3", "82BTN5"]
_DEFAULT_VIDEO2 = ["321BI13", "GGAB425", "SLJP1523", "CA93896"]

VIDEO1_PLATES: list = _json.loads(
    os.environ.get("DEMO_VIDEO1_PLATES", _json.dumps(_DEFAULT_VIDEO1))
)
VIDEO2_PLATES: list = _json.loads(
    os.environ.get("DEMO_VIDEO2_PLATES", _json.dumps(_DEFAULT_VIDEO2))
)

# ── Reference data ────────────────────────────────────────────────────────────

COMPANIES = [
    ("PT509123456", "Transportes Aveiro Lda",    "+351 234 567 890"),
    ("PT509234567", "Iberian Logistics SA",       "+351 234 678 901"),
    ("PT509345678", "EuroTrans Portugal",         "+351 234 789 012"),
    ("ES-B12345678", "Transportes Garcia SL",     "+34 91 234 5678"),
    ("DE123456789",  "Schmidt Spedition GmbH",    "+49 30 1234567"),
    ("FR12345678901","Transports Dupont SARL",    "+33 1 23 45 67 89"),
]

DRIVERS = [
    ("PT12345678", "Oscar Almeida",       0),
    ("PT23456789", "Sofia Rodrigues",     0),
    ("PT34567890", "Miguel Santos",       1),
    ("PT45678901", "Ana Ferreira",        1),
    ("PT56789012", "Bruno Costa",         2),
    ("ES87654321", "Carlos Garcia Lopez", 3),
    ("ES76543210", "Maria Fernandez",     3),
    ("DE11223344", "Hans Mueller",        4),
    ("FR99887766", "Pierre Dubois",       5),
    ("FR88776655", "Jean-Luc Martin",     5),
]

_BRAND_SCANIA   = "Scania R500"
_BRAND_MAN      = "MAN TGX"
_BRAND_MERCEDES = "Mercedes Actros"
_BRAND_DAF      = "DAF XF"
_BRAND_VOLVO    = "Volvo FH16"
_BRAND_IVECO    = "Iveco S-Way"

EXTRA_TRUCKS = [
    ("AA00AA", _BRAND_SCANIA,   0), ("BB11BB", _BRAND_MAN,      1),
    ("CC22CC", _BRAND_MERCEDES, 2), ("DD33DD", _BRAND_DAF,      3),
    ("12AB34", _BRAND_VOLVO,    0), ("56CD78", _BRAND_SCANIA,   1),
    ("90EF12", _BRAND_MAN,      2), ("34GH56", _BRAND_MERCEDES, 0),
    ("78IJ90", _BRAND_DAF,      1), ("23LM45", _BRAND_VOLVO,    0),
    ("67NP89", _BRAND_SCANIA,   1), ("45ST67", _BRAND_VOLVO,    0),
    ("89UV01", _BRAND_SCANIA,   1), ("23WX45", _BRAND_MAN,      2),
    ("11YZ22", _BRAND_IVECO,    3), ("33AB44", _BRAND_DAF,      4),
    ("55CD66", _BRAND_SCANIA,   5), ("77EF88", _BRAND_VOLVO,    0),
    ("99GH00", _BRAND_MAN,      1), ("11IJ22", _BRAND_MERCEDES, 2),
]

CARGO_TYPES = [
    ("Sulfuric acid (fuming)",   "liquid", 22000, True,  "1831", "X886"),
    ("Gasoline ADR",             "liquid", 24000, True,  "1203", "33"),
    ("Propane cylinders",        "gaseous", 8000, True,  "1978", "23"),
    ("Industrial chemicals",     "liquid", 15000, True,  "1830", "80"),
    ("Ammonium nitrate fert.",   "solid",  22000, True,  "1942", "50"),
    ("Ceramic tiles",            "solid",  24000, False, None,   None),
    ("Cork products",            "solid",   8000, False, None,   None),
    ("Paper pulp",               "solid",  28000, False, None,   None),
    ("Salt (Salinas Aveiro)",    "solid",  26000, False, None,   None),
    ("Fish (fresh catch)",       "solid",  12000, False, None,   None),
    ("Wine (Bairrada DOC)",      "liquid", 18000, False, None,   None),
    ("Timber (eucalyptus)",      "solid",  30000, False, None,   None),
    ("Auto parts",               "solid",  16000, False, None,   None),
    ("Construction steel",       "solid",  28000, False, None,   None),
    ("Olive oil (bulk)",         "liquid", 20000, False, None,   None),
    ("Cement bags",              "solid",  25000, False, None,   None),
    ("Plastic granules",         "solid",  15000, False, None,   None),
    ("Machinery parts",          "solid",  12000, False, None,   None),
    ("Canned fish",              "solid",   8000, False, None,   None),
    ("General cargo",            "solid",  10000, False, None,   None),
]

_ALERT_DESCS = {
    "safety":      "Hazardous cargo safety check triggered",
    "operational": "Dock assignment delay — manual reassignment needed",
    "problem":     "Weight discrepancy detected — cargo exceeds declared weight",
    "generic":     "Documentation check — CMR waybill verified",
}

# ── Per-company delay profiles (lo_min, hi_min, weight) ──────────────────────
# Drives SLA variation in per-company analytics (Port Performance page).
# Each tuple is (min_delay_minutes, max_delay_minutes, relative_weight).
_COMPANY_DELAY_PROFILES: dict = {
    "PT509123456":  [(0, 4, 52), (5, 14, 32), (15, 29, 12), (30, 70,  4)],  # Transportes Aveiro — excellent
    "PT509234567":  [(0, 4, 42), (5, 14, 33), (15, 29, 18), (30, 80,  7)],  # Iberian Logistics — good
    "PT509345678":  [(0, 4, 22), (5, 14, 33), (15, 29, 30), (30, 90, 15)],  # EuroTrans — mediocre
    "ES-B12345678": [(0, 4, 12), (5, 14, 23), (15, 29, 38), (30, 90, 27)],  # Garcia SL — consistently late
    "DE123456789":  [(0, 4, 68), (5, 14, 22), (15, 29,  8), (30, 60,  2)],  # Schmidt — punctual (German ops)
    "FR12345678901":[(0, 4, 28), (5, 14, 34), (15, 29, 26), (30, 85, 12)],  # Dupont — below average
}
# Fallback for unlisted companies
_DEFAULT_DELAY_BUCKETS = [(0, 5, 40), (5, 15, 30), (15, 30, 20), (30, 90, 10)]


def _random_delay_for_company(company_nif: str) -> int:
    """Return a realistic delay in minutes for the given company."""
    profile = _COMPANY_DELAY_PROFILES.get(company_nif, _DEFAULT_DELAY_BUCKETS)
    buckets, weights = zip(*[((lo, hi), w) for lo, hi, w in profile])
    lo, hi = random.choices(buckets, weights=weights, k=1)[0]
    return random.randint(lo, hi)


def _random_delay_minutes() -> int:
    """Pick a delay in minutes using the default weighted buckets (legacy helper)."""
    return _random_delay_for_company("")


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _make_booking(db: Session, ref: str, direction: str = "inbound") -> Booking:
    bk = Booking(reference=ref, direction=direction)
    db.add(bk)
    db.flush()
    return bk


def _make_cargo(db: Session, bk_ref: str, cargo_def: tuple) -> Cargo:
    desc, st, weight, is_hazmat, un, kemler = cargo_def
    label = f"{desc} [UN:{un}, Kemler:{kemler}]" if is_hazmat else desc
    c = Cargo(booking_reference=bk_ref, quantity=Decimal(str(weight)),
              state=st, description=label)
    db.add(c)
    db.flush()
    return c


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


def _shift_for_time(dt: datetime, shift_m, shift_a, shift_n):
    """Pick morning/afternoon/night shift based on hour."""
    h = dt.hour
    if 6 <= h < 14:
        return shift_m
    if 14 <= h < 22:
        return shift_a
    return shift_n


def _get_or_create_day_shifts(
    db: Session, d: date, gate_entry_id: int,
    operator_num: str, manager_num: str
) -> tuple:
    """Return (morning_shift, afternoon_shift, night_shift) for a given date,
    creating them if they don't already exist."""
    result = {}
    for stype in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]:
        existing = db.query(Shift).filter(
            Shift.gate_id == gate_entry_id,
            Shift.shift_type == stype,
            Shift.date == d,
        ).first()
        if not existing:
            existing = Shift(
                gate_id=gate_entry_id, shift_type=stype, date=d,
                operator_num_worker=operator_num,
                manager_num_worker=manager_num,
            )
            db.add(existing)
            db.flush()
        result[stype] = existing
    return result[ShiftType.MORNING], result[ShiftType.AFTERNOON], result[ShiftType.NIGHT]


# ── Historical day generator ──────────────────────────────────────────────────

def _generate_historical_day(
    db: Session, day_date: date, trucks, drivers,
    terminal, gate_in, gate_out,
    shift_m, shift_a, shift_n,
    num_appts: int, ref_prefix: str, counter: list,
):
    """Generate a full completed day of appointments with realistic delays."""
    for h in range(num_appts):
        counter[0] += 1
        ref = f"{ref_prefix}-{day_date.strftime('%Y%m%d')}-{counter[0]:05d}"
        bk = _make_booking(db, ref, "inbound" if h % 5 != 0 else "outbound")
        cidx = (h + counter[0]) % len(CARGO_TYPES)
        _make_cargo(db, bk.reference, CARGO_TYPES[cidx])

        hour_offset = random.choice([7, 7, 8, 8, 9, 9, 10, 10, 11, 12, 13, 14, 15, 15, 16, 17, 17])
        sched = datetime.combine(day_date, time(hour_offset, random.randint(0, 55)))

        truck = trucks[h % len(trucks)]
        driver = drivers[h % len(drivers)]
        dur = random.choice([20, 25, 30, 35, 38, 40, 42, 45, 50, 55, 60, 70, 80])
        # Use company-specific delay profile so per-company SLA varies realistically
        delay = _random_delay_for_company(truck.company_nif)

        # ~8% of appointments have a highway infraction (hazmat/speed/docs)
        is_infraction = random.random() < 0.08

        appt = Appointment(
            booking_reference=bk.reference,
            driver_license=driver.drivers_license,
            truck_license_plate=truck.license_plate,
            terminal_id=terminal.id,
            gate_in_id=gate_in.id,
            gate_out_id=gate_out.id,
            scheduled_start_time=sched,
            expected_duration=45,
            status="completed",
            notes=f"Historical — {CARGO_TYPES[cidx][0]}",
            highway_infraction=is_infraction,
        )
        db.add(appt)
        db.flush()

        entry = sched + timedelta(minutes=delay + random.randint(1, 3))
        shift = _shift_for_time(entry, shift_m, shift_a, shift_n)
        v = Visit(
            appointment_id=appt.id,
            shift_gate_id=shift.gate_id,
            shift_type=shift.shift_type,
            shift_date=shift.date,
            entry_time=entry,
            out_time=entry + timedelta(minutes=dur),
            state="done",
        )
        db.add(v)
        db.flush()

        # Operational alert rate: 18% generic, plus mandatory alert for infractions
        if is_infraction:
            at = random.choice(["safety", "safety", "problem"])
            _make_alert(db, v, appt, shift, entry + timedelta(minutes=random.randint(2, 8)), at)
        elif random.random() < 0.12:
            at = random.choice(["operational", "problem", "generic"])
            _make_alert(db, v, appt, shift, entry + timedelta(minutes=random.randint(2, 15)), at)


# ── Main seeder ───────────────────────────────────────────────────────────────

def init_demo_data(db: Session):
    print("=" * 65)
    print("  PEI 2025 — PORTO DE AVEIRO DEMO DATA INITIALIZER")
    print("=" * 65)

    if db.query(Worker).first():
        print("\n  Data already exists — skipping initialization.")
        print("  To reset: docker compose down -v && docker compose up -d")
        return

    try:
        today = date.today()
        now   = datetime.now()

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
        main_driver = drivers[0]  # Oscar Almeida

        # ── Trucks ────────────────────────────────────────────────────────────
        all_demo_plates = VIDEO1_PLATES + VIDEO2_PLATES
        print(f"  Creating trucks: {len(all_demo_plates)} demo + {len(EXTRA_TRUCKS)} historical...")
        trucks_by_plate: dict = {}
        all_trucks_list = []

        for i, plate in enumerate(all_demo_plates):
            t = Truck(
                license_plate=plate,
                brand=[_BRAND_VOLVO, _BRAND_SCANIA, _BRAND_MAN, _BRAND_MERCEDES, _BRAND_DAF][i % 5],
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

        hist_trucks = [t for t in all_trucks_list if t.license_plate not in set(all_demo_plates)]

        # ── Terminals ────────────────────────────────────────────────────────
        print("  Creating terminals...")
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
            Dock(terminal_id=terminal_norte.id,    bay_number="TN-CAIS-1",
                 latitude=Decimal("40.6522"), longitude=Decimal("-8.7428"), current_usage="operational"),
            Dock(terminal_id=terminal_norte.id,    bay_number="TN-CAIS-2",
                 latitude=Decimal("40.6524"), longitude=Decimal("-8.7426"), current_usage="operational"),
            Dock(terminal_id=terminal_norte.id,    bay_number="TN-RORO",
                 latitude=Decimal("40.6518"), longitude=Decimal("-8.7432"), current_usage="operational"),
            Dock(terminal_id=terminal_solidos.id,  bay_number="TGS-CAIS-A",
                 latitude=Decimal("40.6448"), longitude=Decimal("-8.7492"), current_usage="operational"),
            Dock(terminal_id=terminal_solidos.id,  bay_number="TGS-CAIS-B",
                 latitude=Decimal("40.6450"), longitude=Decimal("-8.7494"), current_usage="operational"),
            Dock(terminal_id=terminal_solidos.id,  bay_number="TGS-SILO",
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

        # ── Today's shifts (full, with operators) ─────────────────────────────
        print("  Creating today's shifts...")
        ops = ["OPR001", "OPR002"]
        today_shifts = {}
        for gid, stype, opr, mgr in [
            (gate_entry.id,   ShiftType.MORNING,   ops[0], "MGR001"),
            (gate_entry.id,   ShiftType.AFTERNOON, ops[1], "MGR001"),
            (gate_entry.id,   ShiftType.NIGHT,     ops[0], "MGR002"),
            (gate_highway.id, ShiftType.MORNING,   ops[1], "MGR002"),
            (gate_highway.id, ShiftType.AFTERNOON, ops[0], "MGR002"),
        ]:
            s = Shift(gate_id=gid, shift_type=stype, date=today,
                      operator_num_worker=opr, manager_num_worker=mgr)
            db.add(s)
            today_shifts[(gid, stype)] = s
        db.flush()

        morning_today   = today_shifts[(gate_entry.id, ShiftType.MORNING)]
        afternoon_today = today_shifts[(gate_entry.id, ShiftType.AFTERNOON)]
        night_today     = today_shifts[(gate_entry.id, ShiftType.NIGHT)]

        def _shift_today(dt: datetime):
            return _shift_for_time(dt, morning_today, afternoon_today, night_today)

        # ── Historical shifts (last 5 days, before the 12-month bulk) ─────────
        print("  Creating recent historical shifts (5 days)...")
        recent_shift_map: dict = {}
        for day_offset in range(1, 6):
            d = today - timedelta(days=day_offset)
            sm, sa, sn = _get_or_create_day_shifts(
                db, d, gate_entry.id, ops[day_offset % 2], "MGR001"
            )
            recent_shift_map[d] = (sm, sa, sn)

        # ── 12-month historical shifts (bulk, minimal operator info) ──────────
        print("  Creating 12-month historical shifts (may take a moment)...")
        hist_shift_map: dict = {}
        # We only need gate_entry shifts for historical data
        start_date = today - timedelta(days=365)
        d = start_date
        while d < today - timedelta(days=5):
            # Skip Sundays (very low activity)
            if d.weekday() != 6:
                sm, sa, sn = _get_or_create_day_shifts(
                    db, d, gate_entry.id, ops[d.toordinal() % 2], "MGR001"
                )
                hist_shift_map[d] = (sm, sa, sn)
            d += timedelta(days=1)
        print(f"    Created shifts for {len(hist_shift_map)} historical days")

        # ── Ref counter (global, unique across all appointments) ───────────────
        counter = [0]

        def _next_ref(prefix="AVR"):
            counter[0] += 1
            return f"{prefix}-{counter[0]:06d}"

        # ─────────────────────────────────────────────────────────────────────
        # TODAY'S APPOINTMENTS — explicit statuses, 87AX60 is the only in_transit
        # ─────────────────────────────────────────────────────────────────────
        print("\n  Creating today's appointments...")

        # ── 87AX60 — IN TRANSIT (trial truck, HAZMAT, scheduled 30 min ahead) ─
        sched_87 = now + timedelta(minutes=30)
        bk_87 = _make_booking(db, _next_ref("DEMO"), "inbound")
        _make_cargo(db, bk_87.reference, CARGO_TYPES[0])  # Sulfuric acid
        appt_87 = Appointment(
            booking_reference=bk_87.reference,
            driver_license=main_driver.drivers_license,
            truck_license_plate="87AX60",
            terminal_id=terminal_liquidos.id,
            gate_in_id=gate_entry.id, gate_out_id=None,
            scheduled_start_time=sched_87,
            expected_duration=45,
            status="in_transit",
            notes="HAZMAT: Sulfuric acid [UN:1831, Kemler:X886] — awaiting gate detection",
            highway_infraction=False,
        )
        db.add(appt_87)
        db.flush()
        print(f"    [in_transit ] 87AX60  (id={appt_87.id})")

        # ── SCHEDULED (future today) ──────────────────────────────────────────
        scheduled_specs = [
            # (plate, driver_idx, cargo_idx, hours_ahead, terminal, infraction)
            ("68BSH8",   1, 6,  1.5, terminal_norte,    False),  # Cork products
            ("PEI2025",  2, 8,  2.0, terminal_solidos,  False),  # Salt
            ("LN67OIZGB",3, 12, 3.0, terminal_norte,    False),  # Auto parts
            ("SLJP1523", 4, 19, 4.0, terminal_solidos,  False),  # General cargo
            ("GGAB425",  5, 11, 2.5, terminal_solidos,  False),  # Timber
        ]
        for plate, didx, cidx, hrs_ahead, terminal, infrct in scheduled_specs:
            sched_t = now + timedelta(hours=hrs_ahead)
            bk = _make_booking(db, _next_ref(), "inbound")
            _make_cargo(db, bk.reference, CARGO_TYPES[cidx])
            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[didx % len(drivers)].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal.id,
                gate_in_id=gate_entry.id, gate_out_id=None,
                scheduled_start_time=sched_t,
                expected_duration=45,
                status="scheduled",
                notes=f"Cargo: {CARGO_TYPES[cidx][0]}",
                highway_infraction=infrct,
            )
            db.add(appt)
            db.flush()
            print(f"    [scheduled  ] {plate:12s} (sched +{hrs_ahead:.1f}h)")

        # ── IN PROCESS (inside the port, unloading) ────────────────────────────
        in_process_specs = [
            # (plate, driver_idx, cargo_idx, sched_h, entry_delay_min, dur_so_far)
            ("92BLN3",  2, 7,  now.hour - 1, 8,  30),   # Paper pulp
            ("82BTN5",  1, 13, now.hour - 1, 12, 15),   # Construction steel
        ]
        for plate, didx, cidx, sched_h, entry_delay, dur_so_far in in_process_specs:
            sched_t = datetime.combine(today, time(max(6, min(sched_h, 21)), random.randint(0, 30)))
            entry_t = sched_t + timedelta(minutes=entry_delay)
            bk = _make_booking(db, _next_ref(), "inbound")
            _make_cargo(db, bk.reference, CARGO_TYPES[cidx])
            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[didx % len(drivers)].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal_norte.id,
                gate_in_id=gate_entry.id, gate_out_id=None,
                scheduled_start_time=sched_t,
                expected_duration=45,
                status="in_process",
                notes=f"Cargo: {CARGO_TYPES[cidx][0]}",
            )
            db.add(appt)
            db.flush()
            shift = _shift_today(entry_t)
            db.add(Visit(
                appointment_id=appt.id,
                shift_gate_id=shift.gate_id, shift_type=shift.shift_type, shift_date=shift.date,
                entry_time=entry_t, out_time=None, state="unloading",
            ))
            db.flush()
            print(f"    [in_process ] {plate:12s} (entered {dur_so_far} min ago)")

        # ── COMPLETED (earlier today) ──────────────────────────────────────────
        completed_specs = [
            # (plate, driver_idx, cargo_idx, hours_ago, delay_min, dur_min, terminal, infraction)
            ("321BI13",  6, 5,  4.0, 25, 38, terminal_norte,    True),   # Ceramic tiles, infraction
            ("CA93896",  7, 9,  3.0,  5, 42, terminal_solidos,  False),  # Fish
            ("82BTN5",   3, 16, 6.0,  3, 55, terminal_solidos,  False),  # Plastic granules (second run)
            (hist_trucks[0].license_plate, 8, 18, 5.5, 18, 40, terminal_norte, False),  # Machinery
            (hist_trucks[1].license_plate, 9, 14, 7.0, 35, 60, terminal_solidos, False), # Olive oil
            (hist_trucks[2].license_plate, 4, 11, 8.0,  0, 32, terminal_norte, False),  # Timber
            (hist_trucks[3].license_plate, 1, 8,  2.5,  8, 45, terminal_solidos, False), # Salt
        ]
        for plate, didx, cidx, hrs_ago, delay_min, dur_min, terminal, infrct in completed_specs:
            sched_t = now - timedelta(hours=hrs_ago)
            entry_t = sched_t + timedelta(minutes=delay_min)
            exit_t  = entry_t + timedelta(minutes=dur_min)
            bk = _make_booking(db, _next_ref(), "inbound")
            _make_cargo(db, bk.reference, CARGO_TYPES[cidx])
            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[didx % len(drivers)].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal.id,
                gate_in_id=gate_entry.id, gate_out_id=gate_out.id,
                scheduled_start_time=sched_t,
                expected_duration=45,
                status="completed",
                notes=f"Cargo: {CARGO_TYPES[cidx][0]}",
                highway_infraction=infrct,
            )
            db.add(appt)
            db.flush()
            shift = _shift_today(entry_t)
            v = Visit(
                appointment_id=appt.id,
                shift_gate_id=shift.gate_id, shift_type=shift.shift_type, shift_date=shift.date,
                entry_time=entry_t, out_time=exit_t, state="done",
            )
            db.add(v)
            db.flush()
            if infrct:
                _make_alert(db, v, appt, shift, entry_t + timedelta(minutes=5), "safety")
            print(f"    [completed  ] {plate:12s} ({hrs_ago:.1f}h ago, delay={delay_min}min)")

        # ── CANCELED (1-2 today) ───────────────────────────────────────────────
        canceled_specs = [
            ("LN67OIZGB", 3, 15, 5.0),  # Canceled cement — same plate also has scheduled, different booking
        ]
        for plate, didx, cidx, hrs_ago in canceled_specs:
            sched_t = now - timedelta(hours=hrs_ago)
            bk = _make_booking(db, _next_ref(), "inbound")
            _make_cargo(db, bk.reference, CARGO_TYPES[cidx])
            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[didx % len(drivers)].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal_solidos.id,
                gate_in_id=gate_entry.id, gate_out_id=None,
                scheduled_start_time=sched_t,
                expected_duration=45,
                status="canceled",
                notes=f"Cargo: {CARGO_TYPES[cidx][0]} — cancelado por indisponibilidade de cais",
            )
            db.add(appt)
            db.flush()
            print(f"    [canceled   ] {plate:12s}")

        # ── Extra completed today (more data for wait histogram + dashboard) ────
        # Uses hist_trucks to avoid plate conflicts with live demo trucks.
        # Spans a spread of delays so all 4 histogram buckets have values.
        extra_completed_today = [
            # (truck_idx, driver_idx, cargo_idx, hrs_ago, delay_min, dur_min, terminal, infraction)
            (4,  0, 2,  1.5,  3, 28, terminal_liquidos,  False),  # Propane, on-time
            (5,  1, 6,  2.0,  7, 40, terminal_norte,     False),  # Cork, minor delay
            (6,  2, 7,  2.5,  9, 35, terminal_solidos,   False),  # Paper pulp, minor
            (7,  3, 10, 3.0, 18, 55, terminal_solidos,   False),  # Fish, delayed
            (8,  4, 11, 3.5, 22, 48, terminal_norte,     True),   # Timber, infraction
            (9,  5, 13, 4.5,  2, 33, terminal_norte,     False),  # Steel, on-time
            (10, 6, 16, 5.0, 42, 60, terminal_solidos,   False),  # Plastic, very late
            (11, 7, 19, 5.5,  0, 25, terminal_norte,     False),  # General, on-time
            (12, 8, 5,  6.5, 33, 45, terminal_solidos,   True),   # Ceramics, infraction
            (13, 9, 14, 7.5,  6, 38, terminal_liquidos,  False),  # Olive oil, minor
        ]
        for tidx, didx, cidx, hrs_ago, delay_min, dur_min, terminal, infrct in extra_completed_today:
            truck = hist_trucks[tidx % len(hist_trucks)]
            sched_t = now - timedelta(hours=hrs_ago)
            entry_t = sched_t + timedelta(minutes=delay_min)
            exit_t  = entry_t + timedelta(minutes=dur_min)
            bk = _make_booking(db, _next_ref("EXT"), "inbound")
            _make_cargo(db, bk.reference, CARGO_TYPES[cidx])
            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[didx % len(drivers)].drivers_license,
                truck_license_plate=truck.license_plate,
                terminal_id=terminal.id,
                gate_in_id=gate_entry.id, gate_out_id=gate_out.id,
                scheduled_start_time=sched_t,
                expected_duration=45,
                status="completed",
                notes=f"Cargo: {CARGO_TYPES[cidx][0]}",
                highway_infraction=infrct,
            )
            db.add(appt)
            db.flush()
            shift = _shift_today(entry_t)
            v = Visit(
                appointment_id=appt.id,
                shift_gate_id=shift.gate_id, shift_type=shift.shift_type, shift_date=shift.date,
                entry_time=entry_t, out_time=exit_t, state="done",
            )
            db.add(v)
            db.flush()
            if infrct:
                _make_alert(db, v, appt, shift, entry_t + timedelta(minutes=4), "safety")
            print(f"    [completed+ ] {truck.license_plate:12s} ({hrs_ago:.1f}h ago, delay={delay_min}min)")

        # ── Highway gate appointments (Video2 plates, today) ──────────────────
        v2_today_specs = [
            # (plate, didx, cidx, status, sched_offset_h, delay_min, dur_min, infraction)
            ("321BI13",  5, 1, "completed", -5.0, 10, 38, True),   # Gasoline ADR, infraction
            ("GGAB425",  6, 4, "completed", -4.0,  5, 45, False),  # Ammonium nitrate
            ("CA93896",  7, 3, "scheduled",  2.0,  0,  0, False),  # Industrial chemicals future
        ]
        hw_shift_m = today_shifts[(gate_highway.id, ShiftType.MORNING)]
        hw_shift_a = today_shifts[(gate_highway.id, ShiftType.AFTERNOON)]
        for plate, didx, cidx, status, sched_off_h, delay_min, dur_min, infrct in v2_today_specs:
            sched_t = now + timedelta(hours=sched_off_h)
            bk = _make_booking(db, _next_ref("HWY"), "inbound")
            _make_cargo(db, bk.reference, CARGO_TYPES[cidx])
            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[didx % len(drivers)].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal_liquidos.id,
                gate_in_id=gate_highway.id, gate_out_id=gate_out.id if status == "completed" else None,
                scheduled_start_time=sched_t,
                expected_duration=40,
                status=status,
                notes=f"Highway — {CARGO_TYPES[cidx][0]}",
                highway_infraction=infrct,
            )
            db.add(appt)
            db.flush()
            if status == "completed":
                entry_t = sched_t + timedelta(minutes=delay_min)
                exit_t  = entry_t + timedelta(minutes=dur_min)
                hw_shift = hw_shift_m if entry_t.hour < 14 else hw_shift_a
                v = Visit(
                    appointment_id=appt.id,
                    shift_gate_id=hw_shift.gate_id, shift_type=hw_shift.shift_type, shift_date=hw_shift.date,
                    entry_time=entry_t, out_time=exit_t, state="done",
                )
                db.add(v)
                db.flush()
                if infrct:
                    _make_alert(db, v, appt, hw_shift, entry_t + timedelta(minutes=3), "safety")
            print(f"    [hw-{status[:8]:<8}] {plate:12s}")

        # ─────────────────────────────────────────────────────────────────────
        # RECENT HISTORICAL DATA (last 5 days — existing pattern)
        # ─────────────────────────────────────────────────────────────────────
        print("\n  Creating recent historical data (5 days)...")
        recent_daily = [12, 10, 14, 11, 13]
        terminals_cycle = [terminal_norte, terminal_solidos, terminal_liquidos,
                           terminal_norte, terminal_solidos]
        for day_offset in range(1, 6):
            d = today - timedelta(days=day_offset)
            sm, sa, sn = recent_shift_map[d]
            _generate_historical_day(
                db, d, hist_trucks, drivers,
                terminals_cycle[day_offset - 1],
                gate_entry, gate_out, sm, sa, sn,
                recent_daily[day_offset - 1], "HIST-R", counter,
            )
            print(f"    Day -{day_offset} ({d}): {recent_daily[day_offset-1]} appointments")

        # ─────────────────────────────────────────────────────────────────────
        # 12-MONTH BULK HISTORICAL DATA
        # Monthly volume varies to simulate seasonality (higher summer/autumn)
        # ─────────────────────────────────────────────────────────────────────
        print("\n  Creating 12-month bulk historical data...")

        # Volume multiplier per month (January=1 through December=12)
        _MONTHLY_LOAD = {
            1: 0.70,  # Jan — low (post-holidays)
            2: 0.75,  # Feb
            3: 0.85,  # Mar
            4: 0.90,  # Apr
            5: 0.95,  # May
            6: 1.00,  # Jun
            7: 1.10,  # Jul — peak summer
            8: 1.15,  # Aug — peak summer
            9: 1.10,  # Sep — autumn harvest
            10: 1.05, # Oct
            11: 0.85, # Nov
            12: 0.75, # Dec — holidays
        }

        BASE_DAILY = 20       # base appointments on a weekday
        WEEKEND_FACTOR = 0.4  # weekends have ~40% of weekday load

        total_hist = 0
        prev_month = None
        all_terminals = [terminal_norte, terminal_solidos, terminal_liquidos]

        sorted_hist_days = sorted(hist_shift_map.keys())
        for d in sorted_hist_days:
            month_load = _MONTHLY_LOAD.get(d.month, 1.0)
            is_weekend = d.weekday() >= 5
            load = month_load * (WEEKEND_FACTOR if is_weekend else 1.0)
            num_appts = max(1, round(BASE_DAILY * load + random.randint(-2, 2)))

            sm, sa, sn = hist_shift_map[d]
            terminal = all_terminals[d.toordinal() % len(all_terminals)]
            _generate_historical_day(
                db, d, hist_trucks, drivers,
                terminal, gate_entry, gate_out, sm, sa, sn,
                num_appts, "HIST", counter,
            )
            total_hist += num_appts

            if d.month != prev_month:
                print(f"    Month {d.year}-{d.month:02d}: generating...")
                prev_month = d.month

        print(f"    Total historical appointments: {total_hist}")

        # ── Commit ────────────────────────────────────────────────────────────
        print("\n  Saving to database (this may take a moment)...")
        db.commit()

        # ── Summary ───────────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("  DATABASE INITIALIZED — PEI 2025 PORTO DE AVEIRO DEMO")
        print("=" * 70)

        print("""
┌─────────────────────────────────────────────────────────────────────┐
│                        LOGIN CREDENTIALS                             │
├─────────────────────────────────────────────────────────────────────┤
│  WEB PORTAL:                                                         │
│    worker@porto.pt               │ password123  │ Operator           │
│    manager@example.pt            │ password123  │ Manager            │
│    teresa.lopes@portodeaveiro.pt │ password123  │ Manager            │
├─────────────────────────────────────────────────────────────────────┤
│  MOBILE APP (Drivers):                                               │
│    PT12345678  Oscar Almeida     │ driver123                        │
│    PT23456789  Sofia Rodrigues   │ driver123                        │
│    ES87654321  Carlos Garcia     │ driver123                        │
│    DE11223344  Hans Mueller      │ driver123                        │
│    FR99887766  Pierre Dubois     │ driver123                        │
└─────────────────────────────────────────────────────────────────────┘
""")

        print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│  TODAY'S LIVE STATE:                                                 │
│    87AX60     → in_transit  (only in_transit truck)                 │
│    92BLN3     → in_process  (unloading)                             │
│    82BTN5     → in_process  (unloading)                             │
│    68BSH8     → scheduled   (+1.5h)                                 │
│    PEI2025    → scheduled   (+2.0h)                                 │
│    LN67OIZGB  → scheduled   (+3.0h)                                 │
│    SLJP1523   → scheduled   (+4.0h)                                 │
│    GGAB425    → scheduled   (+2.5h)                                 │
│    321BI13    → completed   (with safety infraction)                │
│    CA93896    → completed   (highway gate)                          │
│    LN67OIZGB  → canceled    (earlier booking, same plate)           │
├─────────────────────────────────────────────────────────────────────┤
│  HISTORY: 12 months · ~{total_hist} appointments · seasonal variation    │
│  CO₂ trend data available for all 12 months                         │
│  Delay profiles vary per company (SLA analytics realistic)           │
│  ~8% highway infractions in history · 12% operational alerts         │
└─────────────────────────────────────────────────────────────────────┘
""")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback; traceback.print_exc()
        db.rollback()
        raise

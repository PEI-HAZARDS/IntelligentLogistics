#!/usr/bin/env python3
"""
Realistic data initializer for Porto de Aveiro demo.
Populates a rich dataset with completed cycles, visits, alerts, and metrics
so the dashboard is immediately populated on first load.

Highlight scenario: truck 87AX60 carrying dangerous goods (UN 1831, Kemler X886)
driven by Oscar Almeida — in_transit, no pre-seeded infraction (detected at runtime).

Run with: python scripts/data_init_realistic.py
"""

from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import os
import sys
import random

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from Data_Module.models.sql_models import (
        Base, Worker, Manager, Operator, Company, Driver,
        Truck, Terminal, Dock, Gate, Shift, ShiftType,
        Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
    )
except Exception:
    try:
        from infrastructure.persistence.sql_models import (
            Base, Worker, Manager, Operator, Company, Driver,
            Truck, Terminal, Dock, Gate, Shift, ShiftType,
            Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
        )
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =============================================================================
# REALISTIC DATA FOR PORTO DE AVEIRO
# =============================================================================

# Transport companies operating in Port of Aveiro region
COMPANIES = [
    ("PT509123456", "Transportes Aveiro Lda", "+351 234 567 890"),
    ("PT509234567", "Iberian Logistics SA", "+351 234 678 901"),
    ("PT509345678", "EuroTrans Portugal", "+351 234 789 012"),
    ("ES-B12345678", "Transportes Garcia SL (Spain)", "+34 91 234 5678"),
    ("DE123456789", "Schmidt Spedition GmbH (Germany)", "+49 30 1234567"),
    ("FR12345678901", "Transports Dupont SARL (France)", "+33 1 23 45 67 89"),
]

# Drivers with realistic names matching nationalities
# (license, name, company_idx)
DRIVERS = [
    ("PT12345678", "Oscar Almeida", 0),        # HAZMAT driver — main demo protagonist
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

# Trucks: plate, brand, company_idx
# All plates in compact format (no dashes)
# 87AX60 is the HAZMAT demo star truck
TRUCKS = [
    # === HAZMAT trucks ===
    ("87AX60",    "Volvo FH16",       0),   # STAR: Oscar Almeida's hazmat truck
    ("AA00AA",    "Scania R500",      0),   # Gasoline
    ("BB11BB",    "MAN TGX",          1),   # Propane
    ("CC22CC",    "Mercedes Actros",  2),   # Chemical
    ("DD33DD",    "DAF XF",           3),   # Ammonium
    # === Normal cargo trucks ===
    ("12AB34",    "Volvo FH16",       0),   # Ceramic tiles
    ("56CD78",    "Scania R500",      1),   # Cork products
    ("90EF12",    "MAN TGX",          2),   # Paper pulp
    ("34GH56",    "Mercedes Actros",  0),   # Salt
    ("78IJ90",    "DAF XF",           1),   # Fish
    ("1234ABC",   "Iveco S-Way",      3),   # Wine (Spanish truck)
    ("5678DEF",   "Volvo FH16",       3),   # Dairy (Spanish truck)
    ("9012GHI",   "Scania R500",      3),   # Timber (Spanish truck)
    ("BAB1234",   "MAN TGX",          4),   # Auto parts (German truck)
    ("MCD5678",   "Mercedes Actros",  4),   # Glass bottles (German truck)
    ("AB123CD",   "Renault T",        5),   # Frozen seafood (French truck)
    ("EF456GH",   "Renault T",        5),   # Construction steel (French truck)
    ("23LM45",    "Volvo FH16",       0),   # Textile rolls
    ("67NP89",    "Scania R500",      1),   # Electronic components
    ("01QR23",    "DAF XF",           2),   # General cargo
    # === Extra trucks for richer dataset ===
    ("45ST67",    "Volvo FH16",       0),
    ("89UV01",    "Scania R500",      1),
    ("23WX45",    "MAN TGX",          2),
    ("67YZ89",    "Mercedes Actros",  3),
    ("11AA22",    "DAF XF",           4),
    ("33BB44",    "Renault T",        5),
    ("55CC66",    "Iveco S-Way",      0),
    ("77DD88",    "Volvo FH16",       1),
    ("99EE00",    "Scania R500",      2),
    ("22FF33",    "MAN TGX",          3),
]

# Cargo types: (description, state, weight_kg, is_hazmat, un_code, kemler_code, origin)
CARGO_DEFS = [
    # HAZMAT cargos (first 5 match first 5 trucks)
    ("Sulfuric acid (fuming)", "liquid", 22000, True, "1831", "X886", "CUF Quimicos Estarreja"),  # 87AX60 STAR
    ("Gasoline ADR",           "liquid", 24000, True, "1203", "33",   "Refinaria Sines"),
    ("Propane cylinders",      "gaseous", 8000, True, "1978", "23",   "Galp Energia"),
    ("Industrial chemicals",   "liquid", 15000, True, "1830", "80",   "CUF Quimicos"),
    ("Ammonium nitrate fert.", "solid",  22000, True, "1942", "50",   "Sapec Agro"),
    # Normal cargos (remaining trucks)
    ("Ceramic tiles (Revigres)",         "solid",  24000, False, None, None, "Revigres Aveiro"),
    ("Cork products (Corticeira)",       "solid",   8000, False, None, None, "Corticeira Amorim"),
    ("Paper pulp (Navigator)",           "solid",  28000, False, None, None, "The Navigator Co"),
    ("Salt (Salinas Aveiro)",            "solid",  26000, False, None, None, "Salinas de Aveiro"),
    ("Fish (fresh catch)",               "solid",  12000, False, None, None, "Docapesca Aveiro"),
    ("Wine (Bairrada DOC)",              "liquid", 18000, False, None, None, "Caves S. Joao"),
    ("Dairy products (Lactogal)",        "solid",  14000, False, None, None, "Lactogal"),
    ("Timber (eucalyptus)",              "solid",  30000, False, None, None, "Altri Florestal"),
    ("Auto parts (Toyota)",              "solid",  16000, False, None, None, "Toyota Caetano"),
    ("Glass bottles (BA Glass)",         "solid",  22000, False, None, None, "BA Glass Aveiro"),
    ("Frozen seafood",                   "solid",  18000, False, None, None, "Friopesca"),
    ("Construction steel",               "solid",  28000, False, None, None, "ArcelorMittal"),
    ("Textile rolls",                    "solid",   9000, False, None, None, "Riopele Texteis"),
    ("Electronic components",            "solid",   5000, False, None, None, "Continental Mabor"),
    ("General cargo",                    "solid",  10000, False, None, None, "Porto de Aveiro"),
    # Extra cargo types
    ("Olive oil (bulk)",                 "liquid", 20000, False, None, None, "Sovena Abrantes"),
    ("Cement bags",                      "solid",  25000, False, None, None, "Cimpor Souselas"),
    ("Fertilizer (organic)",             "solid",  18000, False, None, None, "Fertiberia"),
    ("Plastic granules",                 "solid",  15000, False, None, None, "Repsol Polimeros"),
    ("Machinery parts",                  "solid",  12000, False, None, None, "Renault CACIA"),
    ("Canned fish",                      "solid",   8000, False, None, None, "Ramirez Conservas"),
    ("Marble slabs",                     "solid",  27000, False, None, None, "Marmores Estremoz"),
    ("Animal feed",                      "solid",  20000, False, None, None, "Sorgal Ovar"),
    ("Aluminium profiles",               "solid",  16000, False, None, None, "Extrusal Aveiro"),
    ("Bottled water",                    "liquid", 22000, False, None, None, "Agua Luso"),
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _make_booking(db: Session, ref: str, direction: str = "inbound") -> Booking:
    bk = Booking(reference=ref, direction=direction)
    db.add(bk)
    db.flush()
    return bk


def _make_cargo(db: Session, bk_ref: str, cargo_def: tuple) -> Cargo:
    desc, st, weight, is_hazmat, un, kemler, origin = cargo_def
    label = f"{desc} [UN:{un}, Kemler:{kemler}] - Origin: {origin}" if is_hazmat else f"{desc} - Origin: {origin}"
    c = Cargo(booking_reference=bk_ref, quantity=Decimal(str(weight)), state=st, description=label)
    db.add(c)
    db.flush()
    return c


def _make_appointment(db: Session, bk_ref: str, driver, truck, terminal, gate_in, gate_out,
                      sched_time, status, notes, expected_duration=45,
                      highway_infraction=False) -> Appointment:
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
        state="completed" if duration_min else "unloading"
    )
    db.add(v)
    db.flush()
    return v


def _make_alert(db: Session, visit, appt, shift, timestamp, alert_type, description) -> Alert:
    a = Alert(
        visit_id=visit.appointment_id,
        appointment_id=appt.id,
        timestamp=timestamp,
        type=alert_type,
        description=description
    )
    db.add(a)
    db.flush()
    db.add(ShiftAlertHistory(
        shift_gate_id=shift.gate_id,
        shift_type=shift.shift_type,
        shift_date=shift.date,
        alert_id=a.id
    ))
    db.flush()
    return a


def _generate_historical_day(db, day_date, trucks, drivers, terminal, gate_in, gate_out,
                             shifts_morning, shifts_afternoon, num_appointments, day_label):
    """Generate a full day of historical completed appointments with visits and alerts."""
    base_time = datetime.combine(day_date, time(7, 0))
    created = 0

    for h in range(num_appointments):
        ref = f"AVR-{day_date.strftime('%Y%m%d')}-{h+1:04d}"
        bk = _make_booking(db, ref, "inbound" if h % 3 != 0 else "outbound")

        cidx = (h + 5) % len(CARGO_DEFS)
        cargo_def = CARGO_DEFS[cidx]
        _make_cargo(db, bk.reference, cargo_def)

        # Spread appointments across the day with realistic clustering
        hour_offset = random.choice([7, 8, 8, 9, 9, 9, 10, 10, 11, 12, 13, 14, 14, 15, 15, 16, 17])
        sched = datetime.combine(day_date, time(hour_offset, random.randint(0, 55)))

        tidx = h % len(trucks)
        didx = h % len(drivers)

        # Vary turnaround times (20-90 min range)
        dur = random.choice([20, 25, 28, 30, 32, 35, 38, 40, 42, 45, 50, 55, 60, 70, 80, 90])

        # Some late arrivals (delays)
        delay = random.choice([0, 0, 0, 0, 5, 10, 15, 20, 30, 45])

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
            notes=f"[HIST-{day_label}] Cargo: {cargo_def[0]}",
        )
        db.add(appt)
        db.flush()

        entry = sched + timedelta(minutes=delay + random.randint(1, 5))
        shift = shifts_morning if entry.hour < 14 else shifts_afternoon
        v = _make_visit(db, appt, shift, entry, dur)

        # Add alerts to some visits (roughly 25% of appointments)
        if random.random() < 0.25:
            alert_types = ["operational", "problem", "generic", "safety"]
            alert_descs = {
                "operational": f"Dock reassignment for {trucks[tidx].license_plate}",
                "problem": f"Weight discrepancy — {cargo_def[0]}",
                "generic": f"Documentation check — CMR verified for {trucks[tidx].license_plate}",
                "safety": f"Safety inspection flag for {trucks[tidx].license_plate}",
            }
            at = random.choice(alert_types)
            _make_alert(db, v, appt, shift, entry + timedelta(minutes=random.randint(2, 15)),
                        at, alert_descs[at])

        created += 1

    return created


def init_data(db: Session):
    """
    Initialize database with realistic Porto de Aveiro data.
    Creates a rich dataset with completed cycles, visits, alerts.
    """
    print("=" * 70)
    print("  PORTO DE AVEIRO - REALISTIC DATA INITIALIZER")
    print("=" * 70)

    if db.query(Worker).first():
        print("\nData already exists. Skipping initialization.")
        print("To reset: docker compose down -v && docker compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ===== WORKERS =====
        print("\nCreating port workers...")

        workers_data = [
            ("MGR001", "Joao Silva",        "manager@example.pt",               "+351 910 000 001", True),
            ("MGR002", "Teresa Lopes",       "teresa.lopes@portodeaveiro.pt",    "+351 910 000 004", True),
            ("OPR001", "Maria Santos",       "worker@portodeaveiro.pt",          "+351 910 000 002", True),
            ("OPR002", "Antonio Ferreira",   "antonio.ferreira@portodeaveiro.pt","+351 910 000 003", True),
            ("OPR003", "Carlos Oliveira",    "carlos.oliveira@portodeaveiro.pt", "+351 910 000 005", True),
            ("OPR004", "Beatriz Martins",    "beatriz.martins@portodeaveiro.pt", "+351 910 000 006", True),
        ]

        worker_objs = {}
        for num, name, email, phone, active in workers_data:
            w = Worker(
                num_worker=num, name=name, email=email, phone=phone,
                password_hash=pwd_context.hash("password123"), active=active
            )
            db.add(w)
            worker_objs[num] = w
        db.flush()

        # Manager / Operator specializations
        db.add(Manager(num_worker="MGR001", access_level="admin"))
        db.add(Manager(num_worker="MGR002", access_level="basic"))
        for opr in ["OPR001", "OPR002", "OPR003", "OPR004"]:
            db.add(Operator(num_worker=opr))
        db.flush()

        # ===== COMPANIES =====
        print("Creating transport companies...")
        companies = []
        for nif, name, contact in COMPANIES:
            c = Company(nif=nif, name=name, contact=contact)
            companies.append(c)
        db.add_all(companies)
        db.flush()

        # ===== DRIVERS =====
        print("Creating drivers...")
        drivers = []
        for license_num, name, company_idx in DRIVERS:
            d = Driver(
                drivers_license=license_num, name=name,
                company_nif=companies[company_idx].nif,
                password_hash=pwd_context.hash("driver123"), active=True
            )
            drivers.append(d)
        db.add_all(drivers)
        db.flush()

        # ===== TRUCKS =====
        print(f"Creating {len(TRUCKS)} trucks...")
        trucks = []
        for plate, brand, company_idx in TRUCKS:
            t = Truck(license_plate=plate, brand=brand, company_nif=companies[company_idx].nif)
            trucks.append(t)
        db.add_all(trucks)
        db.flush()

        # ===== TERMINAL =====
        print("Creating Porto de Aveiro terminal...")
        terminal = Terminal(
            name="Terminal Multiusos - Porto de Aveiro",
            latitude=Decimal("40.6446"), longitude=Decimal("-8.7455"),
            hazmat_approved=True
        )
        db.add(terminal)
        db.flush()

        # ===== DOCKS =====
        print("Creating docks...")
        docks = [
            Dock(terminal_id=terminal.id, bay_number="CAIS-NORTE-1", latitude=Decimal("40.6450"), longitude=Decimal("-8.7460"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-NORTE-2", latitude=Decimal("40.6451"), longitude=Decimal("-8.7461"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-SUL-1",   latitude=Decimal("40.6440"), longitude=Decimal("-8.7450"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-SUL-2",   latitude=Decimal("40.6441"), longitude=Decimal("-8.7451"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-HAZMAT",  latitude=Decimal("40.6435"), longitude=Decimal("-8.7445"), current_usage="operational"),
        ]
        db.add_all(docks)
        db.flush()

        # ===== GATES =====
        print("Creating gates...")
        gate_in = Gate(label="Portaria 1 - Entrada Principal", latitude=Decimal("40.6460"), longitude=Decimal("-8.7470"))
        gate_out = Gate(label="Portaria 2 - Saida", latitude=Decimal("40.6430"), longitude=Decimal("-8.7440"))
        gate_highway = Gate(label="Gate 3 - Abordagem A25", latitude=Decimal("40.6500"), longitude=Decimal("-8.7500"))
        db.add_all([gate_in, gate_out, gate_highway])
        db.flush()

        # ===== SHIFTS (today + 5 historical days) =====
        print("Creating shifts...")
        shift_map = {}  # (gate_id, shift_type, date) -> Shift

        # Create shifts for today and 5 previous days
        operators = ["OPR001", "OPR002", "OPR003", "OPR004"]
        for day_offset in range(6):  # today + 5 days back
            d = today - timedelta(days=day_offset)
            configs = [
                (gate_in.id,      ShiftType.MORNING,   d, operators[0], "MGR001"),
                (gate_in.id,      ShiftType.AFTERNOON,  d, operators[1], "MGR001"),
                (gate_in.id,      ShiftType.NIGHT,      d, operators[2], "MGR001"),
                (gate_highway.id, ShiftType.MORNING,    d, operators[3], "MGR002"),
                (gate_highway.id, ShiftType.AFTERNOON,   d, operators[3], "MGR002"),
            ]
            for gid, stype, sdate, opr, mgr in configs:
                s = Shift(gate_id=gid, shift_type=stype, date=sdate,
                          operator_num_worker=opr, manager_num_worker=mgr)
                db.add(s)
                shift_map[(gid, stype, sdate)] = s

        db.flush()

        # Convenience references for today's shifts
        morning_shift = shift_map[(gate_in.id, ShiftType.MORNING, today)]
        afternoon_shift = shift_map[(gate_in.id, ShiftType.AFTERNOON, today)]

        # =====================================================================
        # TODAY'S APPOINTMENTS (40+ for rich dashboard data)
        # =====================================================================
        print("Creating today's appointments (~45 with varied statuses)...")

        all_appointments = []
        appt_counter = [0]  # mutable counter for booking references

        def next_ref():
            appt_counter[0] += 1
            return f"AVR-{today.strftime('%Y%m%d')}-{appt_counter[0]:04d}"

        # ---------------------------------------------------------------
        # APPOINTMENT 0: 87AX60 — HAZMAT IN TRANSIT (approaching port)
        # Oscar Almeida, Sulfuric acid fuming, UN 1831, Kemler X886
        # NO pre-seeded infraction — detected dynamically at runtime
        # ---------------------------------------------------------------
        bk0 = _make_booking(db, next_ref())
        _make_cargo(db, bk0.reference, CARGO_DEFS[0])

        appt0_time = now + timedelta(minutes=15)
        appt0 = Appointment(
            booking_reference=bk0.reference,
            driver_license="PT12345678",  # Oscar Almeida
            truck_license_plate="87AX60",
            terminal_id=terminal.id,
            gate_in_id=gate_in.id,
            gate_out_id=None,
            scheduled_start_time=appt0_time,
            expected_duration=60,
            status="in_transit",
            highway_infraction=False,  # No pre-seeded infraction
            notes="HAZMAT: Sulfuric acid (fuming) [UN:1831, Kemler:X886] - Approaching port",
        )
        db.add(appt0)
        db.flush()
        all_appointments.append((appt0, trucks[0], True, CARGO_DEFS[0][0], "in_transit"))

        # ---------------------------------------------------------------
        # APPOINTMENTS 1-4: Other HAZMAT trucks — mixed statuses
        # ---------------------------------------------------------------
        hazmat_statuses = [
            # (status, has_visit, duration_min, minutes_ago)
            ("in_process", True,  None, 45),      # AA00AA: currently being processed
            ("in_transit", False, None, -20),      # BB11BB: arriving in 20 min
            ("completed",  True,  38,   180),      # CC22CC: completed 3h ago
            ("in_transit", False, None, -60),      # DD33DD: arriving in 1h
        ]

        for i in range(1, 5):
            plate, brand, cidx_c = TRUCKS[i]
            cargo_def = CARGO_DEFS[i]
            status, has_visit, dur, mins_ago = hazmat_statuses[i - 1]

            bk = _make_booking(db, next_ref())
            _make_cargo(db, bk.reference, cargo_def)

            sched_time = now - timedelta(minutes=mins_ago) if mins_ago > 0 else now + timedelta(minutes=abs(mins_ago))
            driver_idx = i % len(drivers)

            appt = _make_appointment(
                db, bk.reference, drivers[driver_idx], trucks[i], terminal,
                gate_in, gate_out, sched_time, status,
                f"HAZMAT: {cargo_def[0]} [UN:{cargo_def[4]}, Kemler:{cargo_def[5]}]",
                highway_infraction=(i == 1),  # AA00AA flagged
            )

            if has_visit:
                entry = sched_time + timedelta(minutes=3)
                shift = morning_shift if entry.hour < 14 else afternoon_shift
                v = _make_visit(db, appt, shift, entry, dur)
                _make_alert(db, v, appt, shift, entry + timedelta(minutes=1),
                            "safety",
                            f"Hazardous cargo detected | UN {cargo_def[4]} - {cargo_def[0]} | Kemler {cargo_def[5]}")

            all_appointments.append((appt, trucks[i], True, cargo_def[0], status))

        # ---------------------------------------------------------------
        # APPOINTMENTS 5-19: Normal cargo — original set with rich statuses
        # ---------------------------------------------------------------
        normal_configs = [
            # (truck_idx, cargo_idx, status, has_visit, dur, mins_offset, alert_type)
            (5,  5,  "completed",  True,  35,   240, None),
            (6,  6,  "completed",  True,  28,   200, None),
            (7,  7,  "completed",  True,  42,   160, "operational"),
            (8,  8,  "completed",  True,  31,   130, None),
            (9,  9,  "in_process", True,  None, 25,  None),
            (10, 10, "in_process", True,  None, 15,  "problem"),
            (11, 11, "completed",  True,  40,   300, None),
            (12, 12, "in_transit", False, None, -10, None),
            (13, 13, "in_transit", False, None, -30, None),
            (14, 14, "in_transit", False, None, -45, None),
            (15, 15, "in_transit", False, None, -70, None),
            (16, 16, "in_transit", False, None, -90, None),
            (17, 17, "completed",  True,  25,   100, None),
            (18, 18, "completed",  True,  33,   80,  "generic"),
            (19, 19, "canceled",   False, None, 60,  None),
        ]

        for cfg in normal_configs:
            tidx, cidx, status, has_visit, dur, mins, alert_t = cfg
            plate, brand, comp_idx = TRUCKS[tidx]
            cargo_def = CARGO_DEFS[cidx]
            driver_idx = tidx % len(drivers)

            bk = _make_booking(db, next_ref(), "inbound" if tidx % 3 != 0 else "outbound")
            _make_cargo(db, bk.reference, cargo_def)

            sched_time = now - timedelta(minutes=mins) if mins > 0 else now + timedelta(minutes=abs(mins))

            appt = _make_appointment(
                db, bk.reference, drivers[driver_idx], trucks[tidx], terminal,
                gate_in, gate_out, sched_time, status, f"Cargo: {cargo_def[0]}",
            )

            if has_visit:
                entry = sched_time + timedelta(minutes=random.randint(2, 8))
                shift = morning_shift if entry.hour < 14 else afternoon_shift
                v = _make_visit(db, appt, shift, entry, dur)

                if alert_t:
                    alert_descs = {
                        "operational": f"Dock assignment delay for {plate} — manual reassignment needed",
                        "problem":     f"Weight discrepancy for {plate} — cargo {cargo_def[0]} exceeds declared weight by 800kg",
                        "generic":     f"Documentation check for {plate} — CMR waybill verified",
                    }
                    _make_alert(db, v, appt, shift, entry + timedelta(minutes=5),
                                alert_t, alert_descs.get(alert_t, f"Alert for {plate}"))

            all_appointments.append((appt, trucks[tidx], False, cargo_def[0], status))

        # ---------------------------------------------------------------
        # APPOINTMENTS 20-44: Extra today appointments for richer metrics
        # More completed, in_process, in_transit, canceled
        # ---------------------------------------------------------------
        extra_configs = [
            # (truck_idx, cargo_idx, status, has_visit, dur, mins_offset, alert_type)
            # --- More completed (for volume/turnaround metrics) ---
            (20, 20, "completed",  True,  22,  350, None),
            (21, 21, "completed",  True,  55,  320, "operational"),
            (22, 22, "completed",  True,  38,  280, None),
            (23, 23, "completed",  True,  70,  250, "problem"),
            (24, 24, "completed",  True,  45,  220, None),
            (25, 25, "completed",  True,  30,  190, "safety"),
            (26, 26, "completed",  True,  85,  150, None),
            (27, 27, "completed",  True,  48,  120, "generic"),
            (28, 28, "completed",  True,  33,  90,  None),
            (29, 29, "completed",  True,  27,  65,  None),
            # --- More in_process ---
            (5,  5,  "in_process", True,  None, 35,  None),
            (8,  8,  "in_process", True,  None, 20,  "operational"),
            (17, 17, "in_process", True,  None, 10,  None),
            # --- More in_transit ---
            (6,  6,  "in_transit", False, None, -5,  None),
            (7,  7,  "in_transit", False, None, -15, None),
            (18, 18, "in_transit", False, None, -25, None),
            (21, 21, "in_transit", False, None, -40, None),
            # --- More canceled ---
            (22, 22, "canceled",   False, None, 100, None),
            (23, 23, "canceled",   False, None, 150, None),
            # --- Peak hour cluster (congestion simulation, 9-10AM) ---
            (24, 20, "completed",  True,  50,  (now - datetime.combine(today, time(9, 10))).seconds // 60, None),
            (25, 21, "completed",  True,  42,  (now - datetime.combine(today, time(9, 25))).seconds // 60, None),
            (26, 22, "completed",  True,  38,  (now - datetime.combine(today, time(9, 40))).seconds // 60, "operational"),
            (27, 23, "completed",  True,  55,  (now - datetime.combine(today, time(9, 55))).seconds // 60, None),
            (28, 24, "completed",  True,  35,  (now - datetime.combine(today, time(10, 5))).seconds // 60, None),
            (29, 25, "completed",  True,  45,  (now - datetime.combine(today, time(10, 20))).seconds // 60, "problem"),
        ]

        for cfg in extra_configs:
            tidx, cidx, status, has_visit, dur, mins, alert_t = cfg
            plate = TRUCKS[tidx][0]
            cargo_def = CARGO_DEFS[cidx]
            driver_idx = tidx % len(drivers)

            bk = _make_booking(db, next_ref(), "inbound" if random.random() > 0.3 else "outbound")
            _make_cargo(db, bk.reference, cargo_def)

            if isinstance(mins, int) and mins > 0:
                sched_time = now - timedelta(minutes=mins)
            elif isinstance(mins, int) and mins <= 0:
                sched_time = now + timedelta(minutes=abs(mins))
            else:
                sched_time = now - timedelta(minutes=int(mins))

            appt = _make_appointment(
                db, bk.reference, drivers[driver_idx], trucks[tidx], terminal,
                gate_in, gate_out, sched_time, status, f"Cargo: {cargo_def[0]}",
            )

            if has_visit:
                delay = random.randint(0, 15)
                entry = sched_time + timedelta(minutes=delay + random.randint(1, 5))
                shift = morning_shift if entry.hour < 14 else afternoon_shift
                v = _make_visit(db, appt, shift, entry, dur)

                if alert_t:
                    alert_descs = {
                        "operational": f"Dock reassignment for {plate}",
                        "problem":     f"Weight discrepancy for {plate} — {cargo_def[0]}",
                        "generic":     f"Documentation verified for {plate}",
                        "safety":      f"Safety check triggered for {plate}",
                    }
                    _make_alert(db, v, appt, shift, entry + timedelta(minutes=random.randint(2, 10)),
                                alert_t, alert_descs.get(alert_t, f"Alert for {plate}"))

                    # Add a second alert to some visits for richer aggregation
                    if random.random() < 0.3:
                        second_type = random.choice(["operational", "generic"])
                        _make_alert(db, v, appt, shift,
                                    entry + timedelta(minutes=random.randint(12, 25)),
                                    second_type, f"Follow-up {second_type} note for {plate}")

            all_appointments.append((appt, trucks[tidx], False, cargo_def[0], status))

        # ---------------------------------------------------------------
        # HISTORICAL DATA: 5 previous days
        # ---------------------------------------------------------------
        print("Creating 5 days of historical data...")
        historical_counts = [10, 12, 8, 11, 9]  # appointments per day (varied)

        for day_offset in range(1, 6):
            d = today - timedelta(days=day_offset)
            count = historical_counts[day_offset - 1]
            sm = shift_map[(gate_in.id, ShiftType.MORNING, d)]
            sa = shift_map[(gate_in.id, ShiftType.AFTERNOON, d)]
            created = _generate_historical_day(
                db, d, trucks, drivers, terminal, gate_in, gate_out, sm, sa, count,
                f"D-{day_offset}"
            )
            print(f"  Day {d}: {created} appointments")

        # ===== COMMIT =====
        print("\nSaving to database...")
        db.commit()

        # ===== SUMMARY =====
        total_completed = sum(1 for _, _, _, _, s in all_appointments if s == "completed")
        total_in_process = sum(1 for _, _, _, _, s in all_appointments if s == "in_process")
        total_in_transit = sum(1 for _, _, _, _, s in all_appointments if s == "in_transit")
        total_canceled = sum(1 for _, _, _, _, s in all_appointments if s == "canceled")
        total_today = len(all_appointments)
        total_historical = sum(historical_counts)

        print("\n" + "=" * 70)
        print("  DATABASE INITIALIZED - PORTO DE AVEIRO REALISTIC")
        print("=" * 70)

        print(f"""
+=====================================================================+
|                        LOGIN CREDENTIALS                             |
+=====================================================================+
|  WEB PORTAL (Operator/Manager):                                      |
|  +----------------------------------+--------------+------------+    |
|  | Email                            | Password     | Role       |    |
|  +----------------------------------+--------------+------------+    |
|  | worker@portodeaveiro.pt          | password123  | Operator   |    |
|  | manager@example.pt               | password123  | Manager    |    |
|  | teresa.lopes@portodeaveiro.pt    | password123  | Manager    |    |
|  +----------------------------------+--------------+------------+    |
|                                                                      |
|  MOBILE APP (Drivers):                                               |
|  +----------------+---------------------+--------------+             |
|  | License        | Name                | Password     |             |
|  +----------------+---------------------+--------------+             |
|  | PT12345678     | Oscar Almeida       | driver123    |             |
|  | PT23456789     | Sofia Rodrigues     | driver123    |             |
|  | ES87654321     | Carlos Garcia Lopez | driver123    |             |
|  | DE11223344     | Hans Mueller        | driver123    |             |
|  | FR99887766     | Pierre Dubois       | driver123    |             |
|  +----------------+---------------------+--------------+             |
+=====================================================================+
""")

        print("+" + "-" * 73 + "+")
        print(f"| {total_today} TODAY APPOINTMENTS: {total_completed} completed, {total_in_process} in_process, "
              f"{total_in_transit} in_transit, {total_canceled} canceled")
        print(f"| +{total_historical} HISTORICAL appointments across 5 previous days")
        print("+" + "-" * 73 + "+")

        print(f"""
+=====================================================================+
|                    HAZMAT DEMO - STAR SCENARIO                       |
+=====================================================================+
|                                                                      |
|  STAR SCENARIO (in_transit — approaching port):                      |
|  Truck 87AX60 | Driver: Oscar Almeida (PT12345678)                  |
|  Cargo: Sulfuric acid (fuming) - 22 tonnes                          |
|  ADR Classification: UN 1831, Kemler X886                            |
|  -> Corrosive, reacts dangerously with water                         |
|                                                                      |
|  Current state:                                                      |
|  1. NO pre-seeded infraction (detected at runtime)                   |
|  2. Arriving at gate in ~15 minutes                                  |
|  3. Status: IN_TRANSIT (awaiting gate entry)                         |
|  4. No visit/alerts yet — truck not at gate                          |
|                                                                      |
|  LIVE DEMO PLATES (still in_transit or in_process):                  |
|  87AX60  -> Sulfuric acid (UN 1831, Kemler X886) - arriving 15 min  |
|  BB11BB  -> Propane (UN 1978, Kemler 23) - arriving in 20 min       |
|  DD33DD  -> Ammonium (UN 1942, Kemler 50) - arriving in 1h          |
|  AA00AA  -> Gasoline (UN 1203, Kemler 33) - in_process now           |
|                                                                      |
|  DASHBOARD METRICS (pre-populated):                                  |
|  - {total_completed} completed + visits + exit times (today)              |
|  - {total_in_process} in_process with active visits                        |
|  - Alerts: safety, operational, problem, generic (diverse)           |
|  - {total_historical} historical appointments across 5 days                |
|  - Volume data, company stats, alert breakdown all populated         |
|                                                                      |
+=====================================================================+
""")

    except Exception as e:
        print(f"\nError during initialization: {e}")
        db.rollback()
        raise


def bootstrap_mongo_projections(database_url: str):
    """
    Bootstrap MongoDB read models from PostgreSQL data.

    After initial seeding, the CQRS read models (MongoDB) are empty because
    no outbox events have been produced yet.  This function projects all
    appointments, drivers, workers, and alerts into MongoDB so the read
    side is immediately consistent with the write side (Guardrail 5).
    """
    try:
        from pymongo import MongoClient
        mongo_url = os.getenv("MONGO_URL", "mongodb://mongo:27017")
        mongo = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        mdb = mongo["intelligent_logistics"]
    except Exception as e:
        print(f"  [WARN] MongoDB not available — skipping projection bootstrap: {e}")
        return

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        from sqlalchemy import text

        # --- Project Appointments ---
        rows = db.execute(text(
            "SELECT id, arrival_id, booking_reference, driver_license, "
            "truck_license_plate, terminal_id, gate_in_id, gate_out_id, "
            "scheduled_start_time, expected_duration, status, notes, highway_infraction "
            "FROM appointment"
        )).fetchall()

        appt_docs = []
        for r in rows:
            doc = {
                "id": r.id,
                "arrival_id": r.arrival_id,
                "booking_reference": r.booking_reference,
                "driver_license": r.driver_license,
                "truck_license_plate": r.truck_license_plate,
                "terminal_id": r.terminal_id,
                "gate_in_id": r.gate_in_id,
                "gate_out_id": r.gate_out_id,
                "scheduled_start_time": r.scheduled_start_time.isoformat() if r.scheduled_start_time else None,
                "expected_duration": r.expected_duration,
                "status": r.status,
                "notes": r.notes,
                "highway_infraction": bool(r.highway_infraction) if r.highway_infraction is not None else False,
                "projected_at": datetime.utcnow(),
            }
            appt_docs.append(doc)

        if appt_docs:
            coll = mdb["appointments_read"]
            coll.delete_many({})
            coll.insert_many(appt_docs)
            print(f"  Projected {len(appt_docs)} appointments to MongoDB")

        # --- Project Drivers ---
        driver_rows = db.execute(text(
            "SELECT drivers_license, name, company_nif, active FROM driver"
        )).fetchall()

        driver_docs = []
        for r in driver_rows:
            driver_docs.append({
                "drivers_license": r.drivers_license,
                "name": r.name,
                "company_nif": r.company_nif,
                "active": bool(r.active),
                "projected_at": datetime.utcnow(),
            })

        if driver_docs:
            coll = mdb["drivers_read"]
            coll.delete_many({})
            coll.insert_many(driver_docs)
            print(f"  Projected {len(driver_docs)} drivers to MongoDB")

        # --- Project Workers ---
        worker_rows = db.execute(text(
            "SELECT num_worker, name, email, phone, active FROM worker"
        )).fetchall()

        worker_docs = []
        for r in worker_rows:
            # Determine role
            mgr = db.execute(text(
                "SELECT num_worker FROM manager WHERE num_worker = :nw"
            ), {"nw": r.num_worker}).fetchone()
            role = "manager" if mgr else "operator"
            worker_docs.append({
                "num_worker": r.num_worker,
                "name": r.name,
                "email": r.email,
                "phone": r.phone,
                "active": bool(r.active),
                "role": role,
                "projected_at": datetime.utcnow(),
            })

        if worker_docs:
            coll = mdb["workers_read"]
            coll.delete_many({})
            coll.insert_many(worker_docs)
            print(f"  Projected {len(worker_docs)} workers to MongoDB")

        # --- Project Alerts ---
        alert_rows = db.execute(text(
            "SELECT id, visit_id, appointment_id, timestamp, type, description FROM alert"
        )).fetchall()

        alert_docs = []
        for r in alert_rows:
            alert_docs.append({
                "id": r.id,
                "visit_id": r.visit_id,
                "appointment_id": r.appointment_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "type": r.type,
                "description": r.description,
                "projected_at": datetime.utcnow(),
            })

        if alert_docs:
            coll = mdb["alerts_read"]
            coll.delete_many({})
            coll.insert_many(alert_docs)
            print(f"  Projected {len(alert_docs)} alerts to MongoDB")

        print("  MongoDB bootstrap projection complete")

    except Exception as e:
        print(f"  [WARN] MongoDB bootstrap projection failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_data(db)
    finally:
        db.close()

    # Bootstrap MongoDB read models so CQRS reads work immediately
    print("\nBootstrapping MongoDB read model projections...")
    bootstrap_mongo_projections(database_url)


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    print(f"\nConnecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)

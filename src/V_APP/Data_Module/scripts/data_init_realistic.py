#!/usr/bin/env python3
"""
Realistic data initializer for Porto de Aveiro demo.
Populates a rich dataset with completed cycles, visits, alerts, and metrics
so the dashboard is immediately populated on first load.

Highlight scenario: truck 87AX60 carrying dangerous goods (UN 1831, Kemler X886)
driven by Rui Almeida — full cycle from in_transit to completed with hazmat alerts.

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
    ("PT12345678", "Rui Almeida", 0),         # HAZMAT driver — main demo protagonist
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
# 87AX60 is the HAZMAT demo star truck
TRUCKS = [
    # === HAZMAT trucks ===
    ("87AX60",    "Volvo FH16",       0),   # STAR: Rui Almeida's hazmat truck
    ("AA-00-AA",  "Scania R500",      0),   # Gasoline
    ("BB-11-BB",  "MAN TGX",          1),   # Propane
    ("CC-22-CC",  "Mercedes Actros",  2),   # Chemical
    ("DD-33-DD",  "DAF XF",           3),   # Ammonium
    # === Normal cargo trucks ===
    ("12-AB-34",  "Volvo FH16",       0),   # Ceramic tiles
    ("56-CD-78",  "Scania R500",      1),   # Cork products
    ("90-EF-12",  "MAN TGX",          2),   # Paper pulp
    ("34-GH-56",  "Mercedes Actros",  0),   # Salt
    ("78-IJ-90",  "DAF XF",           1),   # Fish
    ("1234-ABC",  "Iveco S-Way",      3),   # Wine (Spanish truck)
    ("5678-DEF",  "Volvo FH16",       3),   # Dairy (Spanish truck)
    ("9012-GHI",  "Scania R500",      3),   # Timber (Spanish truck)
    ("B-AB-1234", "MAN TGX",          4),   # Auto parts (German truck)
    ("M-CD-5678", "Mercedes Actros",  4),   # Glass bottles (German truck)
    ("AB-123-CD", "Renault T",        5),   # Frozen seafood (French truck)
    ("EF-456-GH", "Renault T",        5),   # Construction steel (French truck)
    ("23-LM-45",  "Volvo FH16",       0),   # Textile rolls
    ("67-NP-89",  "Scania R500",      1),   # Electronic components
    ("01-QR-23",  "DAF XF",           2),   # General cargo
]

# Cargo types: (description, state, weight_kg, is_hazmat, un_code, kemler_code, origin)
CARGO_DEFS = [
    # HAZMAT cargos (first 5 match first 5 trucks)
    ("Sulfuric acid (fuming)", "liquid", 22000, True, "1831", "X886", "CUF Quimicos Estarreja"),  # 87AX60 STAR
    ("Gasoline ADR",           "liquid", 24000, True, "1203", "33",   "Refinaria Sines"),
    ("Propane cylinders",      "gaseous", 8000, True, "1978", "23",   "Galp Energia"),
    ("Industrial chemicals",   "liquid", 15000, True, "1830", "80",   "CUF Quimicos"),
    ("Ammonium nitrate fert.", "solid",  22000, True, "1942", "50",   "Sapec Agro"),
    # Normal cargos (remaining 15 match remaining 15 trucks)
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
]


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

        # ===== SHIFTS (today + yesterday for historical metrics) =====
        print("Creating shifts...")
        shift_configs = [
            # Today
            (gate_in.id, ShiftType.MORNING,   today, "OPR001", "MGR001"),
            (gate_in.id, ShiftType.AFTERNOON,  today, "OPR002", "MGR001"),
            (gate_in.id, ShiftType.NIGHT,      today, "OPR003", "MGR001"),
            (gate_highway.id, ShiftType.MORNING,   today, "OPR004", "MGR002"),
            (gate_highway.id, ShiftType.AFTERNOON,  today, "OPR004", "MGR002"),
            # Yesterday (for historical data)
            (gate_in.id, ShiftType.MORNING,   today - timedelta(days=1), "OPR001", "MGR001"),
            (gate_in.id, ShiftType.AFTERNOON,  today - timedelta(days=1), "OPR002", "MGR001"),
            (gate_in.id, ShiftType.NIGHT,      today - timedelta(days=1), "OPR003", "MGR001"),
        ]
        shifts = []
        for gid, stype, sdate, opr, mgr in shift_configs:
            s = Shift(gate_id=gid, shift_type=stype, date=sdate,
                      operator_num_worker=opr, manager_num_worker=mgr)
            shifts.append(s)
        db.add_all(shifts)
        db.flush()

        # Helper: find today's morning shift for gate_in
        morning_shift = next(s for s in shifts if s.gate_id == gate_in.id and s.shift_type == ShiftType.MORNING and s.date == today)
        afternoon_shift = next(s for s in shifts if s.gate_id == gate_in.id and s.shift_type == ShiftType.AFTERNOON and s.date == today)
        yesterday_morning = next(s for s in shifts if s.gate_id == gate_in.id and s.shift_type == ShiftType.MORNING and s.date == today - timedelta(days=1))
        yesterday_afternoon = next(s for s in shifts if s.gate_id == gate_in.id and s.shift_type == ShiftType.AFTERNOON and s.date == today - timedelta(days=1))

        # =====================================================================
        # BOOKINGS, CARGOS & APPOINTMENTS
        # =====================================================================
        print("Creating 20 appointments with varied statuses...")

        all_appointments = []

        # ---------------------------------------------------------------
        # APPOINTMENT 0: 87AX60 — FULL HAZMAT CYCLE (completed)
        # Rui Almeida, Sulfuric acid fuming, UN 1831, Kemler X886
        # This is THE demo scenario — arrived 2h ago, processed, completed
        # ---------------------------------------------------------------
        bk0 = Booking(reference=f"AVR-{today.strftime('%Y%m%d')}-0001", direction="inbound")
        db.add(bk0)
        db.flush()

        cargo0 = Cargo(
            booking_reference=bk0.reference,
            quantity=Decimal("22000"),
            state="liquid",
            description="Sulfuric acid (fuming) [UN:1831, Kemler:X886] - Origin: CUF Quimicos Estarreja"
        )
        db.add(cargo0)
        db.flush()

        appt0_time = now - timedelta(hours=2, minutes=15)
        appt0 = Appointment(
            booking_reference=bk0.reference,
            driver_license="PT12345678",  # Rui Almeida
            truck_license_plate="87AX60",
            terminal_id=terminal.id,
            gate_in_id=gate_in.id,
            gate_out_id=gate_out.id,
            scheduled_start_time=appt0_time,
            expected_duration=60,
            status="completed",
            notes="HAZMAT: Sulfuric acid (fuming) [UN:1831, Kemler:X886] - COMPLETE CYCLE",
            highway_infraction=True,  # flagged on highway approach
        )
        db.add(appt0)
        db.flush()

        # Visit for 87AX60 — arrived, processed, departed
        visit0_entry = appt0_time + timedelta(minutes=5)
        visit0_exit = visit0_entry + timedelta(minutes=52)
        visit0 = Visit(
            appointment_id=appt0.id,
            shift_gate_id=morning_shift.gate_id,
            shift_type=morning_shift.shift_type,
            shift_date=morning_shift.date,
            entry_time=visit0_entry,
            out_time=visit0_exit,
            state="completed"
        )
        db.add(visit0)
        db.flush()

        # Alerts for 87AX60 hazmat
        alert0a = Alert(
            visit_id=visit0.appointment_id,
            appointment_id=appt0.id,
            timestamp=visit0_entry + timedelta(minutes=1),
            type="safety",
            description="Hazardous cargo detected | UN 1831 - Sulfuric acid (fuming) | Class: 8 | Hazard: Corrosive, reacts dangerously with water | Kemler X886: Corrosive - reacts with water"
        )
        alert0b = Alert(
            visit_id=visit0.appointment_id,
            appointment_id=appt0.id,
            timestamp=visit0_entry + timedelta(minutes=2),
            type="operational",
            description="Highway infraction confirmed for truck 87AX60 — hazmat vehicle on restricted A25 route, Kemler X886 / UN 1831"
        )
        alert0c = Alert(
            visit_id=visit0.appointment_id,
            appointment_id=appt0.id,
            timestamp=visit0_entry + timedelta(minutes=30),
            type="safety",
            description="ADR safety check completed for 87AX60 — emergency equipment verified, placards confirmed X886/1831"
        )
        db.add_all([alert0a, alert0b, alert0c])
        db.flush()

        # ShiftAlertHistory for 87AX60 alerts
        for alert in [alert0a, alert0b, alert0c]:
            db.add(ShiftAlertHistory(
                shift_gate_id=morning_shift.gate_id,
                shift_type=morning_shift.shift_type,
                shift_date=morning_shift.date,
                alert_id=alert.id
            ))
        db.flush()

        all_appointments.append((appt0, trucks[0], True, CARGO_DEFS[0][0], "completed"))

        # ---------------------------------------------------------------
        # APPOINTMENTS 1-4: Other HAZMAT trucks — mixed statuses
        # ---------------------------------------------------------------
        hazmat_statuses = [
            # (status, has_visit, visit_completed, minutes_ago, duration_min)
            ("in_process", True,  False, 45, None),     # AA-00-AA: currently being processed
            ("in_transit", False, False, -20, None),     # BB-11-BB: arriving in 20 min
            ("completed",  True,  True,  180, 38),       # CC-22-CC: completed 3h ago
            ("in_transit", False, False, -60, None),     # DD-33-DD: arriving in 1h
        ]

        for i in range(1, 5):
            plate, brand, cidx = TRUCKS[i]
            desc, state, weight, _, un, kemler, origin = CARGO_DEFS[i]
            status_info = hazmat_statuses[i - 1]
            appt_status, has_visit, visit_done, mins_ago, dur = status_info

            bk = Booking(reference=f"AVR-{today.strftime('%Y%m%d')}-{i+1:04d}", direction="inbound")
            db.add(bk)
            db.flush()

            cargo = Cargo(
                booking_reference=bk.reference,
                quantity=Decimal(str(weight)),
                state=state,
                description=f"{desc} [UN:{un}, Kemler:{kemler}] - Origin: {origin}"
            )
            db.add(cargo)
            db.flush()

            sched_time = now - timedelta(minutes=mins_ago) if mins_ago > 0 else now + timedelta(minutes=abs(mins_ago))
            driver_idx = i % len(drivers)

            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[driver_idx].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal.id,
                gate_in_id=gate_in.id,
                gate_out_id=gate_out.id if visit_done else None,
                scheduled_start_time=sched_time,
                expected_duration=45,
                status=appt_status,
                notes=f"HAZMAT: {desc} [UN:{un}, Kemler:{kemler}]",
                highway_infraction=(i == 1),  # AA-00-AA flagged
            )
            db.add(appt)
            db.flush()

            if has_visit:
                entry = sched_time + timedelta(minutes=3)
                v = Visit(
                    appointment_id=appt.id,
                    shift_gate_id=morning_shift.gate_id,
                    shift_type=morning_shift.shift_type,
                    shift_date=morning_shift.date,
                    entry_time=entry,
                    out_time=entry + timedelta(minutes=dur) if visit_done and dur else None,
                    state="completed" if visit_done else "unloading"
                )
                db.add(v)
                db.flush()

                # Safety alert for hazmat
                ha = Alert(
                    visit_id=v.appointment_id,
                    appointment_id=appt.id,
                    timestamp=entry + timedelta(minutes=1),
                    type="safety",
                    description=f"Hazardous cargo detected | UN {un} - {desc} | Kemler {kemler}"
                )
                db.add(ha)
                db.flush()
                db.add(ShiftAlertHistory(
                    shift_gate_id=morning_shift.gate_id,
                    shift_type=morning_shift.shift_type,
                    shift_date=morning_shift.date,
                    alert_id=ha.id
                ))
                db.flush()

            all_appointments.append((appt, trucks[i], True, desc, appt_status))

        # ---------------------------------------------------------------
        # APPOINTMENTS 5-19: Normal cargo — rich mix of statuses
        # Creates visits, alerts, and completed cycles for dashboard metrics
        # ---------------------------------------------------------------
        normal_configs = [
            # (truck_idx, cargo_idx, status, has_visit, visit_done, mins_offset, dur, alert_type)
            (5,  5,  "completed",  True,  True,  240, 35, None),          # 12-AB-34: completed 4h ago
            (6,  6,  "completed",  True,  True,  200, 28, None),          # 56-CD-78: completed
            (7,  7,  "completed",  True,  True,  160, 42, "operational"), # 90-EF-12: completed + alert
            (8,  8,  "completed",  True,  True,  130, 31, None),          # 34-GH-56: completed
            (9,  9,  "in_process", True,  False, 25,  None, None),        # 78-IJ-90: being processed
            (10, 10, "in_process", True,  False, 15,  None, "problem"),   # 1234-ABC: processing + issue
            (11, 11, "completed",  True,  True,  300, 40, None),          # 5678-DEF: completed (yesterday overflow)
            (12, 12, "in_transit", False, False, -10, None, None),        # 9012-GHI: arriving 10min
            (13, 13, "in_transit", False, False, -30, None, None),        # B-AB-1234: arriving 30min
            (14, 14, "in_transit", False, False, -45, None, None),        # M-CD-5678: arriving 45min
            (15, 15, "in_transit", False, False, -70, None, None),        # AB-123-CD: arriving 70min
            (16, 16, "in_transit", False, False, -90, None, None),        # EF-456-GH: arriving 90min
            (17, 17, "completed",  True,  True,  100, 25, None),          # 23-LM-45: completed
            (18, 18, "completed",  True,  True,  80,  33, "generic"),     # 67-NP-89: completed + alert
            (19, 19, "canceled",   False, False, 60,  None, None),        # 01-QR-23: canceled
        ]

        for cfg in normal_configs:
            tidx, cidx, status, has_visit, visit_done, mins, dur, alert_t = cfg
            plate, brand, comp_idx = TRUCKS[tidx]
            desc, st, weight, _, un, kemler, origin = CARGO_DEFS[cidx]
            driver_idx = tidx % len(drivers)

            bk = Booking(
                reference=f"AVR-{today.strftime('%Y%m%d')}-{tidx+1:04d}",
                direction="inbound" if tidx % 3 != 0 else "outbound"
            )
            db.add(bk)
            db.flush()

            cargo = Cargo(
                booking_reference=bk.reference,
                quantity=Decimal(str(weight)),
                state=st,
                description=f"{desc} - Origin: {origin}"
            )
            db.add(cargo)
            db.flush()

            if mins > 0:
                sched_time = now - timedelta(minutes=mins)
            else:
                sched_time = now + timedelta(minutes=abs(mins))

            appt = Appointment(
                booking_reference=bk.reference,
                driver_license=drivers[driver_idx].drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal.id,
                gate_in_id=gate_in.id,
                gate_out_id=gate_out.id if visit_done else None,
                scheduled_start_time=sched_time,
                expected_duration=45,
                status=status,
                notes=f"Cargo: {desc}",
            )
            db.add(appt)
            db.flush()

            if has_visit:
                entry = sched_time + timedelta(minutes=random.randint(2, 8))
                shift = morning_shift if entry.hour < 14 else afternoon_shift
                v = Visit(
                    appointment_id=appt.id,
                    shift_gate_id=shift.gate_id,
                    shift_type=shift.shift_type,
                    shift_date=shift.date,
                    entry_time=entry,
                    out_time=entry + timedelta(minutes=dur) if visit_done and dur else None,
                    state="completed" if visit_done else "unloading"
                )
                db.add(v)
                db.flush()

                if alert_t:
                    alert_descs = {
                        "operational": f"Dock assignment delay for {plate} — manual reassignment needed",
                        "problem":     f"Weight discrepancy for {plate} — cargo {desc} exceeds declared weight by 800kg",
                        "generic":     f"Documentation check for {plate} — CMR waybill verified",
                    }
                    a = Alert(
                        visit_id=v.appointment_id,
                        appointment_id=appt.id,
                        timestamp=entry + timedelta(minutes=5),
                        type=alert_t,
                        description=alert_descs.get(alert_t, f"Alert for {plate}")
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

            all_appointments.append((appt, trucks[tidx], False, desc, status))

        # ---------------------------------------------------------------
        # YESTERDAY'S HISTORICAL APPOINTMENTS (for dashboard trend data)
        # 8 completed appointments from yesterday
        # ---------------------------------------------------------------
        print("Creating yesterday's historical data (8 completed appointments)...")
        yesterday = today - timedelta(days=1)
        yesterday_base = datetime.combine(yesterday, time(8, 0))

        for h in range(8):
            bk = Booking(
                reference=f"AVR-{yesterday.strftime('%Y%m%d')}-{h+1:04d}",
                direction="inbound"
            )
            db.add(bk)
            db.flush()

            cidx = (h + 5) % len(CARGO_DEFS)
            desc, st, weight, _, _, _, origin = CARGO_DEFS[cidx]
            cargo = Cargo(
                booking_reference=bk.reference,
                quantity=Decimal(str(weight)),
                state=st,
                description=f"{desc} - Origin: {origin}"
            )
            db.add(cargo)
            db.flush()

            sched = yesterday_base + timedelta(hours=h, minutes=random.randint(0, 30))
            tidx = (h + 5) % len(trucks)
            didx = h % len(drivers)

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
                notes=f"[HIST] Cargo: {desc}",
            )
            db.add(appt)
            db.flush()

            entry = sched + timedelta(minutes=random.randint(1, 10))
            dur_h = random.randint(25, 55)
            shift_h = yesterday_morning if entry.hour < 14 else yesterday_afternoon
            v = Visit(
                appointment_id=appt.id,
                shift_gate_id=shift_h.gate_id,
                shift_type=shift_h.shift_type,
                shift_date=shift_h.date,
                entry_time=entry,
                out_time=entry + timedelta(minutes=dur_h),
                state="completed"
            )
            db.add(v)
            db.flush()

        # ===== COMMIT =====
        print("\nSaving to database...")
        db.commit()

        # ===== SUMMARY =====
        total_completed = sum(1 for _, _, _, _, s in all_appointments if s == "completed")
        total_in_process = sum(1 for _, _, _, _, s in all_appointments if s == "in_process")
        total_in_transit = sum(1 for _, _, _, _, s in all_appointments if s == "in_transit")
        total_canceled = sum(1 for _, _, _, _, s in all_appointments if s == "canceled")

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
|  | PT12345678     | Rui Almeida         | driver123    |             |
|  | PT23456789     | Sofia Rodrigues     | driver123    |             |
|  | ES87654321     | Carlos Garcia Lopez | driver123    |             |
|  | DE11223344     | Hans Mueller        | driver123    |             |
|  | FR99887766     | Pierre Dubois       | driver123    |             |
|  +----------------+---------------------+--------------+             |
+=====================================================================+
""")

        print("+" + "-" * 73 + "+")
        print(f"| 20 TODAY APPOINTMENTS: {total_completed} completed, {total_in_process} in_process, "
              f"{total_in_transit} in_transit, {total_canceled} canceled |")
        print("| +8 YESTERDAY completed (historical metrics)                          |")
        print("+" + "-" * 73 + "+")
        print("| #  | PIN        | Plate       | Status      | Cargo                  |")
        print("+" + "-" * 73 + "+")

        for i, (appt, truck, is_hazmat, desc, status) in enumerate(all_appointments):
            pin = appt.arrival_id or f"PRT-{i+1:04d}"
            hazmat_flag = "[HZ]" if is_hazmat else "    "
            cargo_short = desc[:20] if len(desc) <= 20 else desc[:17] + "..."
            status_short = status[:11]
            print(f"| {i+1:2} | {pin:<10} | {truck.license_plate:<11} | {status_short:<11} | {hazmat_flag} {cargo_short:<17} |")

        print("+" + "-" * 73 + "+")

        print(f"""
+=====================================================================+
|                    HAZMAT DEMO - COMPLETE CYCLE                      |
+=====================================================================+
|                                                                      |
|  STAR SCENARIO (already completed in DB):                            |
|  Truck 87AX60 | Driver: Rui Almeida (PT12345678)                    |
|  Cargo: Sulfuric acid (fuming) - 22 tonnes                          |
|  ADR Classification: UN 1831, Kemler X886                            |
|  -> Corrosive, reacts dangerously with water                         |
|                                                                      |
|  Timeline (pre-populated):                                           |
|  1. Scheduled arrival: ~2h15min ago                                  |
|  2. Highway infraction flagged (A25 restricted route)                |
|  3. Gate entry: 5 min after schedule                                 |
|  4. Safety alert: Hazmat detected (UN 1831 / X886)                   |
|  5. Operational alert: Highway infraction confirmed                  |
|  6. ADR safety check completed (30 min after entry)                  |
|  7. Departure: 52 min after entry                                    |
|  8. Status: COMPLETED                                                |
|                                                                      |
|  LIVE DEMO PLATES (still in_transit or in_process):                  |
|  BB-11-BB -> Propane (UN 1978, Kemler 23) - arriving in 20 min      |
|  DD-33-DD -> Ammonium (UN 1942, Kemler 50) - arriving in 1h         |
|  AA-00-AA -> Gasoline (UN 1203, Kemler 33) - in_process now         |
|                                                                      |
|  DASHBOARD METRICS (pre-populated):                                  |
|  - 8 completed + visits + exit times (today)                         |
|  - 2 in_process with active visits                                   |
|  - 6 safety/operational/problem alerts                               |
|  - 8 historical appointments from yesterday                          |
|  - Volume data, company stats, alert breakdown all populated         |
|                                                                      |
+=====================================================================+
""")

    except Exception as e:
        print(f"\nError during initialization: {e}")
        db.rollback()
        raise


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    print(f"\nConnecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)

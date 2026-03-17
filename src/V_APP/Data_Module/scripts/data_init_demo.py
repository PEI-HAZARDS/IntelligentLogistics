#!/usr/bin/env python3
"""
Demo data initializer for PEI 2025 presentation.

Video1 plates → Gate 1 (Decision Engine / port entry)
Video2 plates → Gate Highway (Infraction Engine / highway approach)

Run with:
    python scripts/data_init_demo.py
"""

from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from Data_Module.models.sql_models import (
        Base, Worker, Manager, Operator, Company, Driver,
        Truck, Terminal, Dock, Gate, Shift, ShiftType,
        Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
    )
except Exception:
    try:
        from models.sql_models import (
            Base, Worker, Manager, Operator, Company, Driver,
            Truck, Terminal, Dock, Gate, Shift, ShiftType,
            Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
        )
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ──────────────────────────────────────────────────────────────────────────────
# Video1 → Decision Engine (Gate 1 — Port entry)
# Format: normalized OCR output (no spaces, no hyphens) — must match exactly
# what the AI pipeline delivers to Data_Module after PlateMatcher resolves it.
#
# Original plates in video → OCR reads:
#   "1-HEU-148"  → 1HEU148
#   "68-BSH-8"   → 68BSH8
#   "PEI 2025"   → PEI2025
#   "LN67 OIZ"   → LN67OIZGB  (GB suffix added by UK plate reader)
#   "92-BLN-3"   → 92BLN3
#   "83-BTN-5"   → 83BTN5
# ──────────────────────────────────────────────────────────────────────────────
VIDEO1_PLATES = [
    "87AX60",  #1HEU148
    "68BSH8",
    "PEI2025",
    "LN67OIZGB",
    "92BLN3",
    "82BTN5",
]

# ──────────────────────────────────────────────────────────────────────────────
# Video2 → Infraction Engine (Gate Highway — highway approach)
# Trucks on the highway without prior appointment — infraction detection
# ──────────────────────────────────────────────────────────────────────────────
VIDEO2_PLATES = [
    "321BI13",     # 1
    "GGAB425",   # 2
    "SLJP1523",   # 3
    "CA93896",     # 4
]

# Cargo types: (description, state, weight_kg, is_hazmat, un_code, kemler_code)
CARGO_TYPES = [
    ("Gasoline fuel",        "liquid", 18000, True,  "1203", "33"),
    ("Propane gas",          "gaseous", 5000, True,  "1978", "23"),
    ("Sulfuric acid",        "liquid", 12000, True,  "1830", "80"),
    ("Ammonium nitrate",     "solid",  20000, True,  "1942", "50"),
    ("Toxic pesticides",     "liquid",  8000, True,  "2902", "60"),
    ("Auto parts",           "solid",   8000, False, None,   None),
    ("Electronic equipment", "solid",   5500, False, None,   None),
    ("Furniture",            "solid",   9000, False, None,   None),
    ("Construction material","solid",  16000, False, None,   None),
    ("Textile products",     "solid",   6000, False, None,   None),
]


def init_demo_data(db: Session):
    print("=" * 60)
    print("  PEI 2025 DEMO DATA INITIALIZER")
    print("=" * 60)

    if db.query(Worker).first():
        print("\n⚠️  Data already exists. Skipping initialization.")
        print("   To reset: docker compose down -v && docker compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ── Workers ──────────────────────────────────────────────
        print("\n📋 Creating workers...")
        manager = Worker(
            num_worker="MGR001", name="João Silva",
            email="manager@example.pt", phone="910000001",
            password_hash=pwd_context.hash("password123"), active=True
        )
        operator = Worker(
            num_worker="OPR001", name="Maria Vicente",
            email="worker@porto.pt", phone="910000002",
            password_hash=pwd_context.hash("password123"), active=True
        )
        db.add_all([manager, operator])
        db.flush()
        db.add_all([
            Manager(num_worker=manager.num_worker, access_level="admin"),
            Operator(num_worker=operator.num_worker),
        ])
        db.flush()

        # ── Companies ────────────────────────────────────────────
        print("🏢 Creating companies...")
        companies = [
            Company(nif="500123456", name="TransPortugal Lda", contact="220123456"),
            Company(nif="500789012", name="EuroTrans SA",       contact="220789012"),
            Company(nif="500345678", name="Iberian Logistics",  contact="220345678"),
        ]
        db.add_all(companies)
        db.flush()

        # ── Driver ───────────────────────────────────────────────
        print("🚚 Creating driver...")
        driver = Driver(
            drivers_license="PT12345678", name="Rui Almeida",
            company_nif=companies[0].nif,
            password_hash=pwd_context.hash("driver123"), active=True
        )
        db.add(driver)
        db.flush()

        # ── Trucks ───────────────────────────────────────────────
        all_plates = VIDEO1_PLATES + VIDEO2_PLATES
        print(f"🚛 Creating {len(all_plates)} trucks ({len(VIDEO1_PLATES)} gate + {len(VIDEO2_PLATES)} highway)...")
        trucks = {}
        for i, plate in enumerate(all_plates):
            t = Truck(
                license_plate=plate,
                brand=["Volvo", "Scania", "MAN", "Mercedes", "DAF"][i % 5],
                company_nif=companies[i % len(companies)].nif,
            )
            db.add(t)
            trucks[plate] = t
        db.flush()

        # ── Terminal ─────────────────────────────────────────────
        print("🏭 Creating terminal...")
        terminal = Terminal(
            name="Terminal Norte",
            latitude=Decimal("40.6443"),
            longitude=Decimal("-8.6456"),
            hazmat_approved=True
        )
        db.add(terminal)
        db.flush()

        # ── Docks ────────────────────────────────────────────────
        docks = [
            Dock(terminal_id=terminal.id, bay_number="DOCK-A1",
                 latitude=Decimal("40.6440"), longitude=Decimal("-8.6450"),
                 current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="DOCK-A2",
                 latitude=Decimal("40.6441"), longitude=Decimal("-8.6451"),
                 current_usage="operational"),
        ]
        db.add_all(docks)
        db.flush()

        # ── Gates ────────────────────────────────────────────────
        print("🚪 Creating gates...")
        # Gate 1 — Decision Engine (port entry, Video1)
        gate_entry = Gate(label="Gate 1 - Entrada Norte",
                          latitude=Decimal("40.6450"), longitude=Decimal("-8.6460"))
        # Gate 2 — Infraction Engine (Video2)
        gate_highway = Gate(label="Gate 2 - Abordagem A1",
                            latitude=Decimal("40.6500"), longitude=Decimal("-8.6500"))
        db.add_all([gate_entry, gate_highway])
        db.flush()

        # ── Shifts ───────────────────────────────────────────────
        print("📅 Creating shifts...")
        for shift_type in [ShiftType.MORNING, ShiftType.AFTERNOON, ShiftType.NIGHT]:
            db.add(Shift(
                gate_id=gate_entry.id,
                shift_type=shift_type,
                date=today,
                operator_num_worker=operator.num_worker,
                manager_num_worker=manager.num_worker,
            ))
        db.flush()

        # ── Appointments — Video1 (Gate 1 / Decision Engine) ─────
        print(f"\n📦 Creating {len(VIDEO1_PLATES)} appointments for Gate 1 (Video1)...")
        v1_appointments = []
        for i, plate in enumerate(VIDEO1_PLATES):
            cargo_desc, state, weight, is_hazmat, un_code, kemler = CARGO_TYPES[i % len(CARGO_TYPES)]

            booking = Booking(
                reference=f"BK-G1-{today.strftime('%Y%m%d')}-{i+1:04d}",
                direction="inbound"
            )
            db.add(booking)
            db.flush()

            cargo = Cargo(
                booking_reference=booking.reference,
                quantity=Decimal(str(weight)),
                state=state,
                description=cargo_desc if not is_hazmat else f"{cargo_desc} [UN:{un_code}, Kemler:{kemler}]"
            )
            db.add(cargo)
            db.flush()

            scheduled_time = now + timedelta(minutes=-5 + (10 * i))
            appt = Appointment(
                booking_reference=booking.reference,
                driver_license=driver.drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal.id,
                gate_in_id=gate_entry.id,
                gate_out_id=None,
                scheduled_start_time=scheduled_time,
                expected_duration=45,
                status="in_transit",
                notes=f"HAZMAT: {cargo_desc} [UN:{un_code}]" if is_hazmat else f"Cargo: {cargo_desc}",
                highway_infraction=False,
            )
            db.add(appt)
            db.flush()
            v1_appointments.append((appt, trucks[plate], is_hazmat, cargo_desc))

        # ── Appointments — Video2 (Highway / Infraction Engine) ──
        print(f"📦 Creating {len(VIDEO2_PLATES)} appointments for Highway gate (Video2)...")
        v2_appointments = []
        for i, plate in enumerate(VIDEO2_PLATES):
            cargo_desc, state, weight, is_hazmat, un_code, kemler = CARGO_TYPES[i % len(CARGO_TYPES)]

            booking = Booking(
                reference=f"BK-HW-{today.strftime('%Y%m%d')}-{i+1:04d}",
                direction="inbound"
            )
            db.add(booking)
            db.flush()

            cargo = Cargo(
                booking_reference=booking.reference,
                quantity=Decimal(str(weight)),
                state=state,
                description=cargo_desc if not is_hazmat else f"{cargo_desc} [UN:{un_code}, Kemler:{kemler}]"
            )
            db.add(cargo)
            db.flush()

            scheduled_time = now + timedelta(minutes=30 * i)
            appt = Appointment(
                booking_reference=booking.reference,
                driver_license=driver.drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal.id,
                gate_in_id=gate_highway.id,
                gate_out_id=None,
                scheduled_start_time=scheduled_time,
                expected_duration=45,
                status="in_transit",
                notes=f"Highway approach — HAZMAT: {cargo_desc} [UN:{un_code}]" if is_hazmat else f"Highway approach — Cargo: {cargo_desc}",
                highway_infraction=is_hazmat,  # flag infraction for hazmat
            )
            db.add(appt)
            db.flush()
            v2_appointments.append((appt, trucks[plate], is_hazmat, cargo_desc))

        # ── Commit ───────────────────────────────────────────────
        print("\n💾 Saving to database...")
        db.commit()

        # ── Summary ──────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("  ✅ PEI 2025 DEMO DATABASE INITIALIZED")
        print("=" * 70)

        print("""
┌─────────────────────────────────────────────────────────────────────┐
│                        LOGIN CREDENTIALS                             │
├─────────────────────────────────────────────────────────────────────┤
│  WEB PORTAL:                                                         │
│    worker@porto.pt      │ password123  │ Operator                   │
│    manager@example.pt   │ password123  │ Manager                    │
│  MOBILE APP (Driver):                                                │
│    PT12345678           │ driver123                                  │
└─────────────────────────────────────────────────────────────────────┘
""")

        print("┌" + "─" * 68 + "┐")
        print("│  VIDEO1 — GATE 1 — Decision Engine                               │")
        print("├──────┬───────────────┬──────────────┬──────────────────────────┤")
        print("│  #   │ License Plate │ Scheduled    │ Cargo                    │")
        print("├──────┼───────────────┼──────────────┼──────────────────────────┤")
        for i, (appt, truck, is_hazmat, desc) in enumerate(v1_appointments):
            t = appt.scheduled_start_time.strftime('%H:%M') if appt.scheduled_start_time else '--:--'
            flag = "⚠️ " if is_hazmat else "   "
            print(f"│ {i+1:2}   │ {truck.license_plate:<13} │ {t:<12} │ {flag}{desc[:22]:<23} │")
        print("└──────┴───────────────┴──────────────┴──────────────────────────┘")

        print()
        print("┌" + "─" * 68 + "┐")
        print("│  VIDEO2 — GATE 2 — Infraction Engine                             │")
        print("├──────┬───────────────┬──────────────┬──────────────────────────┤")
        print("│  #   │ License Plate │ Scheduled    │ Cargo                    │")
        print("├──────┼───────────────┼──────────────┼──────────────────────────┤")
        for i, (appt, truck, is_hazmat, desc) in enumerate(v2_appointments):
            t = appt.scheduled_start_time.strftime('%H:%M') if appt.scheduled_start_time else '--:--'
            flag = "⚠️ " if is_hazmat else "   "
            print(f"│ {i+1:2}   │ {truck.license_plate:<13} │ {t:<12} │ {flag}{desc[:22]:<23} │")
        print("└──────┴───────────────┴──────────────┴──────────────────────────┘")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        db.rollback()
        raise


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_demo_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    print(f"\n🔗 Connecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)

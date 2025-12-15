#!/usr/bin/env python3
"""
Simple data initializer for MVP demo.
Creates 20 appointments with unique license plates - all in_transit for demo flow.
Run with: python scripts/data_init_sample.py
"""

from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import os
import sys

# Add parent directory to path so we can import models
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Try to import models from package path
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

# 20 unique license plates for MVP demo (1 plate = 1 appointment)
# Mostly your existing platesfrom video test + extras to complete 20
LICENSE_PLATES = [
    # Your existing plates (11 plates)
    "VKTH76",     # 1 - HAZMAT TEST (use for hazmat demo)
    "SL06173",    # 2 - HAZMAT
    "KHTS141",    # 3 - HAZMAT
    "SLS06408",   # 4 - HAZMAT
    "WNDSU600",   # 5 - HAZMAT
    "MZGOH112",   # 6
    "MZGOH89",    # 7
    "BC8003",     # 8
    "AE66LR",     # 9
    "AA12DF",     # 10
    "BI00US",     # 11
    # Additional plates to complete 20
    "12-AB-34",   # 12 - Portuguese format
    "56-CD-78",   # 13 - Portuguese format
    "90-EF-12",   # 14 - Portuguese format
    "1234-ABC",   # 15 - Spanish format
    "5678-DEF",   # 16 - Spanish format
    "B-AB-1234",  # 17 - German format
    "AB-123-CD",  # 18 - French format
    "34-GH-56",   # 19 - Portuguese format
    "78-IJ-90",   # 20 - Portuguese format
]


# Cargo types with hazmat flags for demo
# Format: (description, state, weight_kg, is_hazmat, un_code, kemler_code)
CARGO_TYPES = [
    # HAZMAT cargos (first 5 - for hazmat detection demo)
    ("Gasoline fuel", "liquid", 18000, True, "1203", "33"),           # Flammable liquid
    ("Propane gas cylinders", "gaseous", 5000, True, "1978", "23"),   # Flammable gas
    ("Sulfuric acid", "liquid", 12000, True, "1830", "80"),           # Corrosive
    ("Ammonium nitrate", "solid", 20000, True, "1942", "50"),         # Oxidizer
    ("Toxic pesticides", "liquid", 8000, True, "2902", "60"),         # Toxic
    # Normal cargos (remaining 15)
    ("Auto parts", "solid", 8000, False, None, None),
    ("Electronic equipment", "solid", 5500, False, None, None),
    ("Furniture", "solid", 9000, False, None, None),
    ("Construction materials", "solid", 16000, False, None, None),
    ("Textile products", "solid", 6000, False, None, None),
    ("Industrial machinery", "solid", 19000, False, None, None),
    ("Frozen meat (refrigerated)", "solid", 18000, False, None, None),
    ("Pharmaceutical products", "solid", 5000, False, None, None),
    ("Wheat cereals", "solid", 22000, False, None, None),
    ("Industrial sand", "solid", 25000, False, None, None),
    ("Wine and beverages", "liquid", 12000, False, None, None),
    ("Olive oil", "liquid", 9500, False, None, None),
    ("Fresh vegetables", "solid", 14000, False, None, None),
    ("Paper products", "solid", 11000, False, None, None),
    ("Ceramic tiles", "solid", 24000, False, None, None),
]


def init_simple_data(db: Session):
    """
    Initialize database with MVP demo data.
    20 appointments, 1 unique plate each, ALL in_transit status.
    """
    print("=" * 60)
    print("  MVP DEMO DATA INITIALIZER")
    print("=" * 60)

    # Check if data already exists
    if db.query(Worker).first():
        print("\n⚠️  Data already exists. Skipping initialization.")
        print("   To reset, run: docker-compose down -v && docker-compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ===== WORKERS =====
        print("\n📋 Creating workers...")

        manager = Worker(
            num_worker="MGR001",
            name="João Silva",
            email="joao.silva@porto.pt",
            phone="910000001",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        operator = Worker(
            num_worker="OPR001",
            name="Maria Vicente",
            email="worker@porto.pt",
            phone="910000002",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        db.add_all([manager, operator])
        db.flush()

        manager_obj = Manager(num_worker=manager.num_worker, access_level="admin")
        operator_obj = Operator(num_worker=operator.num_worker)
        db.add_all([manager_obj, operator_obj])
        db.flush()

        # ===== COMPANIES =====
        print("🏢 Creating transport companies...")

        companies = [
            Company(nif="500123456", name="TransPortugal Lda", contact="220123456"),
            Company(nif="500789012", name="EuroTrans SA", contact="220789012"),
            Company(nif="500345678", name="Iberian Logistics", contact="220345678"),
        ]
        db.add_all(companies)
        db.flush()

        # ===== DRIVERS =====
        print("🚚 Creating drivers...")

        drivers = [
            Driver(
                drivers_license="PT12345678",
                name="Rui Almeida",
                company_nif=companies[0].nif,
                password_hash=pwd_context.hash("driver123"),
                active=True
            ),
            Driver(
                drivers_license="ES87654321",
                name="Carlos García",
                company_nif=companies[1].nif,
                password_hash=pwd_context.hash("driver123"),
                active=True
            ),
            Driver(
                drivers_license="DE11223344",
                name="Hans Müller",
                company_nif=companies[2].nif,
                password_hash=pwd_context.hash("driver123"),
                active=True
            ),
        ]
        db.add_all(drivers)
        db.flush()

        # ===== TRUCKS (20 unique plates) =====
        print("🚛 Creating 20 trucks with unique plates...")

        trucks = []
        for i, plate in enumerate(LICENSE_PLATES):
            company_idx = i % len(companies)
            trucks.append(Truck(
                license_plate=plate,
                brand=["Volvo", "Scania", "MAN", "Mercedes", "DAF"][i % 5],
                company_nif=companies[company_idx].nif
            ))
        db.add_all(trucks)
        db.flush()

        # ===== TERMINAL =====
        print("🏭 Creating terminal...")

        terminal = Terminal(
            name="Terminal Norte - Porto de Aveiro",
            latitude=Decimal("40.6443"),
            longitude=Decimal("-8.6456"),
            hazmat_approved=True
        )
        db.add(terminal)
        db.flush()

        # ===== DOCKS =====
        print("🔧 Creating docks...")

        docks = [
            Dock(terminal_id=terminal.id, bay_number="DOCK-A1", latitude=Decimal("40.6440"), longitude=Decimal("-8.6450"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="DOCK-A2", latitude=Decimal("40.6441"), longitude=Decimal("-8.6451"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="DOCK-B1", latitude=Decimal("40.6442"), longitude=Decimal("-8.6452"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="DOCK-B2", latitude=Decimal("40.6443"), longitude=Decimal("-8.6453"), current_usage="operational"),
        ]
        db.add_all(docks)
        db.flush()

        # ===== GATES =====
        print("🚪 Creating gates...")

        gate_in = Gate(label="Gate 1 - Entrada Norte", latitude=Decimal("40.6450"), longitude=Decimal("-8.6460"))
        gate_out = Gate(label="Gate 2 - Saída Sul", latitude=Decimal("40.6430"), longitude=Decimal("-8.6440"))
        db.add_all([gate_in, gate_out])
        db.flush()

        # ===== SHIFTS =====
        print("📅 Creating shifts for today...")

        shifts = [
            Shift(
                gate_id=gate_in.id,
                shift_type=ShiftType.MORNING,
                date=today,
                operator_num_worker=operator.num_worker,
                manager_num_worker=manager.num_worker
            ),
            Shift(
                gate_id=gate_in.id,
                shift_type=ShiftType.AFTERNOON,
                date=today,
                operator_num_worker=operator.num_worker,
                manager_num_worker=manager.num_worker
            ),
            Shift(
                gate_id=gate_in.id,
                shift_type=ShiftType.NIGHT,
                date=today,
                operator_num_worker=operator.num_worker,
                manager_num_worker=manager.num_worker
            ),
        ]
        db.add_all(shifts)
        db.flush()

        # ===== BOOKINGS & CARGOS & APPOINTMENTS =====
        print("📦 Creating 20 appointments (all in_transit)...")

        appointments = []
        
        for i in range(20):
            # Booking
            booking = Booking(
                reference=f"BK-{today.strftime('%Y%m%d')}-{i+1:04d}",
                direction="inbound"
            )
            db.add(booking)
            db.flush()

            # Cargo (with hazmat for first 5)
            desc, state, weight, is_hazmat, un_code, kemler = CARGO_TYPES[i]
            # Note: un_code and kemler_code are not stored in Cargo model,
            # hazmat info is tracked via description and appointment notes
            cargo = Cargo(
                booking_reference=booking.reference,
                quantity=Decimal(str(weight)),
                state=state,
                description=desc if not is_hazmat else f"{desc} [UN:{un_code}, Kemler:{kemler}]"
            )
            db.add(cargo)
            db.flush()

            # Distribute drivers among appointments
            driver_idx = i % len(drivers)
            
            # Schedule appointments: first 10 in next 2 hours, rest spread through day
            if i < 10:
                # Arriving soon - every 10 minutes starting from 5 minutes ago
                scheduled_time = now + timedelta(minutes=-5 + (10 * i))
            else:
                # Later arrivals - every 30 minutes
                scheduled_time = now + timedelta(hours=2, minutes=30 * (i - 10))

            # Appointment
            appt = Appointment(
                booking_reference=booking.reference,
                driver_license=drivers[driver_idx].drivers_license,
                truck_license_plate=trucks[i].license_plate,
                terminal_id=terminal.id,
                gate_in_id=gate_in.id,
                gate_out_id=None,
                scheduled_start_time=scheduled_time,
                expected_duration=45,
                status="in_transit",  # ALL in_transit for demo flow
                notes=f"HAZMAT: {desc}" if is_hazmat else f"Cargo: {desc}"
            )
            db.add(appt)
            db.flush()
            appointments.append((appt, trucks[i], is_hazmat, desc))

        # ===== COMMIT =====
        print("\n💾 Saving to database...")
        db.commit()

        # ===== SUMMARY =====
        print("\n" + "=" * 70)
        print("  ✅ MVP DEMO DATABASE INITIALIZED SUCCESSFULLY")
        print("=" * 70)

        print("""
┌─────────────────────────────────────────────────────────────────────┐
│                        LOGIN CREDENTIALS                             │
├─────────────────────────────────────────────────────────────────────┤
│  WEB PORTAL (Operator/Manager):                                      │
│  ┌─────────────────────────┬─────────────┬────────────┐             │
│  │ Email                   │ Password    │ Role       │             │
│  ├─────────────────────────┼─────────────┼────────────┤             │
│  │ worker@porto.pt         │ password123 │ Operator   │             │
│  │ joao.silva@porto.pt     │ password123 │ Manager    │             │
│  └─────────────────────────┴─────────────┴────────────┘             │
│                                                                      │
│  MOBILE APP (Drivers):                                               │
│  ┌──────────────────┬─────────────────┬─────────────┐               │
│  │ License          │ Name            │ Password    │               │
│  ├──────────────────┼─────────────────┼─────────────┤               │
│  │ PT12345678       │ Rui Almeida     │ driver123   │               │
│  │ ES87654321       │ Carlos García   │ driver123   │               │
│  │ DE11223344       │ Hans Müller     │ driver123   │               │
│  └──────────────────┴─────────────────┴─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
""")

        print("┌" + "─" * 68 + "┐")
        print("│  20 APPOINTMENTS - ALL IN_TRANSIT (ready for demo flow)           │")
        print("├" + "─" * 68 + "┤")
        print("│  #  │ PIN        │ License Plate │ Scheduled  │ Cargo              │")
        print("├" + "─" * 68 + "┤")

        for i, (appt, truck, is_hazmat, desc) in enumerate(appointments):
            time_str = appt.scheduled_start_time.strftime('%H:%M') if appt.scheduled_start_time else '--:--'
            pin = appt.arrival_id or f"PRT-{i+1:04d}"
            hazmat_flag = "⚠️ " if is_hazmat else "   "
            cargo_short = desc[:18] if len(desc) <= 18 else desc[:15] + "..."
            print(f"│ {i+1:2} │ {pin:<10} │ {truck.license_plate:<13} │ {time_str:<10} │ {hazmat_flag}{cargo_short:<15} │")

        print("└" + "─" * 68 + "┘")

        print("""
┌─────────────────────────────────────────────────────────────────────┐
│                     🎯 MVP DEMO QUICK GUIDE                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  FOR HAZMAT DETECTION DEMO:                                          │
│  → Use plates AA-00-AA through EE-44-EE (first 5 appointments)      │
│  → These have UN/Kemler codes that trigger hazmat alerts            │
│                                                                      │
│  FOR NORMAL FLOW DEMO:                                               │
│  → Use any other plate (12-AB-34, VKTH76, etc.)                     │
│  → Shows standard approval flow without hazmat alerts               │
│                                                                      │
│  DEMO TIPS:                                                          │
│  1. Start with normal flow (plate 12-AB-34) to show basic operation │
│  2. Then demo hazmat (plate AA-00-AA) to show alert generation      │
│  3. Use operator dashboard to show real-time WebSocket updates      │
│  4. All appointments are in_transit - ready for detection           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
""")

    except Exception as e:
        print(f"\n❌ Error during initialization: {e}")
        db.rollback()
        raise


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_simple_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://porto:porto_password@localhost:5432/porto_logistica"
    print(f"\n🔗 Connecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)

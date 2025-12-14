#!/usr/bin/env python3
"""
Simple data initializer for MVP demo.
Creates 1 driver with 22 appointments using specific license plates (max 2 per plate).
Run with PYTHONPATH=src python src/Data_Module/scripts/data_init_simple.py
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

# Try to import models from package path (assuming PYTHONPATH includes `src`)
try:
    from Data_Module.models.sql_models import (
        Base, Worker, Manager, Operator, Company, Driver,
        Truck, Terminal, Dock, Gate, Shift, ShiftType,
        Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
    )
except Exception:
    # Fallback for direct execution
    try:
        from models.sql_models import (
            Base, Worker, Manager, Operator, Company, Driver,
            Truck, Terminal, Dock, Gate, Shift, ShiftType,
            Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
        )
    except Exception as e:
        print("Error importing models:", e)
        print("Make sure PYTHONPATH includes the `src` folder or run from repository root.")
        sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Specific license plates for demo (11 plates = max 22 appointments with 2 each)
LICENSE_PLATES = [
    "VKTH76", "SL06173", "KHTS141", "SLS06408", "WNDSU600",
    "MZGOH112", "MZGOH89", "BC8003", "AE66LR", "AA12DF", "BI00US"
]


def init_simple_data(db: Session):
    """
    Initialize database with simple mock data for MVP demo.
    1 driver, 22 appointments with specific trucks (max 2 per plate).
    """
    print("Populating database with simple demo data...")

    # Check if data already exists
    if db.query(Worker).first():
        print("Data already exists. Skipping initialization.")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ===== WORKERS =====
        print("Creating workers...")

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

        # ===== COMPANY =====
        print("Creating company...")

        company = Company(nif="500123456", name="TransPortugal Lda", contact="220123456")
        db.add(company)
        db.flush()

        # ===== DRIVER =====
        print("Creating driver...")

        driver = Driver(
            drivers_license="PT12345678",
            name="Rui Almeida",
            company_nif=company.nif,
            password_hash=pwd_context.hash("driver123"),
            active=True
        )
        db.add(driver)
        db.flush()

        # ===== TRUCKS =====
        print("Creating trucks...")

        trucks = []
        for plate in LICENSE_PLATES:
            trucks.append(Truck(
                license_plate=plate,
                brand="Volvo",
                company_nif=company.nif
            ))
        db.add_all(trucks)
        db.flush()

        # ===== TERMINAL =====
        print("Creating terminal...")

        terminal = Terminal(
            name="Terminal Norte",
            latitude=Decimal("41.1523"),
            longitude=Decimal("-8.6145"),
            hazmat_approved=True
        )
        db.add(terminal)
        db.flush()

        # ===== DOCKS =====
        print("Creating docks...")

        docks = []
        for i in range(1, 4):
            docks.append(Dock(
                terminal_id=terminal.id,
                bay_number=f"BAY-{i:02d}",
                latitude=Decimal(f"41.{1520 + i}"),
                longitude=Decimal(f"-8.{6140 + i}"),
                current_usage="operational"
            ))
        db.add_all(docks)
        db.flush()

        # ===== GATES =====
        print("Creating gates...")

        gate_in = Gate(label="Gate A - Entrada", latitude=Decimal("41.1510"), longitude=Decimal("-8.6210"))
        gate_out = Gate(label="Gate B - Saída", latitude=Decimal("41.1520"), longitude=Decimal("-8.6200"))
        db.add_all([gate_in, gate_out])
        db.flush()

        # ===== SHIFTS =====
        print("Creating shifts...")

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
        ]
        db.add_all(shifts)
        db.flush()

        # ===== BOOKINGS =====
        print("Creating bookings...")

        bookings = []
        for i in range(22):
            bookings.append(Booking(
                reference=f"BK-{today.strftime('%Y%m%d')}-{i+1:04d}",
                direction="inbound" if i % 2 == 0 else "outbound"
            ))
        db.add_all(bookings)
        db.flush()

        # ===== CARGOS =====
        print("Creating cargos...")

        cargo_descriptions = [
            ("Auto parts", "solid", Decimal("8000")),
            ("Electronic equipment", "solid", Decimal("5500")),
            ("Furniture", "solid", Decimal("9000")),
            ("Construction materials", "solid", Decimal("16000")),
            ("Textile products", "solid", Decimal("6000")),
            ("Industrial machinery", "solid", Decimal("19000")),
            ("Frozen meat", "solid", Decimal("18000")),
            ("Pharmaceutical products", "solid", Decimal("5000")),
            ("Wheat cereals", "solid", Decimal("22000")),
            ("Industrial sand", "solid", Decimal("25000")),
            ("Wine and beverages", "liquid", Decimal("12000")),
            ("Olive oil", "liquid", Decimal("9500")),
        ]

        cargos = []
        for i, booking in enumerate(bookings):
            desc, state, qty = cargo_descriptions[i % len(cargo_descriptions)]
            cargos.append(Cargo(
                booking_reference=booking.reference,
                quantity=qty,
                state=state,
                description=desc
            ))
        db.add_all(cargos)
        db.flush()

        # ===== APPOINTMENTS =====
        print("Creating 22 appointments for demo (max 2 per license plate)...")

        # Spread appointments across the day starting from now
        appointments = []
        # All appointments start as in_transit
        statuses = ["in_transit"] * 22

        for i in range(22):
            # Schedule appointments every 20 minutes starting from now
            scheduled_time = now + timedelta(minutes=20 * i)
            
            # Each plate gets max 2 appointments (11 plates * 2 = 22)
            truck_idx = i % len(trucks)
            
            appt = Appointment(
                booking_reference=bookings[i].reference,
                driver_license=driver.drivers_license,
                truck_license_plate=trucks[truck_idx].license_plate,
                terminal_id=terminal.id,
                gate_in_id=gate_in.id,
                gate_out_id=None,
                scheduled_start_time=scheduled_time,
                expected_duration=45,
                status=statuses[i],
                notes=f"Demo arrival #{i+1}"
            )
            # Insert one at a time so arrival_id auto-generation works correctly
            db.add(appt)
            db.flush()
            appointments.append(appt)

        # ===== COMMIT =====
        print("[Saving data to the database...]")
        db.commit()

        print("Database initialized successfully!")
        print(f"""
================================================================================
                     SIMPLE DATABASE INITIALIZATION SUMMARY
================================================================================

ENTITIES CREATED:
- Workers: 2 (1 manager, 1 operator)
- Company: 1
- Driver: 1
- Trucks: {len(trucks)}
- Terminal: 1
- Docks: {len(docks)}
- Gates: 2
- Shifts: {len(shifts)}
- Bookings: {len(bookings)}
- Cargos: {len(cargos)}
- Appointments: {len(appointments)} (12 in_transit, 6 delayed, 4 in_process)
- Alerts: 0

================================================================================
                              MVP TEST CREDENTIALS
================================================================================

WEB PORTAL (Operator/Manager):
┌─────────────────────────────────┬─────────────┬────────────┐
│ Email                           │ Password    │ Role       │
├─────────────────────────────────┼─────────────┼────────────┤
│ joao.silva@porto.pt             │ password123 │ Manager    │
│ worker@porto.pt                 │ password123 │ Operator   │
└─────────────────────────────────┴─────────────┴────────────┘

MOBILE APP (Driver):
┌──────────────────┬─────────────────────┬─────────────┐
│ Driver License   │ Name                │ Password    │
├──────────────────┼─────────────────────┼─────────────┤
│ PT12345678       │ Rui Almeida         │ driver123   │
└──────────────────┴─────────────────────┴─────────────┘

================================================================================
                          APPOINTMENTS FOR DEMO
================================================================================

All 22 appointments assigned to driver: PT12345678 (Rui Almeida)
Each license plate has max 2 appointments.
""")

        print("┌────────────┬────────────────┬───────────────────────┬─────────────┐")
        print("│ PIN        │ Truck          │ Scheduled Time        │ Status      │")
        print("├────────────┼────────────────┼───────────────────────┼─────────────┤")
        
        for i, appt in enumerate(appointments):
            time_str = appt.scheduled_start_time.strftime('%H:%M') if appt.scheduled_start_time else '--:--'
            pin_display = appt.arrival_id or "PRT-XXXX"
            plate = trucks[i % len(trucks)].license_plate
            print(f"│ {pin_display:<10} │ {plate:<14} │ {today.strftime('%Y-%m-%d')} {time_str:<7} │ {appt.status:<11} │")
        
        print("└────────────┴────────────────┴───────────────────────┴─────────────┘")

        print("""
================================================================================
                               QUICK TEST GUIDE
================================================================================

NOTE: Arrival IDs (PINs) are auto-generated by database trigger in PRT-XXXX format.

1. Login as driver:
   POST /drivers/login
   {"drivers_license": "PT12345678", "password": "driver123"}

2. Claim appointment with PIN (use actual PIN from table above):
   POST /drivers/claim?drivers_license=PT12345678
   {"arrival_id": "PRT-0001"}

3. Get active arrival:
   GET /drivers/me/active?drivers_license=PT12345678

4. Login as operator:
   POST /workers/login
   {"email": "worker@porto.pt", "password": "password123"}

================================================================================""")

    except Exception as e:
        print("!!! Error during initialization:", e)
        db.rollback()
        raise


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    # Create tables if they don't exist
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_simple_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://user:password@localhost/porto_db"
    print("Using DATABASE_URL =", DATABASE_URL)
    create_and_seed(DATABASE_URL)

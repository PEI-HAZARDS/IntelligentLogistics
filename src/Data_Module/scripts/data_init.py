#!/usr/bin/env python3
"""
Data initializer for MVP.
Run with PYTHONPATH=src python src/Data_Module/scripts/data_init.py
"""

from datetime import datetime, date, time, timedelta
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
import os
import random
import sys

# Add parent directory to path so we can import models
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

# Try to import models from package path (assuming PYTHONPATH includes `src`)
try:
    from Data_Module.models.sql_models import (
        Base, Worker, Manager, Operator, Company, Driver,
        Truck, Terminal, Dock, Gate, Shift, ShiftType,
        Booking, Cargo, Appointment, Visit, Alert
    )
except Exception:
    # Fallback for direct execution
    try:
        from models.sql_models import (
            Base, Worker, Manager, Operator, Company, Driver,
            Truck, Terminal, Dock, Gate, Shift, ShiftType,
            Booking, Cargo, Appointment, Visit, Alert
        )
    except Exception as e:
        print("Error importing models:", e)
        print("Make sure PYTHONPATH includes the `src` folder or run from repository root.")
        sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def init_data(db: Session):
    """
    Initialize database with mock data for MVP.
    Idempotent function for development/demo use.
    """
    print("Populating database with initial data...")

    # Check if data already exists
    if db.query(Worker).first():
        print("Data already exists. Skipping initialization.")
        return

    try:
        # ===== WORKERS =====
        print("Creating workers...")

        # Manager
        manager1 = Worker(
            nif="123456789",
            name="João Silva",
            email="joao.silva@porto.pt",
            phone="910000001",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        # Operator
        operator1 = Worker(
            nif="234567890",
            name="Carlos Oliveira",
            email="carlos.oliveira@porto.pt",
            phone="910000002",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        db.add_all([manager1, operator1])
        db.flush()

        # Create manager and operator records
        manager_obj1 = Manager(nif=manager1.nif, access_level="admin")
        operator_obj1 = Operator(nif=operator1.nif)

        db.add_all([manager_obj1, operator_obj1])
        db.flush()

        # ===== COMPANIES =====
        print("Creating companies...")

        companies = [
            Company(nif="500123456", name="TransPortugal Lda", contact="220123456"),
            Company(nif="500234567", name="EuroCargas SA", contact="220234567"),
            Company(nif="500345678", name="LogísticaPro", contact="220345678"),
            Company(nif="500456789", name="CargoExpress", contact="220456789"),
            Company(nif="500567890", name="MegaTrans", contact="220567890"),
        ]
        db.add_all(companies)
        db.flush()

        # ===== DRIVERS =====
        print("Creating drivers...")

        drivers = [
            Driver(drivers_license="PT12345678", name="Rui Almeida", company_nif=companies[0].nif),
            Driver(drivers_license="PT23456789", name="Sofia Rodrigues", company_nif=companies[0].nif),
            Driver(drivers_license="PT34567890", name="Miguel Teixeira", company_nif=companies[1].nif),
            Driver(drivers_license="PT45678901", name="Rita Pereira", company_nif=companies[1].nif),
            Driver(drivers_license="PT56789012", name="Bruno Sousa", company_nif=companies[2].nif),
            Driver(drivers_license="PT67890123", name="Carla Mendes", company_nif=companies[2].nif),
            Driver(drivers_license="PT78901234", name="Nuno Dias", company_nif=companies[3].nif),
            Driver(drivers_license="PT89012345", name="Patrícia Lima", company_nif=companies[3].nif),
            Driver(drivers_license="PT90123456", name="Tiago Martins", company_nif=companies[4].nif),
            Driver(drivers_license="PT01234567", name="Vera Castro", company_nif=companies[4].nif),
        ]
        
        # Add test passwords for mobile app
        print("Adding test passwords for drivers...")
        for driver in drivers:
            driver.password_hash = pwd_context.hash("driver123")
            driver.active = True
        
        db.add_all(drivers)
        db.flush()

        # ===== TRUCKS =====
        print("Creating trucks...")

        brands = ["Volvo", "Scania", "Mercedes", "MAN", "Iveco", "DAF"]
        trucks = []
        license_plates = ["AA-11-BB", "CC-22-DD", "EE-33-FF", "GG-44-HH", "II-55-JJ",
                          "KK-66-LL", "MM-77-NN", "OO-88-PP", "QQ-99-RR", "SS-00-TT",
                          "UU-12-VV", "WW-34-XX", "YY-56-ZZ", "AB-78-CD", "EF-90-GH"]

        for i, plate in enumerate(license_plates):
            trucks.append(Truck(
                license_plate=plate, 
                brand=random.choice(brands),
                company_nif=companies[i % len(companies)].nif
            ))

        db.add_all(trucks)
        db.flush()

        # ===== TERMINALS =====
        print("Creating terminals...")

        terminals = [
            Terminal(latitude=Decimal("41.1523"), longitude=Decimal("-8.6145")),
            Terminal(latitude=Decimal("41.1524"), longitude=Decimal("-8.6146")),
        ]

        db.add_all(terminals)
        db.flush()

        # ===== DOCKS =====
        print("Creating docks...")

        docks = []
        for i in range(1, 6):
            docks.append(Dock(
                terminal_id=terminals[0].id,
                bay_number=f"BAY-{i:02d}",
                latitude=Decimal(f"41.{1520 + i}"),
                longitude=Decimal(f"-8.{6140 + i}"),
                current_usage="operational"
            ))

        db.add_all(docks)
        db.flush()

        # ===== GATES =====
        print("Creating gates...")

        gates = [
            Gate(label="Gate A - Main Entrance", latitude=Decimal("41.1510"), longitude=Decimal("-8.6210")),
            Gate(label="Gate B - North Exit", latitude=Decimal("41.1520"), longitude=Decimal("-8.6200")),
        ]

        db.add_all(gates)
        db.flush()

        # ===== SHIFTS =====
        print("Creating shifts...")

        today = date.today()

        shifts = [
            Shift(
                shift_type=ShiftType.MORNING,
                date=today,
                operator_nif=operator1.nif,
                manager_nif=manager1.nif,
                gate_id=gates[0].id
            ),
            Shift(
                shift_type=ShiftType.AFTERNOON,
                date=today,
                operator_nif=operator1.nif,
                manager_nif=manager1.nif,
                gate_id=gates[0].id
            ),
        ]

        db.add_all(shifts)
        db.flush()

        # ===== BOOKINGS =====
        print("Creating bookings...")

        bookings = []
        for i in range(33):
            bookings.append(Booking(
                reference=f"BK-{today.strftime('%Y%m%d')}-{i+1:04d}",
                direction="inbound" if i % 2 == 0 else "outbound"
            ))

        db.add_all(bookings)
        db.flush()

        # ===== CARGOS =====
        print("Creating cargos...")

        cargo_descriptions = [
            ("Sulfuric acid (H2SO4)", "liquid", Decimal("15000")),
            ("Compressed propane gas", "gaseous", Decimal("8000")),
            ("Flammable chemicals", "liquid", Decimal("12000")),
            ("Frozen meat", "solid", Decimal("18000")),
            ("Pharmaceutical products", "solid", Decimal("5000")),
            ("Cattle", "solid", Decimal("6000")),
            ("Poultry", "solid", Decimal("3000")),
            ("Wheat cereals", "solid", Decimal("22000")),
            ("Industrial sand", "solid", Decimal("25000")),
            ("Auto parts", "solid", Decimal("8000")),
            ("Electronic equipment", "solid", Decimal("5500")),
            ("Furniture", "solid", Decimal("9000")),
            ("Construction materials", "solid", Decimal("16000")),
            ("Textile products", "solid", Decimal("6000")),
            ("Industrial machinery", "solid", Decimal("19000")),
        ]

        cargos = []
        for i, booking in enumerate(bookings):
            desc, state, qty = cargo_descriptions[i % len(cargo_descriptions)]
            cargos.append(Cargo(
                booking_id=booking.id,
                quantity=qty,
                state=state,
                description=desc
            ))

        db.add_all(cargos)
        db.flush()

        # ===== APPOINTMENTS =====
        print("Creating appointments...")

        schedules = [
            time(6, 30), time(7, 0), time(7, 45), time(8, 20), time(9, 0),
            time(9, 40), time(10, 15), time(11, 0), time(11, 30), time(12, 15),
            time(13, 0), time(13, 45), time(14, 30), time(15, 0), time(15, 45),
            time(16, 20), time(17, 0), time(17, 40), time(18, 15), time(19, 0),
            time(19, 45), time(20, 30), time(21, 0), time(21, 45), time(22, 30),
            time(23, 0), time(23, 30), time(0, 15), time(1, 0), time(2, 0),
            time(3, 0), time(4, 0), time(5, 0)
        ]

        status_distribution = (
            ["pending"] * 13 +
            ["approved"] * 10 +
            ["completed"] * 7 +
            ["canceled"] * 3
        )
        random.shuffle(status_distribution)

        appointments = []
        for i in range(33):
            scheduled_time = datetime.combine(today, schedules[i])
            appointments.append(Appointment(
                arrival_id=f"PRT-{i+1:04d}",
                booking_id=bookings[i].id,
                driver_license=drivers[i % len(drivers)].drivers_license,
                truck_license_plate=trucks[i % len(trucks)].license_plate,
                terminal_id=terminals[0].id,
                gate_in_id=gates[0].id,
                gate_out_id=gates[1].id if status_distribution[i] == "completed" else None,
                scheduled_start_time=scheduled_time,
                expected_duration=random.randint(30, 120),
                status=status_distribution[i],
                notes="Normal delivery"
            ))

        db.add_all(appointments)
        db.flush()

        # ===== VISITS =====
        print("Creating visits for completed/approved appointments...")

        visits = []
        for appt in appointments:
            if appt.status in ["approved", "completed"]:
                entry_time = appt.scheduled_start_time + timedelta(minutes=random.randint(-15, 30))
                out_time = None
                state = "in_transit"
                
                if appt.status == "completed":
                    out_time = entry_time + timedelta(minutes=random.randint(30, 90))
                    state = "completed"
                
                visits.append(Visit(
                    appointment_id=appt.id,
                    shift_id=shifts[0].id,
                    entry_time=entry_time,
                    out_time=out_time,
                    state=state
                ))

        db.add_all(visits)
        db.flush()

        # ===== ALERTS =====
        print("Creating alerts...")

        alerts = [
            Alert(
                cargo_id=cargos[0].id,
                type="hazmat",
                severity=4,
                description="Hazardous cargo (acid) - check containment"
            ),
            Alert(
                cargo_id=cargos[1].id,
                type="hazmat",
                severity=5,
                description="Compressed gas - mandatory ADR inspection"
            ),
            Alert(
                cargo_id=cargos[3].id,
                type="temperature",
                severity=3,
                description="Temperature out of range - refrigerated cargo"
            ),
        ]

        db.add_all(alerts)
        db.flush()

        # ===== COMMIT =====
        print("[Saving data to the database...]")
        db.commit()

        print("Database initialized successfully!")
        print(f"""
Summary:
- Workers: 2 (1 manager, 1 operator)
- Companies: {len(companies)}
- Drivers: {len(drivers)} (all with password: driver123)
- Trucks: {len(trucks)}
- Terminals: {len(terminals)}
- Docks: {len(docks)}
- Gates: {len(gates)}
- Shifts: {len(shifts)}
- Bookings: {len(bookings)}
- Cargos: {len(cargos)}
- Appointments: {len(appointments)} (with arrival_id PRT-0001 to PRT-0033)
  · Pending: {status_distribution.count('pending')}
  · Approved: {status_distribution.count('approved')}
  · Completed: {status_distribution.count('completed')}
  · Canceled: {status_distribution.count('canceled')}
- Visits: {len(visits)}
- Alerts: {len(alerts)}

Test credentials:

Web Portal:
Email: joao.silva@porto.pt | Password: password123 (Manager)
Email: carlos.oliveira@porto.pt | Password: password123 (Operator)

Mobile App (Drivers):
Driver license: PT12345678, PT23456789, etc.
Password: driver123
Test PIN: PRT-0001 (First appointment)
""")
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
        init_data(db)
    finally:
        db.close()

if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://user:password@localhost/porto_db"
    print("Using DATABASE_URL =", DATABASE_URL)
    create_and_seed(DATABASE_URL)
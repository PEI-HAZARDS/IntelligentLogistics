#!/usr/bin/env python3
"""
Data initializer for Tests - Porto de Aveiro realistic scenario.
20 appointments with unique license plates for demo.
Run with: python scripts/data_init_realistic.py
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

# Try to import models
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

# =============================================================================
# REALISTIC DATA FOR PORTO DE AVEIRO
# =============================================================================

# 20 unique license plates for MVP demo (1 plate = 1 appointment)
# Mix of Portuguese and international formats for realism
LICENSE_PLATES = [
    # Portuguese plates (easy to remember for demo - HAZMAT)
    "AA-00-AA",  # Demo plate 1 - HAZMAT TEST (Gasoline)
    "BB-11-BB",  # Demo plate 2 - HAZMAT (Propane)
    "CC-22-CC",  # Demo plate 3 - HAZMAT (Chemical)
    "DD-33-DD",  # Demo plate 4 - HAZMAT (Ammonia)
    "EE-44-EE",  # Demo plate 5 - HAZMAT (Pesticides)
    # Real-looking Portuguese plates (Normal cargo)
    "12-AB-34",
    "56-CD-78",
    "90-EF-12",
    "34-GH-56",
    "78-IJ-90",
    # Spanish plates (cross-border transport)
    "1234-ABC",
    "5678-DEF",
    "9012-GHI",
    # German plates
    "B-AB-1234",
    "M-CD-5678",
    # French plates
    "AB-123-CD",
    "EF-456-GH",
    # More Portuguese plates
    "23-LM-45",
    "67-NP-89",
    "01-QR-23",
]

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
DRIVERS = [
    # Portuguese drivers
    ("PT12345678", "Rui Almeida", 0),
    ("PT23456789", "Sofia Rodrigues", 0),
    ("PT34567890", "Miguel Santos", 1),
    ("PT45678901", "Ana Ferreira", 1),
    ("PT56789012", "Bruno Costa", 2),
    # Spanish driver
    ("ES87654321", "Carlos Garcia Lopez", 3),
    ("ES76543210", "Maria Fernandez", 3),
    # German driver
    ("DE11223344", "Hans Mueller", 4),
    # French driver
    ("FR99887766", "Pierre Dubois", 5),
    ("FR88776655", "Jean-Luc Martin", 5),
]

# Cargo types realistic for Port of Aveiro operations
# Format: (description, state, weight_kg, is_hazmat, un_code, kemler_code, typical_origin)
CARGO_TYPES = [
    # HAZMAT cargos (first 5 - for hazmat detection demo)
    ("Gasoline ADR", "liquid", 24000, True, "1203", "33", "Refinaria Sines"),
    ("Propane cylinders", "gaseous", 8000, True, "1978", "23", "Galp Energia"),
    ("Industrial chemicals", "liquid", 15000, True, "1830", "80", "CUF Quimicos"),
    ("Ammonium nitrate fertilizer", "solid", 22000, True, "1942", "50", "Sapec Agro"),
    ("Agricultural pesticides", "liquid", 6000, True, "2902", "60", "Syngenta PT"),
    
    # Port of Aveiro typical cargos
    ("Ceramic tiles (Revigrés)", "solid", 24000, False, None, None, "Revigrés Aveiro"),
    ("Cork products (Corticeira)", "solid", 8000, False, None, None, "Corticeira Amorim"),
    ("Paper pulp (Navigator)", "solid", 28000, False, None, None, "The Navigator Co"),
    ("Salt (Salinas Aveiro)", "solid", 26000, False, None, None, "Salinas de Aveiro"),
    ("Fish (fresh catch)", "solid", 12000, False, None, None, "Docapesca Aveiro"),
    ("Moliceiro boat parts", "solid", 3500, False, None, None, "Estaleiros Aveiro"),
    ("Wine (Bairrada DOC)", "liquid", 18000, False, None, None, "Caves S. Joao"),
    ("Dairy products (Lactogal)", "solid", 14000, False, None, None, "Lactogal"),
    ("Timber (eucalyptus)", "solid", 30000, False, None, None, "Altri Florestal"),
    ("Auto parts (Toyota)", "solid", 16000, False, None, None, "Toyota Caetano"),
    ("Glass bottles (BA Glass)", "solid", 22000, False, None, None, "BA Glass Aveiro"),
    ("Frozen seafood", "solid", 18000, False, None, None, "Friopesca"),
    ("Construction steel", "solid", 28000, False, None, None, "ArcelorMittal"),
    ("Textile rolls", "solid", 9000, False, None, None, "Riopele Texteis"),
    ("Electronic components", "solid", 5000, False, None, None, "Continental Mabor"),
]


def init_data(db: Session):
    """
    Initialize database with realistic Porto de Aveiro data.
    20 appointments for MVP demo - all in_transit for decision flow.
    """
    print("=" * 70)
    print("  PORTO DE AVEIRO - REALISTIC MVP DATA INITIALIZER")
    print("=" * 70)

    # Check if data already exists
    if db.query(Worker).first():
        print("\nData already exists. Skipping initialization.")
        print("To reset: docker-compose down -v && docker-compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ===== WORKERS =====
        print("\nCreating port workers...")

        manager = Worker(
            num_worker="MGR001",
            name="Joao Silva",
            email="joao.silva@portodeaveiro.pt",
            phone="+351 910 000 001",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        operator = Worker(
            num_worker="OPR001",
            name="Maria Santos",
            email="worker@portodeaveiro.pt",
            phone="+351 910 000 002",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        # Second operator for shift coverage
        operator2 = Worker(
            num_worker="OPR002",
            name="Antonio Ferreira",
            email="antonio.ferreira@portodeaveiro.pt",
            phone="+351 910 000 003",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        db.add_all([manager, operator, operator2])
        db.flush()

        manager_obj = Manager(num_worker=manager.num_worker, access_level="admin")
        operator_obj = Operator(num_worker=operator.num_worker)
        operator_obj2 = Operator(num_worker=operator2.num_worker)
        db.add_all([manager_obj, operator_obj, operator_obj2])
        db.flush()

        # ===== COMPANIES =====
        print("Creating transport companies...")

        companies = []
        for nif, name, contact in COMPANIES:
            companies.append(Company(nif=nif, name=name, contact=contact))
        db.add_all(companies)
        db.flush()

        # ===== DRIVERS =====
        print("Creating drivers...")

        drivers = []
        for license_num, name, company_idx in DRIVERS:
            drivers.append(Driver(
                drivers_license=license_num,
                name=name,
                company_nif=companies[company_idx].nif,
                password_hash=pwd_context.hash("driver123"),
                active=True
            ))
        db.add_all(drivers)
        db.flush()

        # ===== TRUCKS (20 unique plates) =====
        print("Creating 20 trucks with unique plates...")

        trucks = []
        brands = ["Volvo FH16", "Scania R500", "Mercedes Actros", "MAN TGX", "DAF XF", "Iveco S-Way"]
        for i, plate in enumerate(LICENSE_PLATES):
            company_idx = i % len(companies)
            trucks.append(Truck(
                license_plate=plate,
                brand=brands[i % len(brands)],
                company_nif=companies[company_idx].nif
            ))
        db.add_all(trucks)
        db.flush()

        # ===== TERMINAL - Porto de Aveiro =====
        print("Creating Porto de Aveiro terminal...")

        # Real coordinates for Port of Aveiro
        terminal = Terminal(
            name="Terminal Multiusos - Porto de Aveiro",
            latitude=Decimal("40.6446"),   # Real coordinates
            longitude=Decimal("-8.7455"),
            hazmat_approved=True
        )
        db.add(terminal)
        db.flush()

        # ===== DOCKS =====
        print("Creating docks...")

        docks = [
            Dock(terminal_id=terminal.id, bay_number="CAIS-NORTE-1", latitude=Decimal("40.6450"), longitude=Decimal("-8.7460"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-NORTE-2", latitude=Decimal("40.6451"), longitude=Decimal("-8.7461"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-SUL-1", latitude=Decimal("40.6440"), longitude=Decimal("-8.7450"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-SUL-2", latitude=Decimal("40.6441"), longitude=Decimal("-8.7451"), current_usage="operational"),
            Dock(terminal_id=terminal.id, bay_number="CAIS-HAZMAT", latitude=Decimal("40.6435"), longitude=Decimal("-8.7445"), current_usage="operational"),
        ]
        db.add_all(docks)
        db.flush()

        # ===== GATES =====
        print("Creating gates...")

        gate_in = Gate(label="Portaria 1 - Entrada Principal", latitude=Decimal("40.6460"), longitude=Decimal("-8.7470"))
        gate_out = Gate(label="Portaria 2 - Saida", latitude=Decimal("40.6430"), longitude=Decimal("-8.7440"))
        db.add_all([gate_in, gate_out])
        db.flush()

        # ===== SHIFTS =====
        print("Creating shifts for today...")

        shifts = [
            Shift(gate_id=gate_in.id, shift_type=ShiftType.MORNING, date=today, operator_num_worker=operator.num_worker, manager_num_worker=manager.num_worker),
            Shift(gate_id=gate_in.id, shift_type=ShiftType.AFTERNOON, date=today, operator_num_worker=operator.num_worker, manager_num_worker=manager.num_worker),
            Shift(gate_id=gate_in.id, shift_type=ShiftType.NIGHT, date=today, operator_num_worker=operator2.num_worker, manager_num_worker=manager.num_worker),
        ]
        db.add_all(shifts)
        db.flush()

        # ===== BOOKINGS, CARGOS & APPOINTMENTS =====
        print("Creating 20 realistic appointments (all in_transit)...")

        appointments = []

        for i in range(20):
            # Booking
            booking = Booking(
                reference=f"AVR-{today.strftime('%Y%m%d')}-{i+1:04d}",
                direction="inbound"
            )
            db.add(booking)
            db.flush()

            # Cargo
            desc, state, weight, is_hazmat, un_code, kemler, origin = CARGO_TYPES[i]
            cargo = Cargo(
                booking_reference=booking.reference,
                quantity=Decimal(str(weight)),
                state=state,
                description=f"{desc} - Origin: {origin}",
                un_code=un_code,
                kemler_code=kemler
            )
            db.add(cargo)
            db.flush()

            # Driver distribution
            driver_idx = i % len(drivers)

            # Schedule: first 10 arriving in next 2 hours (demo), rest spread
            if i < 10:
                # Demo arrivals - every 10 minutes starting from 5 min ago
                scheduled_time = now + timedelta(minutes=-5 + (12 * i))
            else:
                # Later arrivals - every 30 minutes after
                scheduled_time = now + timedelta(hours=2, minutes=30 * (i - 10))

            # Appointment - ALL in_transit for demo flow
            appt = Appointment(
                booking_reference=booking.reference,
                driver_license=drivers[driver_idx].drivers_license,
                truck_license_plate=trucks[i].license_plate,
                terminal_id=terminal.id,
                gate_in_id=gate_in.id,
                gate_out_id=None,
                scheduled_start_time=scheduled_time,
                expected_duration=45,
                status="in_transit",
                notes=f"HAZMAT: {desc}" if is_hazmat else f"Cargo: {desc}"
            )
            db.add(appt)
            db.flush()
            appointments.append((appt, trucks[i], is_hazmat, desc, origin))

        # ===== COMMIT =====
        print("\nSaving to database...")
        db.commit()

        # ===== SUMMARY =====
        print("\n" + "=" * 70)
        print("  MVP DATABASE INITIALIZED - PORTO DE AVEIRO")
        print("=" * 70)

        print("""
+=====================================================================+
|                        LOGIN CREDENTIALS                             |
+=====================================================================+
|  WEB PORTAL (Operator/Manager):                                      |
|  +---------------------------+--------------+------------+           |
|  | Email                     | Password     | Role       |           |
|  +---------------------------+--------------+------------+           |
|  | worker@portodeaveiro.pt   | password123  | Operator   |           |
|  | joao.silva@portodeaveiro.pt | password123| Manager    |           |
|  +---------------------------+--------------+------------+           |
|                                                                      |
|  MOBILE APP (Drivers):                                               |
|  +----------------+---------------------+--------------+             |
|  | License        | Name                | Password     |             |
|  +----------------+---------------------+--------------+             |
|  | PT12345678     | Rui Almeida         | driver123    |             |
|  | ES87654321     | Carlos Garcia Lopez | driver123    |             |
|  | DE11223344     | Hans Mueller        | driver123    |             |
|  | FR99887766     | Pierre Dubois       | driver123    |             |
|  +----------------+---------------------+--------------+             |
+=====================================================================+
""")

        print("+" + "-" * 73 + "+")
        print("|  20 APPOINTMENTS - ALL IN_TRANSIT (ready for demo)                   |")
        print("+" + "-" * 73 + "+")
        print("|  #  | PIN        | Plate       | Time  | Cargo                       |")
        print("+" + "-" * 73 + "+")

        for i, (appt, truck, is_hazmat, desc, origin) in enumerate(appointments):
            time_str = appt.scheduled_start_time.strftime('%H:%M') if appt.scheduled_start_time else '--:--'
            pin = appt.arrival_id or f"PRT-{i+1:04d}"
            hazmat_flag = "[HZ]" if is_hazmat else "    "
            cargo_short = desc[:24] if len(desc) <= 24 else desc[:21] + "..."
            print(f"| {i+1:2} | {pin:<10} | {truck.license_plate:<11} | {time_str} | {hazmat_flag} {cargo_short:<22} |")

        print("+" + "-" * 73 + "+")

        print("""
+=====================================================================+
|                       MVP DEMO QUICK GUIDE                           |
+=====================================================================+
|                                                                      |
|  HAZMAT DETECTION DEMO (use these plates):                           |
|    AA-00-AA -> Gasoline (UN 1203, Kemler 33) - Flammable             |
|    BB-11-BB -> Propane (UN 1978, Kemler 23) - Flammable gas          |
|    CC-22-CC -> Chemicals (UN 1830, Kemler 80) - Corrosive            |
|    DD-33-DD -> Ammonium (UN 1942, Kemler 50) - Oxidizer              |
|    EE-44-EE -> Pesticides (UN 2902, Kemler 60) - Toxic               |
|                                                                      |
|  NORMAL FLOW DEMO (use these plates):                                |
|    12-AB-34 -> Ceramic tiles (Revigres)                              |
|    56-CD-78 -> Cork products (Corticeira Amorim)                     |
|    1234-ABC -> Paper pulp (Navigator) [Spanish truck]                |
|                                                                      |
|  DEMO WORKFLOW:                                                      |
|  1. Open Operator Dashboard (worker@portodeaveiro.pt)                |
|  2. Start with normal plate (12-AB-34) - shows standard flow         |
|  3. Then demo hazmat plate (AA-00-AA) - shows alert generation       |
|  4. WebSocket updates dashboard in real-time                         |
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
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://porto:porto_password@localhost:5432/porto_logistica"
    print(f"\nConnecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)
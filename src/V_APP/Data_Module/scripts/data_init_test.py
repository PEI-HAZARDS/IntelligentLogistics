#!/usr/bin/env python3
"""
Minimal test data initializer — single appointment cycle.

Creates the bare minimum to run one complete demo cycle:
  - 1 company, 1 driver (Oscar Almeida), 1 truck (87AX60)
  - 1 terminal, 2 gates, 1 shift
  - 1 appointment: 87AX60 / UN 1831 / Kemler X886 / status=in_transit

Run with: python scripts/data_init_test.py
"""

from datetime import datetime, date, time, timedelta
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
        from infrastructure.persistence.sql_models import (
            Base, Worker, Manager, Operator, Company, Driver,
            Truck, Terminal, Dock, Gate, Shift, ShiftType,
            Booking, Cargo, Appointment, Visit, Alert, ShiftAlertHistory
        )
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def init_data(db: Session):
    """
    Seed a single appointment cycle for truck 87AX60.
    Creates only the entities needed for the HAZMAT demo scenario.
    """
    print("=" * 70)
    print("  PORTO DE AVEIRO - MINIMAL TEST DATA INITIALIZER")
    print("  Single appointment: 87AX60 / UN 1831 / Kemler X886")
    print("=" * 70)

    if db.query(Worker).first():
        print("\nData already exists. Skipping initialization.")
        print("To reset: docker compose down -v && docker compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ===== WORKERS (minimum: 1 manager + 1 operator) =====
        print("\nCreating workers...")
        mgr_worker = Worker(
            num_worker="MGR001", name="Joao Silva",
            email="manager@example.pt", phone="+351 910 000 001",
            password_hash=pwd_context.hash("password123"), active=True
        )
        opr_worker = Worker(
            num_worker="OPR001", name="Maria Santos",
            email="worker@portodeaveiro.pt", phone="+351 910 000 002",
            password_hash=pwd_context.hash("password123"), active=True
        )
        db.add_all([mgr_worker, opr_worker])
        db.flush()
        db.add(Manager(num_worker="MGR001", access_level="admin"))
        db.add(Operator(num_worker="OPR001"))
        db.flush()

        # ===== COMPANY =====
        print("Creating company...")
        company = Company(
            nif="PT509123456",
            name="Transportes Aveiro Lda",
            contact="+351 234 567 890"
        )
        db.add(company)
        db.flush()

        # ===== DRIVER — Oscar Almeida =====
        print("Creating driver (Oscar Almeida)...")
        driver = Driver(
            drivers_license="PT12345678",
            name="Oscar Almeida",
            company_nif=company.nif,
            password_hash=pwd_context.hash("driver123"),
            active=True
        )
        db.add(driver)
        db.flush()

        # ===== TRUCK — 87AX60 =====
        print("Creating truck (87AX60 / Volvo FH16)...")
        truck = Truck(
            license_plate="87AX60",
            brand="Volvo FH16",
            company_nif=company.nif
        )
        db.add(truck)
        db.flush()

        # ===== TERMINAL — Terminal de Granéis Líquidos (HAZMAT) =====
        print("Creating terminal...")
        terminal = Terminal(
            name="Terminal de Granéis Líquidos - Porto de Aveiro",
            latitude=Decimal("40.6360"),
            longitude=Decimal("-8.7520"),
            hazmat_approved=True
        )
        db.add(terminal)
        db.flush()

        # ===== DOCKS =====
        print("Creating docks...")
        docks = [
            Dock(
                terminal_id=terminal.id, bay_number="CAIS-LIQ-1",
                latitude=Decimal("40.6362"), longitude=Decimal("-8.7522"),
                current_usage="operational"
            ),
            Dock(
                terminal_id=terminal.id, bay_number="CAIS-LIQ-HAZMAT",
                latitude=Decimal("40.6358"), longitude=Decimal("-8.7518"),
                current_usage="operational"
            ),
        ]
        db.add_all(docks)
        db.flush()

        # ===== GATES =====
        print("Creating gates...")
        gate_in = Gate(
            label="Portaria 1 - Entrada Principal",
            latitude=Decimal("40.6460"), longitude=Decimal("-8.7470")
        )
        gate_out = Gate(
            label="Portaria 2 - Saida",
            latitude=Decimal("40.6430"), longitude=Decimal("-8.7440")
        )
        gate_highway = Gate(
            label="Gate 3 - Abordagem A25",
            latitude=Decimal("40.6500"), longitude=Decimal("-8.7500")
        )
        db.add_all([gate_in, gate_out, gate_highway])
        db.flush()

        # ===== SHIFT (today morning) =====
        print("Creating shift...")
        morning_shift = Shift(
            gate_id=gate_in.id,
            shift_type=ShiftType.MORNING,
            date=today,
            operator_num_worker="OPR001",
            manager_num_worker="MGR001"
        )
        db.add(morning_shift)
        db.flush()

        # ===== CARGO — UN 1831, Kemler X886 =====
        print("Creating cargo (Sulfuric acid fuming, UN 1831, Kemler X886)...")
        booking = Booking(reference=f"AVR-TEST-{today.strftime('%Y%m%d')}-0001", direction="inbound")
        db.add(booking)
        db.flush()

        cargo_label = (
            "Sulfuric acid (fuming) [UN:1831, Kemler:X886] - Origin: CUF Quimicos Estarreja"
        )
        cargo = Cargo(
            booking_reference=booking.reference,
            quantity=Decimal("22000"),
            state="liquid",
            description=cargo_label
        )
        db.add(cargo)
        db.flush()

        # ===== APPOINTMENT — 87AX60, in_transit, arriving in 15 min =====
        print("Creating appointment (87AX60 / in_transit / arriving in 15 min)...")
        appt_time = now + timedelta(minutes=15)
        appt = Appointment(
            booking_reference=booking.reference,
            driver_license="PT12345678",       # Oscar Almeida
            truck_license_plate="87AX60",
            terminal_id=terminal.id,
            gate_in_id=gate_in.id,
            gate_out_id=None,
            scheduled_start_time=appt_time,
            expected_duration=60,
            status="in_transit",
            highway_infraction=False,          # No pre-seeded infraction — detected at runtime
            notes="HAZMAT: Sulfuric acid (fuming) [UN:1831, Kemler:X886] - Approaching port"
        )
        db.add(appt)
        db.flush()

        # ===== COMMIT =====
        print("\nSaving to database...")
        db.commit()

        print("\n" + "=" * 70)
        print("  TEST DATA INITIALIZED")
        print("=" * 70)
        print(f"""
+=====================================================================+
|                        LOGIN CREDENTIALS                             |
+=====================================================================+
|  WEB PORTAL:                                                         |
|  Email: worker@portodeaveiro.pt   Password: password123  (Operator) |
|  Email: manager@example.pt        Password: password123  (Manager)  |
|                                                                      |
|  MOBILE APP:                                                         |
|  License: PT12345678  Name: Oscar Almeida  Password: driver123      |
+=====================================================================+

+=====================================================================+
|                    HAZMAT DEMO — SINGLE CYCLE                        |
+=====================================================================+
|  Truck:  87AX60 (Volvo FH16)                                        |
|  Driver: Oscar Almeida (PT12345678)                                  |
|  Cargo:  Sulfuric acid (fuming) — 22 tonnes                         |
|  ADR:    UN 1831 / Kemler X886 (Corrosive, reacts with water)       |
|  Status: IN_TRANSIT — arriving at gate in ~15 minutes               |
|  Infraction: None pre-seeded — detected dynamically at runtime      |
|  Terminal: Terminal de Graneis Liquidos (HAZMAT approved)           |
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
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

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

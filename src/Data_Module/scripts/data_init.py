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
            num_worker="MGR001",
            name="João Silva",
            email="joao.silva@porto.pt",
            phone="910000001",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        # Operator
        operator1 = Worker(
            num_worker="OPR001",
            name="Carlos Oliveira",
            email="carlos.oliveira@porto.pt",
            phone="910000002",
            password_hash=pwd_context.hash("password123"),
            active=True
        )

        db.add_all([manager1, operator1])
        db.flush()

        # Create manager and operator records
        manager_obj1 = Manager(num_worker=manager1.num_worker, access_level="admin")
        operator_obj1 = Operator(num_worker=operator1.num_worker)

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
        license_plates = ["VKTH76", "SL06173", "KHTS141", "SLS06408", "WNDSU600",
                          "MZGOH112", "MZGOH89", "BC8003", "BC8004", "BC8005",
                          "BC8006", "BC8007", "BC8008", "BC8009", "BC8010"]

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
            Terminal(name="Terminal Norte", latitude=Decimal("41.1523"), longitude=Decimal("-8.6145"), hazmat_approved=True),
            Terminal(name="Terminal Sul", latitude=Decimal("41.1524"), longitude=Decimal("-8.6146"), hazmat_approved=False),
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

        # ===== SHIFTS (composite PK: gate_id + shift_type + date) =====
        print("Creating shifts...")

        # Use tomorrow for future appointments, today for current ones
        today = date.today()
        tomorrow = today + timedelta(days=1)
        
        # Create shifts for today and tomorrow
        shifts = []
        for shift_date in [today, tomorrow]:
            shifts.extend([
                Shift(
                    gate_id=gates[0].id,
                    shift_type=ShiftType.MORNING,
                    date=shift_date,
                    operator_num_worker=operator1.num_worker,
                    manager_num_worker=manager1.num_worker
                ),
                Shift(
                    gate_id=gates[0].id,
                    shift_type=ShiftType.AFTERNOON,
                    date=shift_date,
                    operator_num_worker=operator1.num_worker,
                    manager_num_worker=manager1.num_worker
                ),
            ])

        db.add_all(shifts)
        db.flush()

        # ===== BOOKINGS (PK: reference) =====
        print("Creating bookings...")

        # Create bookings for today
        bookings = []
        for i in range(40):
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
                booking_reference=booking.reference,
                quantity=qty,
                state=state,
                description=desc
            ))

        db.add_all(cargos)
        db.flush()

        # ===== APPOINTMENTS =====
        print("Creating appointments...")

        # Current time for MVP demo
        now = datetime.now()
        
        # ===== MVP DEMO APPOINTMENTS (near current time) =====
        # These will appear in the dashboard immediately for demo
        demo_appointments = []
        
        # Demo trucks with recognizable license plates for Decision Engine
        demo_configs = [
            # (truck_index, driver_index, minutes_offset, status, notes)
            (0, 0, -20, "delayed", "DEMO: Delayed arrival - hazmat cargo"),   # VKTH76 - already delayed
            (1, 1, -5, "delayed", "DEMO: Just became delayed"),                # SL06173
            (2, 2, 5, "in_transit", "DEMO: Arriving soon"),                    # KHTS141
            (3, 3, 10, "in_transit", "DEMO: Expected in 10 min"),              # SLS06408
            (4, 4, 15, "in_transit", "DEMO: Scheduled arrival"),               # WNDSU600
        ]
        
        for truck_idx, driver_idx, offset_min, status, notes in demo_configs:
            scheduled_time = now + timedelta(minutes=offset_min)
            demo_appointments.append(Appointment(
                # arrival_id auto-generated by trigger (PRT-XXXX format)
                booking_reference=bookings[truck_idx].reference,
                driver_license=drivers[driver_idx].drivers_license,
                truck_license_plate=trucks[truck_idx].license_plate,
                terminal_id=terminals[0].id,
                gate_in_id=gates[0].id,
                gate_out_id=None,
                scheduled_start_time=scheduled_time,
                expected_duration=random.randint(30, 60),
                status=status,
                notes=notes
            ))
        
        # ===== REST OF THE DAY APPOINTMENTS =====
        # Background appointments for realistic dashboard
        def generate_schedule_times(base_date: date, count: int, start_offset_hours: int = 1) -> list:
            """Generate appointment times spread across remaining operational hours."""
            schedules = []
            current_hour = now.hour + start_offset_hours
            end_hour = 22
            
            if current_hour >= end_hour:
                # If late in day, schedule for tomorrow morning
                current_hour = 8
            
            remaining_hours = end_hour - current_hour
            if remaining_hours <= 0:
                remaining_hours = 8  # Default spread
            
            interval_minutes = (remaining_hours * 60) // max(count, 1)
            
            for i in range(count):
                offset = i * interval_minutes + random.randint(0, 15)
                hour = current_hour + (offset // 60)
                minute = (offset % 60) // 5 * 5  # Round to 5 min
                
                if hour >= 22:
                    hour = 21
                    minute = 30
                
                schedules.append(datetime.combine(base_date, time(hour, minute)))
            
            return schedules

        # Generate 35 more background appointments
        background_count = 35
        schedule_times = generate_schedule_times(today, background_count)
        
        status_distribution = (
            ["in_transit"] * 25 +
            ["delayed"] * 6 +
            ["completed"] * 3 +
            ["canceled"] * 1
        )
        random.shuffle(status_distribution)

        background_appointments = []
        for i in range(background_count):
            scheduled_time = schedule_times[i]
            truck_idx = (i + 5) % len(trucks)  # Skip demo trucks
            driver_idx = (i + 5) % len(drivers)
            booking_idx = (i + 5) % len(bookings)
            
            background_appointments.append(Appointment(
                # arrival_id auto-generated by trigger
                booking_reference=bookings[booking_idx].reference,
                driver_license=drivers[driver_idx].drivers_license,
                truck_license_plate=trucks[truck_idx].license_plate,
                terminal_id=terminals[0].id,
                gate_in_id=gates[0].id,
                gate_out_id=gates[1].id if status_distribution[i] == "completed" else None,
                scheduled_start_time=scheduled_time,
                expected_duration=random.randint(30, 120),
                status=status_distribution[i],
                notes="Regular delivery"
            ))

        # Combine all appointments
        appointments = demo_appointments + background_appointments

        db.add_all(appointments)
        db.flush()

        # ===== VISITS (composite FK to Shift) =====
        print("Creating visits for in_transit/delayed/completed appointments...")

        # Get tomorrow's morning shift (shifts[2] is tomorrow morning, shifts[3] is tomorrow afternoon)
        tomorrow_morning_shift = shifts[2]  # Index 2 = tomorrow morning

        visits = []
        for appt in appointments:
            if appt.status in ["in_transit", "delayed", "completed"]:
                entry_time = appt.scheduled_start_time + timedelta(minutes=random.randint(-15, 30))
                out_time = None
                state = "unloading"  # Updated to match DeliveryStatusEnum
                
                if appt.status == "completed":
                    out_time = entry_time + timedelta(minutes=random.randint(30, 90))
                    state = "completed"
                
                # Determine which shift to use based on entry time
                if entry_time.hour < 14:
                    shift_to_use = tomorrow_morning_shift  # Morning shift
                else:
                    shift_to_use = shifts[3]  # Afternoon shift
                
                visits.append(Visit(
                    appointment_id=appt.id,
                    shift_gate_id=shift_to_use.gate_id,
                    shift_type=shift_to_use.shift_type,
                    shift_date=shift_to_use.date,
                    entry_time=entry_time,
                    out_time=out_time,
                    state=state
                ))

        db.add_all(visits)
        db.flush()

        # ===== ALERTS (using visit_id instead of cargo_id) =====
        print("Creating alerts...")

        # Find visits with hazardous cargo to attach alerts
        hazmat_visits = [v for v in visits if v.appointment_id <= 3]  # First 3 visits

        alerts = []
        if len(hazmat_visits) >= 1:
            alerts.append(Alert(
                visit_id=hazmat_visits[0].appointment_id,
                type="safety",
                description="Hazardous cargo (acid) - check containment | UN 1830 - Sulfuric acid | Class: 8 | Hazard: Corrosive"
            ))
        if len(hazmat_visits) >= 2:
            alerts.append(Alert(
                visit_id=hazmat_visits[1].appointment_id,
                type="safety",
                description="Compressed gas - mandatory ADR inspection | UN 1978 - Propane | Class: 2.1 | Hazard: Flammable gas"
            ))
        # Generic operational alert
        alerts.append(Alert(
            visit_id=None,
            type="operational",
            description="Temperature out of range - refrigerated cargo"
        ))

        db.add_all(alerts)
        db.flush()

        # ===== SHIFT ALERT HISTORY =====
        # Auto-created by trigger (trg_create_shift_alert_history)
        # when alert has visit_id, it's automatically linked to shift

        # ===== COMMIT =====
        print("[Saving data to the database...]")
        db.commit()

        print("Database initialized successfully!")
        print(f"""
================================================================================
                           DATABASE INITIALIZATION SUMMARY
================================================================================

ENTITIES CREATED:
- Workers: 2 (1 manager, 1 operator)
- Companies: {len(companies)}
- Drivers: {len(drivers)}
- Trucks: {len(trucks)}
- Terminals: {len(terminals)} (1 hazmat approved)
- Docks: {len(docks)}
- Gates: {len(gates)}
- Shifts: {len(shifts)} (today + tomorrow)
- Bookings: {len(bookings)}
- Cargos: {len(cargos)}
- Appointments: {len(appointments)}
  · In Transit: {status_distribution.count('in_transit')}
  · Delayed: {status_distribution.count('delayed')}
  · Completed: {status_distribution.count('completed')}
  · Canceled: {status_distribution.count('canceled')}
- Visits: {len(visits)}
- Alerts: {len(alerts)}

================================================================================
                              MVP TEST CREDENTIALS
================================================================================

WEB PORTAL (Operator/Manager):
┌─────────────────────────────────┬─────────────┬────────────┐
│ Email                           │ Password    │ Role       │
├─────────────────────────────────┼─────────────┼────────────┤
│ joao.silva@porto.pt             │ password123 │ Manager    │
│ carlos.oliveira@porto.pt        │ password123 │ Operator   │
└─────────────────────────────────┴─────────────┴────────────┘

MOBILE APP (Drivers):
┌──────────────────┬─────────────────────┬─────────────┐
│ Driver License   │ Name                │ Password    │
├──────────────────┼─────────────────────┼─────────────┤""")
        
        for driver in drivers[:5]:  # Show first 5 drivers
            print(f"│ {driver.drivers_license:<16} │ {driver.name:<19} │ driver123   │")
        
        print(f"""│ ...              │ (more drivers)      │ driver123   │
└──────────────────┴─────────────────────┴─────────────┘

================================================================================
                          APPOINTMENT PINs FOR TESTING
================================================================================

Date: {today.strftime('%Y-%m-%d')} (Today)
""")
        
        print("Sample PINs to test in mobile app:")
        print("┌────────────┬────────────────┬───────────────────────┬────────────┐")
        print("│ PIN        │ Driver         │ Scheduled Time        │ Status     │")
        print("├────────────┼────────────────┼───────────────────────┼────────────┤")
        
        for i, appt in enumerate(appointments[:10]):  # Show first 10 appointments
            driver = drivers[i % len(drivers)]
            time_str = appt.scheduled_start_time.strftime('%H:%M') if appt.scheduled_start_time else '--:--'
            pin_display = appt.arrival_id or "PRT-XXXX"  # Handle None
            print(f"│ {pin_display:<10} │ {driver.drivers_license:<14} │ {today.strftime('%Y-%m-%d')} {time_str:<7} │ {appt.status:<10} │")
        
        print("│ ...        │ ...            │ ...                   │ ...        │")
        print("└────────────┴────────────────┴───────────────────────┴────────────┘")
        
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
        init_data(db)
    finally:
        db.close()

if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://user:password@localhost/porto_db"
    print("Using DATABASE_URL =", DATABASE_URL)
    create_and_seed(DATABASE_URL)
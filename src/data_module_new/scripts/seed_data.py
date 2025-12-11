#!/usr/bin/env python3
"""
Database Seed Script for Port Logistics Management System.

This script populates all database tables with sample data for development and testing.
Run: python scripts/seed_data.py

Tables populated:
- InfrastructureZone (3 entries)
- Gate (7 entries) 
- InternalLocation (7 entries)
- HaulerCompany (3 entries)
- Truck (7 entries)
- Driver (7 entries)
- Cargo (7 entries)
- Booking (7 entries)
- Appointment (7 entries)
- GateVisit (7 entries)
- VisitEventLog (7 entries)
- AIRecognitionEvent (7 entries)
- AICorrection (3 entries)
- SystemResourceMetrics (3 entries)
- Shift (3 entries)
- Worker (3 entries)
- AccessDecision (5 entries)
"""

import asyncio
import sys
from datetime import datetime, timedelta, time
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models import (
    Base,
    InfrastructureZone,
    Gate,
    InternalLocation,
    HaulerCompany,
    Truck,
    Driver,
    Cargo,
    Booking,
    Appointment,
    GateVisit,
    VisitEventLog,
    AIRecognitionEvent,
    AICorrection,
    SystemResourceMetrics,
    Shift,
    Worker,
    AccessDecision,
)


settings = get_settings()


async def create_enums(session: AsyncSession):
    """Create PostgreSQL enum types if they don't exist."""
    enum_definitions = [
        "CREATE TYPE IF NOT EXISTS zone_type AS ENUM ('YARD', 'WAREHOUSE', 'GATE_COMPLEX', 'INSPECTION')",
        "CREATE TYPE IF NOT EXISTS gate_direction AS ENUM ('INBOUND', 'OUTBOUND')",
        "CREATE TYPE IF NOT EXISTS gate_operational_status AS ENUM ('OPEN', 'CLOSED', 'MAINTENANCE')",
        "CREATE TYPE IF NOT EXISTS location_usage_status AS ENUM ('EMPTY', 'OCCUPIED', 'RESERVED')",
        "CREATE TYPE IF NOT EXISTS chassis_type AS ENUM ('FLATBED', 'SKELETAL', 'BOX')",
        "CREATE TYPE IF NOT EXISTS emission_standard AS ENUM ('EURO5', 'EURO6', 'EV')",
        "CREATE TYPE IF NOT EXISTS appointment_direction AS ENUM ('IMPORT', 'EXPORT')",
        "CREATE TYPE IF NOT EXISTS appointment_status AS ENUM ('CREATED', 'CONFIRMED', 'COMPLETED', 'MISSED', 'CANCELLED')",
        "CREATE TYPE IF NOT EXISTS visit_stage AS ENUM ('AT_GATE', 'ROUTED', 'IN_YARD', 'SERVICING', 'EXIT_QUEUE', 'COMPLETE')",
        "CREATE TYPE IF NOT EXISTS event_type AS ENUM ('GATE_CHECK_IN', 'ARRIVED_AT_STACK', 'LIFT_ON_START', 'LIFT_ON_END', 'GATE_OUT')",
        "CREATE TYPE IF NOT EXISTS ai_object_class AS ENUM ('TRUCK', 'CONTAINER', 'HAZMAT_SIGN')",
        "CREATE TYPE IF NOT EXISTS ai_reason_code AS ENUM ('OCR_ERROR', 'MISCLASSIFICATION', 'GLARE', 'OCCLUSION')",
        "CREATE TYPE IF NOT EXISTS shift_type AS ENUM ('MORNING', 'AFTERNOON', 'NIGHT')",
        "CREATE TYPE IF NOT EXISTS decision_status AS ENUM ('APPROVED', 'REJECTED', 'MANUAL_REVIEW', 'OVERRIDDEN')",
    ]
    
    for enum_sql in enum_definitions:
        try:
            # PostgreSQL 9.x doesn't have CREATE TYPE IF NOT EXISTS
            # We need to check if type exists first
            type_name = enum_sql.split("CREATE TYPE IF NOT EXISTS ")[1].split(" AS")[0]
            check_sql = f"SELECT 1 FROM pg_type WHERE typname = '{type_name}'"
            result = await session.execute(text(check_sql))
            if not result.scalar():
                create_sql = enum_sql.replace("IF NOT EXISTS ", "")
                await session.execute(text(create_sql))
        except Exception as e:
            print(f"Note: {e}")
    
    await session.commit()


async def seed_infrastructure_zones(session: AsyncSession) -> list[InfrastructureZone]:
    """Seed infrastructure zones."""
    print("Seeding InfrastructureZones...")
    
    zones = [
        InfrastructureZone(
            zone_id=1,
            zone_code="GATE-A",
            zone_name="Main Gate Complex A",
            zone_type="GATE_COMPLEX",
            is_hazmat_approved=False,
            max_capacity_teu=None
        ),
        InfrastructureZone(
            zone_id=2,
            zone_code="YARD-01",
            zone_name="Container Yard North",
            zone_type="YARD",
            is_hazmat_approved=True,
            max_capacity_teu=5000
        ),
        InfrastructureZone(
            zone_id=3,
            zone_code="WH-MAIN",
            zone_name="Main Warehouse",
            zone_type="WAREHOUSE",
            is_hazmat_approved=False,
            max_capacity_teu=2000
        ),
    ]
    
    for zone in zones:
        session.add(zone)
    await session.flush()
    return zones


async def seed_gates(session: AsyncSession) -> list[Gate]:
    """Seed gates."""
    print("Seeding Gates...")
    
    gates = [
        Gate(gate_id=1, zone_id=1, gate_label="Gate A1 - Entry", direction="INBOUND", 
             camera_rtsp_url="rtsp://192.168.1.101:554/stream1", barrier_device_id="BAR-A1", 
             operational_status="OPEN"),
        Gate(gate_id=2, zone_id=1, gate_label="Gate A2 - Entry", direction="INBOUND",
             camera_rtsp_url="rtsp://192.168.1.102:554/stream1", barrier_device_id="BAR-A2",
             operational_status="OPEN"),
        Gate(gate_id=3, zone_id=1, gate_label="Gate A3 - Exit", direction="OUTBOUND",
             camera_rtsp_url="rtsp://192.168.1.103:554/stream1", barrier_device_id="BAR-A3",
             operational_status="OPEN"),
        Gate(gate_id=4, zone_id=1, gate_label="Gate A4 - Exit", direction="OUTBOUND",
             camera_rtsp_url="rtsp://192.168.1.104:554/stream1", barrier_device_id="BAR-A4",
             operational_status="MAINTENANCE"),
        Gate(gate_id=5, zone_id=2, gate_label="Yard Gate North", direction="INBOUND",
             camera_rtsp_url="rtsp://192.168.1.105:554/stream1", barrier_device_id="BAR-YN",
             operational_status="OPEN"),
        Gate(gate_id=6, zone_id=2, gate_label="Yard Gate South", direction="OUTBOUND",
             camera_rtsp_url="rtsp://192.168.1.106:554/stream1", barrier_device_id="BAR-YS",
             operational_status="OPEN"),
        Gate(gate_id=7, zone_id=3, gate_label="Warehouse Gate", direction="INBOUND",
             camera_rtsp_url="rtsp://192.168.1.107:554/stream1", barrier_device_id="BAR-WH",
             operational_status="CLOSED"),
    ]
    
    for gate in gates:
        session.add(gate)
    await session.flush()
    return gates


async def seed_internal_locations(session: AsyncSession) -> list[InternalLocation]:
    """Seed internal locations."""
    print("Seeding InternalLocations...")
    
    locations = [
        InternalLocation(location_id=1, zone_id=2, aisle_number="A01", bay_number="B01", tier_height=1, current_usage_status="EMPTY"),
        InternalLocation(location_id=2, zone_id=2, aisle_number="A01", bay_number="B02", tier_height=1, current_usage_status="OCCUPIED"),
        InternalLocation(location_id=3, zone_id=2, aisle_number="A01", bay_number="B03", tier_height=2, current_usage_status="EMPTY"),
        InternalLocation(location_id=4, zone_id=2, aisle_number="A02", bay_number="B01", tier_height=1, current_usage_status="RESERVED"),
        InternalLocation(location_id=5, zone_id=2, aisle_number="A02", bay_number="B02", tier_height=2, current_usage_status="EMPTY"),
        InternalLocation(location_id=6, zone_id=3, aisle_number="W01", bay_number="S01", tier_height=1, current_usage_status="OCCUPIED"),
        InternalLocation(location_id=7, zone_id=3, aisle_number="W01", bay_number="S02", tier_height=1, current_usage_status="EMPTY"),
    ]
    
    for loc in locations:
        session.add(loc)
    await session.flush()
    return locations


async def seed_hauler_companies(session: AsyncSession) -> list[HaulerCompany]:
    """Seed hauler companies."""
    print("Seeding HaulerCompanies...")
    
    haulers = [
        HaulerCompany(
            hauler_id=1,
            company_name="Atlantic Transport Solutions",
            tax_id="PT123456789",
            api_key="ats_api_key_abc123",
            safety_rating=Decimal("4.75")
        ),
        HaulerCompany(
            hauler_id=2,
            company_name="Porto Logistics Express",
            tax_id="PT987654321",
            api_key="ple_api_key_xyz789",
            safety_rating=Decimal("4.50")
        ),
        HaulerCompany(
            hauler_id=3,
            company_name="Iberian Freight Services",
            tax_id="ES12345678A",
            api_key="ifs_api_key_def456",
            safety_rating=Decimal("4.90")
        ),
    ]
    
    for hauler in haulers:
        session.add(hauler)
    await session.flush()
    return haulers


async def seed_trucks(session: AsyncSession) -> list[Truck]:
    """Seed trucks."""
    print("Seeding Trucks...")
    
    trucks = [
        Truck(truck_id=1, hauler_id=1, license_plate="PT-12-AB", country_of_registration="PRT", 
              chassis_type="SKELETAL", emission_standard="EURO6", last_seen_date=datetime.utcnow()),
        Truck(truck_id=2, hauler_id=1, license_plate="PT-34-CD", country_of_registration="PRT",
              chassis_type="FLATBED", emission_standard="EURO6", last_seen_date=datetime.utcnow() - timedelta(days=1)),
        Truck(truck_id=3, hauler_id=2, license_plate="PT-56-EF", country_of_registration="PRT",
              chassis_type="BOX", emission_standard="EURO5", last_seen_date=datetime.utcnow() - timedelta(days=2)),
        Truck(truck_id=4, hauler_id=2, license_plate="PT-78-GH", country_of_registration="PRT",
              chassis_type="SKELETAL", emission_standard="EV", last_seen_date=datetime.utcnow()),
        Truck(truck_id=5, hauler_id=3, license_plate="ES-1234-ABC", country_of_registration="ESP",
              chassis_type="SKELETAL", emission_standard="EURO6", last_seen_date=datetime.utcnow() - timedelta(hours=6)),
        Truck(truck_id=6, hauler_id=3, license_plate="ES-5678-DEF", country_of_registration="ESP",
              chassis_type="FLATBED", emission_standard="EURO6", last_seen_date=datetime.utcnow() - timedelta(hours=12)),
        Truck(truck_id=7, hauler_id=1, license_plate="PT-90-IJ", country_of_registration="PRT",
              chassis_type="SKELETAL", emission_standard="EV", last_seen_date=None),
    ]
    
    for truck in trucks:
        session.add(truck)
    await session.flush()
    return trucks


async def seed_drivers(session: AsyncSession) -> list[Driver]:
    """Seed drivers."""
    print("Seeding Drivers...")
    
    drivers = [
        Driver(driver_id=1, hauler_id=1, license_number="DL-PT-001234", full_name="João Silva",
               mobile_device_token="fcm_token_joao_123", is_banned=False, biometric_hash="bio_hash_001"),
        Driver(driver_id=2, hauler_id=1, license_number="DL-PT-001235", full_name="Maria Santos",
               mobile_device_token="fcm_token_maria_456", is_banned=False, biometric_hash="bio_hash_002"),
        Driver(driver_id=3, hauler_id=2, license_number="DL-PT-002001", full_name="António Costa",
               mobile_device_token="fcm_token_antonio_789", is_banned=False, biometric_hash="bio_hash_003"),
        Driver(driver_id=4, hauler_id=2, license_number="DL-PT-002002", full_name="Ana Ferreira",
               mobile_device_token="fcm_token_ana_012", is_banned=False, biometric_hash="bio_hash_004"),
        Driver(driver_id=5, hauler_id=3, license_number="DL-ES-300001", full_name="Carlos García",
               mobile_device_token="fcm_token_carlos_345", is_banned=False, biometric_hash="bio_hash_005"),
        Driver(driver_id=6, hauler_id=3, license_number="DL-ES-300002", full_name="Elena Rodríguez",
               mobile_device_token="fcm_token_elena_678", is_banned=False, biometric_hash="bio_hash_006"),
        Driver(driver_id=7, hauler_id=1, license_number="DL-PT-001236", full_name="Pedro Oliveira",
               mobile_device_token=None, is_banned=True, biometric_hash="bio_hash_007"),
    ]
    
    for driver in drivers:
        session.add(driver)
    await session.flush()
    return drivers


async def seed_cargos(session: AsyncSession) -> list[Cargo]:
    """Seed cargos (containers)."""
    print("Seeding Cargos...")
    
    cargos = [
        Cargo(cargo_id=1, iso_code="MSCU1234567", size_type="40HC", tare_weight_kg=3800, max_payload_kg=26680),
        Cargo(cargo_id=2, iso_code="MAEU7654321", size_type="20ST", tare_weight_kg=2250, max_payload_kg=28250),
        Cargo(cargo_id=3, iso_code="CMAU9876543", size_type="40HC", tare_weight_kg=3900, max_payload_kg=26580),
        Cargo(cargo_id=4, iso_code="HLCU1111111", size_type="40ST", tare_weight_kg=3700, max_payload_kg=26780),
        Cargo(cargo_id=5, iso_code="OOLU2222222", size_type="20ST", tare_weight_kg=2300, max_payload_kg=28200),
        Cargo(cargo_id=6, iso_code="EISU3333333", size_type="40RF", tare_weight_kg=4500, max_payload_kg=25980),
        Cargo(cargo_id=7, iso_code="TCLU4444444", size_type="45HC", tare_weight_kg=4200, max_payload_kg=27280),
    ]
    
    for cargo in cargos:
        session.add(cargo)
    await session.flush()
    return cargos


async def seed_bookings(session: AsyncSession) -> list[Booking]:
    """Seed bookings."""
    print("Seeding Bookings...")
    
    bookings = [
        Booking(booking_id=1, booking_ref="BK-2024-001001", direction="IMPORT", cargo_id=1),
        Booking(booking_id=2, booking_ref="BK-2024-001002", direction="EXPORT", cargo_id=2),
        Booking(booking_id=3, booking_ref="BK-2024-001003", direction="IMPORT", cargo_id=3),
        Booking(booking_id=4, booking_ref="BK-2024-001004", direction="EXPORT", cargo_id=4),
        Booking(booking_id=5, booking_ref="BK-2024-001005", direction="IMPORT", cargo_id=5),
        Booking(booking_id=6, booking_ref="BK-2024-001006", direction="EXPORT", cargo_id=6),
        Booking(booking_id=7, booking_ref="BK-2024-001007", direction="IMPORT", cargo_id=7),
    ]
    
    for booking in bookings:
        session.add(booking)
    await session.flush()
    return bookings


async def seed_appointments(session: AsyncSession) -> list[Appointment]:
    """Seed appointments."""
    print("Seeding Appointments...")
    
    now = datetime.utcnow()
    
    appointments = [
        Appointment(
            appointment_id=1, booking_id=1, hauler_id=1, truck_id=1, driver_id=1,
            scheduled_start_time=now + timedelta(hours=1),
            scheduled_end_time=now + timedelta(hours=2),
            appointment_status="CONFIRMED"
        ),
        Appointment(
            appointment_id=2, booking_id=2, hauler_id=1, truck_id=2, driver_id=2,
            scheduled_start_time=now + timedelta(hours=2),
            scheduled_end_time=now + timedelta(hours=3),
            appointment_status="CONFIRMED"
        ),
        Appointment(
            appointment_id=3, booking_id=3, hauler_id=2, truck_id=3, driver_id=3,
            scheduled_start_time=now - timedelta(hours=1),
            scheduled_end_time=now,
            appointment_status="COMPLETED"
        ),
        Appointment(
            appointment_id=4, booking_id=4, hauler_id=2, truck_id=4, driver_id=4,
            scheduled_start_time=now + timedelta(hours=3),
            scheduled_end_time=now + timedelta(hours=4),
            appointment_status="CREATED"
        ),
        Appointment(
            appointment_id=5, booking_id=5, hauler_id=3, truck_id=5, driver_id=5,
            scheduled_start_time=now - timedelta(days=1),
            scheduled_end_time=now - timedelta(days=1) + timedelta(hours=1),
            appointment_status="MISSED"
        ),
        Appointment(
            appointment_id=6, booking_id=6, hauler_id=3, truck_id=6, driver_id=6,
            scheduled_start_time=now + timedelta(days=1),
            scheduled_end_time=now + timedelta(days=1, hours=1),
            appointment_status="CONFIRMED"
        ),
        Appointment(
            appointment_id=7, booking_id=7, hauler_id=1, truck_id=7, driver_id=1,
            scheduled_start_time=now + timedelta(days=2),
            scheduled_end_time=now + timedelta(days=2, hours=1),
            appointment_status="CREATED"
        ),
    ]
    
    for appt in appointments:
        session.add(appt)
    await session.flush()
    return appointments


async def seed_gate_visits(session: AsyncSession) -> list[GateVisit]:
    """Seed gate visits."""
    print("Seeding GateVisits...")
    
    now = datetime.utcnow()
    
    visits = [
        GateVisit(
            visit_id=1, appointment_id=1, truck_id=1, driver_id=1,
            entry_gate_id=1, exit_gate_id=None,
            gate_in_time=now - timedelta(minutes=30),
            gate_out_time=None,
            visit_stage="IN_YARD"
        ),
        GateVisit(
            visit_id=2, appointment_id=2, truck_id=2, driver_id=2,
            entry_gate_id=2, exit_gate_id=None,
            gate_in_time=now - timedelta(minutes=15),
            gate_out_time=None,
            visit_stage="AT_GATE"
        ),
        GateVisit(
            visit_id=3, appointment_id=3, truck_id=3, driver_id=3,
            entry_gate_id=1, exit_gate_id=3,
            gate_in_time=now - timedelta(hours=2),
            gate_out_time=now - timedelta(hours=1),
            visit_stage="COMPLETE"
        ),
        GateVisit(
            visit_id=4, appointment_id=None, truck_id=4, driver_id=4,
            entry_gate_id=2, exit_gate_id=None,
            gate_in_time=now - timedelta(hours=1),
            gate_out_time=None,
            visit_stage="SERVICING"
        ),
        GateVisit(
            visit_id=5, appointment_id=None, truck_id=5, driver_id=5,
            entry_gate_id=1, exit_gate_id=3,
            gate_in_time=now - timedelta(days=1, hours=3),
            gate_out_time=now - timedelta(days=1, hours=1),
            visit_stage="COMPLETE"
        ),
        GateVisit(
            visit_id=6, appointment_id=None, truck_id=6, driver_id=6,
            entry_gate_id=2, exit_gate_id=None,
            gate_in_time=now - timedelta(minutes=45),
            gate_out_time=None,
            visit_stage="ROUTED"
        ),
        GateVisit(
            visit_id=7, appointment_id=None, truck_id=1, driver_id=2,
            entry_gate_id=1, exit_gate_id=4,
            gate_in_time=now - timedelta(days=2, hours=5),
            gate_out_time=now - timedelta(days=2, hours=3),
            visit_stage="COMPLETE"
        ),
    ]
    
    for visit in visits:
        session.add(visit)
    await session.flush()
    return visits


async def seed_visit_event_logs(session: AsyncSession) -> list[VisitEventLog]:
    """Seed visit event logs."""
    print("Seeding VisitEventLogs...")
    
    now = datetime.utcnow()
    
    events = [
        VisitEventLog(log_id=1, visit_id=1, event_type="GATE_CHECK_IN", timestamp=now - timedelta(minutes=30),
                      location_id=None, description="Check-in at Gate A1"),
        VisitEventLog(log_id=2, visit_id=1, event_type="ARRIVED_AT_STACK", timestamp=now - timedelta(minutes=20),
                      location_id=2, description="Arrived at stack location A01-B02"),
        VisitEventLog(log_id=3, visit_id=2, event_type="GATE_CHECK_IN", timestamp=now - timedelta(minutes=15),
                      location_id=None, description="Check-in at Gate A2"),
        VisitEventLog(log_id=4, visit_id=3, event_type="GATE_CHECK_IN", timestamp=now - timedelta(hours=2),
                      location_id=None, description="Check-in at Gate A1"),
        VisitEventLog(log_id=5, visit_id=3, event_type="LIFT_ON_START", timestamp=now - timedelta(hours=1, minutes=30),
                      location_id=6, description="Lift-on operation started"),
        VisitEventLog(log_id=6, visit_id=3, event_type="LIFT_ON_END", timestamp=now - timedelta(hours=1, minutes=15),
                      location_id=6, description="Lift-on operation completed"),
        VisitEventLog(log_id=7, visit_id=3, event_type="GATE_OUT", timestamp=now - timedelta(hours=1),
                      location_id=None, description="Check-out at Gate A3"),
    ]
    
    for event in events:
        session.add(event)
    await session.flush()
    return events


async def seed_ai_recognition_events(session: AsyncSession) -> list[AIRecognitionEvent]:
    """Seed AI recognition events."""
    print("Seeding AIRecognitionEvents...")
    
    now = datetime.utcnow()
    
    ai_events = [
        AIRecognitionEvent(
            recognition_id=1, gate_id=1, timestamp=now - timedelta(minutes=31),
            object_class="TRUCK", detected_text="PT-12-AB", confidence_score=0.97,
            bounding_box_json={"x": 100, "y": 200, "width": 300, "height": 100},
            image_storage_path="/images/2024/12/10/gate1_001.jpg", processing_duration_ms=45
        ),
        AIRecognitionEvent(
            recognition_id=2, gate_id=1, timestamp=now - timedelta(minutes=30),
            object_class="CONTAINER", detected_text="MSCU1234567", confidence_score=0.92,
            bounding_box_json={"x": 150, "y": 250, "width": 400, "height": 200},
            image_storage_path="/images/2024/12/10/gate1_002.jpg", processing_duration_ms=52
        ),
        AIRecognitionEvent(
            recognition_id=3, gate_id=2, timestamp=now - timedelta(minutes=16),
            object_class="TRUCK", detected_text="PT-34-CD", confidence_score=0.89,
            bounding_box_json={"x": 120, "y": 220, "width": 320, "height": 110},
            image_storage_path="/images/2024/12/10/gate2_001.jpg", processing_duration_ms=48
        ),
        AIRecognitionEvent(
            recognition_id=4, gate_id=2, timestamp=now - timedelta(minutes=15),
            object_class="CONTAINER", detected_text="MAEU7654321", confidence_score=0.75,
            bounding_box_json={"x": 160, "y": 260, "width": 420, "height": 210},
            image_storage_path="/images/2024/12/10/gate2_002.jpg", processing_duration_ms=55
        ),
        AIRecognitionEvent(
            recognition_id=5, gate_id=1, timestamp=now - timedelta(hours=2),
            object_class="TRUCK", detected_text="PT-56-EF", confidence_score=0.96,
            bounding_box_json={"x": 110, "y": 210, "width": 310, "height": 105},
            image_storage_path="/images/2024/12/10/gate1_003.jpg", processing_duration_ms=42
        ),
        AIRecognitionEvent(
            recognition_id=6, gate_id=3, timestamp=now - timedelta(hours=1),
            object_class="TRUCK", detected_text="PT-56-3F", confidence_score=0.65,
            bounding_box_json={"x": 130, "y": 230, "width": 330, "height": 115},
            image_storage_path="/images/2024/12/10/gate3_001.jpg", processing_duration_ms=61
        ),
        AIRecognitionEvent(
            recognition_id=7, gate_id=1, timestamp=now - timedelta(days=1),
            object_class="CONTAINER", detected_text="HLCU1111111", confidence_score=0.99,
            bounding_box_json={"x": 170, "y": 270, "width": 430, "height": 220},
            image_storage_path="/images/2024/12/09/gate1_004.jpg", processing_duration_ms=38
        ),
    ]
    
    for event in ai_events:
        session.add(event)
    await session.flush()
    return ai_events


async def seed_shifts(session: AsyncSession) -> list[Shift]:
    """Seed shifts."""
    print("Seeding Shifts...")
    
    shifts = [
        Shift(shift_id=1, shift_type="MORNING", start_time=time(6, 0), end_time=time(14, 0),
              description="Morning shift - 6:00 to 14:00"),
        Shift(shift_id=2, shift_type="AFTERNOON", start_time=time(14, 0), end_time=time(22, 0),
              description="Afternoon shift - 14:00 to 22:00"),
        Shift(shift_id=3, shift_type="NIGHT", start_time=time(22, 0), end_time=time(6, 0),
              description="Night shift - 22:00 to 6:00"),
    ]
    
    for shift in shifts:
        session.add(shift)
    await session.flush()
    return shifts


async def seed_workers(session: AsyncSession) -> list[Worker]:
    """Seed workers."""
    print("Seeding Workers...")
    
    workers = [
        Worker(
            worker_id=1,
            full_name="Admin User",
            email="admin@portlogistics.com",
            password_hash=get_password_hash("admin123"),
            role="admin",
            assigned_gate_id=None,
            shift_id=1,
            is_active=True
        ),
        Worker(
            worker_id=2,
            full_name="Gate Operator 1",
            email="operator1@portlogistics.com",
            password_hash=get_password_hash("operator123"),
            role="operator",
            assigned_gate_id=1,
            shift_id=1,
            is_active=True
        ),
        Worker(
            worker_id=3,
            full_name="Gate Operator 2",
            email="operator2@portlogistics.com",
            password_hash=get_password_hash("operator123"),
            role="operator",
            assigned_gate_id=2,
            shift_id=2,
            is_active=True
        ),
    ]
    
    for worker in workers:
        session.add(worker)
    await session.flush()
    return workers


async def seed_ai_corrections(session: AsyncSession) -> list[AICorrection]:
    """Seed AI corrections."""
    print("Seeding AICorrections...")
    
    now = datetime.utcnow()
    
    corrections = [
        AICorrection(
            correction_id=1,
            recognition_id=4,
            corrected_value="MAEU7654321",
            operator_id=2,
            reason_code="OCR_ERROR",
            is_retrained=False,
            created_at=now - timedelta(minutes=10)
        ),
        AICorrection(
            correction_id=2,
            recognition_id=6,
            corrected_value="PT-56-EF",
            operator_id=2,
            reason_code="GLARE",
            is_retrained=True,
            created_at=now - timedelta(minutes=55)
        ),
        AICorrection(
            correction_id=3,
            recognition_id=3,
            corrected_value="PT-34-CD",
            operator_id=3,
            reason_code="OCCLUSION",
            is_retrained=False,
            created_at=now - timedelta(minutes=12)
        ),
    ]
    
    for correction in corrections:
        session.add(correction)
    await session.flush()
    return corrections


async def seed_system_metrics(session: AsyncSession) -> list[SystemResourceMetrics]:
    """Seed system resource metrics."""
    print("Seeding SystemResourceMetrics...")
    
    now = datetime.utcnow()
    
    metrics = [
        SystemResourceMetrics(
            metric_id=1,
            timestamp=now - timedelta(minutes=5),
            node_id="edge-node-01",
            cpu_usage_pct=45.2,
            gpu_usage_pct=78.5,
            power_consumption_watts=320.0,
            active_camera_streams=4,
            traffic_volume_in_gate=12
        ),
        SystemResourceMetrics(
            metric_id=2,
            timestamp=now - timedelta(minutes=10),
            node_id="edge-node-01",
            cpu_usage_pct=42.8,
            gpu_usage_pct=75.1,
            power_consumption_watts=315.0,
            active_camera_streams=4,
            traffic_volume_in_gate=10
        ),
        SystemResourceMetrics(
            metric_id=3,
            timestamp=now - timedelta(minutes=5),
            node_id="edge-node-02",
            cpu_usage_pct=38.5,
            gpu_usage_pct=62.3,
            power_consumption_watts=285.0,
            active_camera_streams=3,
            traffic_volume_in_gate=8
        ),
    ]
    
    for metric in metrics:
        session.add(metric)
    await session.flush()
    return metrics


async def seed_access_decisions(session: AsyncSession) -> list[AccessDecision]:
    """Seed access decisions."""
    print("Seeding AccessDecisions...")
    
    now = datetime.utcnow()
    
    decisions = [
        AccessDecision(
            decision_id=1,
            event_id="evt-2024-001",
            gate_id=1,
            decision="APPROVED",
            reason="All checks passed - valid appointment and time window",
            license_plate="PT-12-AB",
            un_number=None,
            kemler_code=None,
            plate_image_url="https://minio:9000/license-plates/gate-01/evt-2024-001/crop.jpg",
            hazard_image_url=None,
            route={"gate_id": 1, "destination": "YARD-01", "bay": "A01-B02"},
            alerts=[],
            lp_confidence=0.97,
            hz_confidence=None,
            reviewed_by=None,
            reviewed_at=None,
            original_decision=None,
            created_at=now - timedelta(minutes=30)
        ),
        AccessDecision(
            decision_id=2,
            event_id="evt-2024-002",
            gate_id=2,
            decision="APPROVED",
            reason="Valid appointment within time window",
            license_plate="PT-34-CD",
            un_number=None,
            kemler_code=None,
            plate_image_url="https://minio:9000/license-plates/gate-02/evt-2024-002/crop.jpg",
            hazard_image_url=None,
            route={"gate_id": 2, "destination": "WH-MAIN", "bay": "W01-S01"},
            alerts=[],
            lp_confidence=0.89,
            hz_confidence=None,
            reviewed_by=None,
            reviewed_at=None,
            original_decision=None,
            created_at=now - timedelta(minutes=15)
        ),
        AccessDecision(
            decision_id=3,
            event_id="evt-2024-003",
            gate_id=1,
            decision="REJECTED",
            reason="Vehicle not registered in arrivals system",
            license_plate="XX-99-ZZ",
            un_number=None,
            kemler_code=None,
            plate_image_url="https://minio:9000/license-plates/gate-01/evt-2024-003/crop.jpg",
            hazard_image_url=None,
            route=None,
            alerts=["Vehicle not registered in arrivals system"],
            lp_confidence=0.95,
            hz_confidence=None,
            reviewed_by=None,
            reviewed_at=None,
            original_decision=None,
            created_at=now - timedelta(hours=1)
        ),
        AccessDecision(
            decision_id=4,
            event_id="evt-2024-004",
            gate_id=1,
            decision="MANUAL_REVIEW",
            reason="Low confidence detection requires operator review",
            license_plate="PT-56-EF",
            un_number="1203",
            kemler_code="33",
            plate_image_url="https://minio:9000/license-plates/gate-01/evt-2024-004/crop.jpg",
            hazard_image_url="https://minio:9000/hazard-placards/gate-01/evt-2024-004/crop.jpg",
            route=None,
            alerts=["License plate detection confidence too low (0.65)", "Hazardous material detected - requires verification"],
            lp_confidence=0.65,
            hz_confidence=0.72,
            reviewed_by=None,
            reviewed_at=None,
            original_decision=None,
            created_at=now - timedelta(minutes=45)
        ),
        AccessDecision(
            decision_id=5,
            event_id="evt-2024-005",
            gate_id=2,
            decision="OVERRIDDEN",
            reason="Manual review: Operator verified plate manually - OCR error due to glare",
            license_plate="ES-1234-ABC",
            un_number=None,
            kemler_code=None,
            plate_image_url="https://minio:9000/license-plates/gate-02/evt-2024-005/crop.jpg",
            hazard_image_url=None,
            route={"gate_id": 2, "destination": "YARD-01", "bay": "A02-B01"},
            alerts=["License plate detection confidence too low (0.58)"],
            lp_confidence=0.58,
            hz_confidence=None,
            reviewed_by=2,
            reviewed_at=now - timedelta(minutes=20),
            original_decision="MANUAL_REVIEW",
            created_at=now - timedelta(minutes=25)
        ),
    ]
    
    for decision in decisions:
        session.add(decision)
    await session.flush()
    return decisions


async def main():
    """Main function to seed all data."""
    print("=" * 60)
    print("Port Logistics Database Seed Script")
    print("=" * 60)
    
    # Create async engine and session
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # Create enums first
            print("\nCreating PostgreSQL enum types...")
            await create_enums(session)
            
            # Seed data in order (respecting foreign key constraints)
            print("\n--- Seeding Database ---\n")
            
            await seed_infrastructure_zones(session)
            await seed_gates(session)
            await seed_internal_locations(session)
            await seed_hauler_companies(session)
            await seed_trucks(session)
            await seed_drivers(session)
            await seed_cargos(session)
            await seed_bookings(session)
            await seed_appointments(session)
            await seed_gate_visits(session)
            await seed_visit_event_logs(session)
            await seed_ai_recognition_events(session)
            await seed_shifts(session)
            await seed_workers(session)
            await seed_ai_corrections(session)
            await seed_system_metrics(session)
            await seed_access_decisions(session)
            
            # Commit all changes
            await session.commit()
            
            print("\n" + "=" * 60)
            print("✅ Database seeding completed successfully!")
            print("=" * 60)
            print("\nSummary:")
            print("  - InfrastructureZones: 3")
            print("  - Gates: 7")
            print("  - InternalLocations: 7")
            print("  - HaulerCompanies: 3")
            print("  - Trucks: 7")
            print("  - Drivers: 7")
            print("  - Cargos: 7")
            print("  - Bookings: 7")
            print("  - Appointments: 7")
            print("  - GateVisits: 7")
            print("  - VisitEventLogs: 7")
            print("  - AIRecognitionEvents: 7")
            print("  - Shifts: 3")
            print("  - Workers: 3")
            print("  - AICorrections: 3")
            print("  - SystemResourceMetrics: 3")
            print("  - AccessDecisions: 5")
            print("\nTest credentials:")
            print("  Admin: admin@portlogistics.com / admin123")
            print("  Operator: operator1@portlogistics.com / operator123")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Error during seeding: {e}")
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
"""
Trial data initializer — minimal seed for live demo.

Scenario
--------
  87AX60  → appointment in_transit  (no infraction yet)
             AI pipeline will detect hazmat placard → set highway_infraction=True
             Truck enters gate → in_transit → in_process → unloading → completed

A handful of completed/in_process appointments are also seeded so the
manager dashboard has something to display on first load.

Run:
    DATABASE_URL=postgresql://porto:porto@localhost:5433/porto_logistica \
        python scripts/data_init_trial.py
"""

import os
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from Data_Module.models.sql_models import (
        Alert, Appointment, Base, Booking, Cargo, Company, Dock, Driver,
        Gate, Manager, Operator, Shift, ShiftAlertHistory, ShiftType,
        Terminal, Truck, Visit, Worker,
    )
except Exception:
    try:
        from infrastructure.persistence.sql_models import (
            Alert, Appointment, Base, Booking, Cargo, Company, Dock, Driver,
            Gate, Manager, Operator, Shift, ShiftAlertHistory, ShiftType,
            Terminal, Truck, Visit, Worker,
        )
    except Exception as e:
        print("Error importing models:", e)
        sys.exit(1)


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def init_trial_data(db: Session):
    print("=" * 60)
    print("  TRIAL DATA INITIALIZER — 87AX60 DEMO FLOW")
    print("=" * 60)

    if db.query(Worker).first():
        print("\n  Data already exists — skipping.")
        print("  To reset: docker compose down -v && docker compose up -d")
        return

    try:
        today = date.today()
        now = datetime.now()

        # ── Workers ──────────────────────────────────────────────────────────
        print("\n  Creating workers...")
        manager_w = Worker(
            num_worker="MGR001", name="João Silva",
            email="manager@example.pt", phone="+351 910 000 001",
            password_hash=_hash("password123"), active=True,
        )
        operator_w = Worker(
            num_worker="OPR001", name="Maria Santos",
            email="worker@porto.pt", phone="+351 910 000 002",
            password_hash=_hash("password123"), active=True,
        )
        db.add_all([manager_w, operator_w])
        db.flush()
        db.add_all([
            Manager(num_worker="MGR001", access_level="admin"),
            Operator(num_worker="OPR001"),
        ])
        db.flush()

        # ── Company + Driver ──────────────────────────────────────────────────
        print("  Creating company and driver...")
        company = Company(
            nif="PT509123456", name="Transportes Aveiro Lda", contact="+351 234 567 890",
        )
        db.add(company)
        db.flush()

        driver = Driver(
            drivers_license="PT12345678", name="Oscar Almeida",
            company_nif=company.nif,
            password_hash=_hash("driver123"), active=True,
        )
        driver2 = Driver(
            drivers_license="PT23456789", name="Sofia Rodrigues",
            company_nif=company.nif,
            password_hash=_hash("driver123"), active=True,
        )
        db.add_all([driver, driver2])
        db.flush()

        # ── Trucks ────────────────────────────────────────────────────────────
        print("  Creating trucks...")
        truck_87 = Truck(
            license_plate="87AX60", brand="Scania R500", company_nif=company.nif,
        )
        truck_b1 = Truck(
            license_plate="68BSH8", brand="Volvo FH16", company_nif=company.nif,
        )
        truck_b2 = Truck(
            license_plate="92BLN3", brand="MAN TGX", company_nif=company.nif,
        )
        truck_b3 = Truck(
            license_plate="82BTN5", brand="DAF XF", company_nif=company.nif,
        )
        db.add_all([truck_87, truck_b1, truck_b2, truck_b3])
        db.flush()

        # ── Terminals ────────────────────────────────────────────────────────
        print("  Creating terminals...")
        terminal_norte = Terminal(
            name="Terminal Norte - Porto de Aveiro",
            latitude=Decimal("40.6520"), longitude=Decimal("-8.7430"),
            hazmat_approved=False,
        )
        terminal_liquidos = Terminal(
            name="Terminal de Granéis Líquidos - Porto de Aveiro",
            latitude=Decimal("40.6360"), longitude=Decimal("-8.7520"),
            hazmat_approved=True,
        )
        db.add_all([terminal_norte, terminal_liquidos])
        db.flush()

        # ── Docks ─────────────────────────────────────────────────────────────
        docks = [
            Dock(terminal_id=terminal_norte.id, bay_number="TN-CAIS-1",
                 latitude=Decimal("40.6522"), longitude=Decimal("-8.7428"), current_usage="operational"),
            Dock(terminal_id=terminal_norte.id, bay_number="TN-CAIS-2",
                 latitude=Decimal("40.6524"), longitude=Decimal("-8.7426"), current_usage="operational"),
            Dock(terminal_id=terminal_liquidos.id, bay_number="TGL-CAIS-1",
                 latitude=Decimal("40.6362"), longitude=Decimal("-8.7522"), current_usage="operational"),
            Dock(terminal_id=terminal_liquidos.id, bay_number="TGL-HAZMAT",
                 latitude=Decimal("40.6358"), longitude=Decimal("-8.7518"), current_usage="operational"),
        ]
        db.add_all(docks)
        db.flush()

        # ── Gates ─────────────────────────────────────────────────────────────
        print("  Creating gates...")
        gate_entry = Gate(
            label="Portaria 1 — Entrada Principal",
            latitude=Decimal("40.6460"), longitude=Decimal("-8.7470"),
        )
        gate_out = Gate(
            label="Portaria 2 — Saída",
            latitude=Decimal("40.6430"), longitude=Decimal("-8.7440"),
        )
        gate_highway = Gate(
            label="Gate 2 — Abordagem A25",
            latitude=Decimal("40.6500"), longitude=Decimal("-8.7500"),
        )
        db.add_all([gate_entry, gate_out, gate_highway])
        db.flush()

        # ── Shifts (today only) ───────────────────────────────────────────────
        print("  Creating shifts...")
        morning_shift = Shift(
            gate_id=gate_entry.id, shift_type=ShiftType.MORNING, date=today,
            operator_num_worker="OPR001", manager_num_worker="MGR001",
        )
        afternoon_shift = Shift(
            gate_id=gate_entry.id, shift_type=ShiftType.AFTERNOON, date=today,
            operator_num_worker="OPR001", manager_num_worker="MGR001",
        )
        night_shift = Shift(
            gate_id=gate_entry.id, shift_type=ShiftType.NIGHT, date=today,
            operator_num_worker="OPR001", manager_num_worker="MGR001",
        )
        highway_morning = Shift(
            gate_id=gate_highway.id, shift_type=ShiftType.MORNING, date=today,
            operator_num_worker="OPR001", manager_num_worker="MGR001",
        )
        highway_afternoon = Shift(
            gate_id=gate_highway.id, shift_type=ShiftType.AFTERNOON, date=today,
            operator_num_worker="OPR001", manager_num_worker="MGR001",
        )
        db.add_all([morning_shift, afternoon_shift, night_shift, highway_morning, highway_afternoon])
        db.flush()

        def _shift_for(dt: datetime):
            h = dt.hour
            if 6 <= h < 14:
                return morning_shift
            if 14 <= h < 22:
                return afternoon_shift
            return night_shift

        ref_counter = [0]

        def _ref(prefix="TRL"):
            ref_counter[0] += 1
            return f"{prefix}-{today.strftime('%Y%m%d')}-{ref_counter[0]:04d}"

        # ── 87AX60 — MAIN DEMO TRUCK (in_transit, no infraction yet) ────────
        # Scheduled 45 min ago → in_transit; AI will set infraction + transition later.
        print("\n  [DEMO] Creating 87AX60 appointment (in_transit, no infraction)...")
        sched_87 = now - timedelta(minutes=45)
        bk_87 = Booking(reference=_ref("DEMO"), direction="inbound")
        db.add(bk_87)
        db.flush()
        # Hazmat cargo — the placard will be detected by AgentC
        cargo_87 = Cargo(
            booking_reference=bk_87.reference,
            quantity=Decimal("22000"),
            state="liquid",
            description="Sulfuric acid (fuming) [UN:1831, Kemler:X886]",
        )
        db.add(cargo_87)
        db.flush()
        appt_87 = Appointment(
            booking_reference=bk_87.reference,
            driver_license=driver.drivers_license,
            truck_license_plate="87AX60",
            terminal_id=terminal_liquidos.id,
            gate_in_id=gate_highway.id,
            gate_out_id=None,
            scheduled_start_time=sched_87,
            expected_duration=45,
            status="in_transit",
            notes="HAZMAT: Sulfuric acid [UN:1831, Kemler:X886] — awaiting gate detection",
            highway_infraction=False,
        )
        db.add(appt_87)
        db.flush()
        print(f"    appointment_id={appt_87.id}  status=in_transit  highway_infraction=False")

        # ── Bonus appointments (give the dashboard some data) ─────────────────
        print("\n  Creating bonus appointments for dashboard context...")

        # 1 in_process (entered 20 min ago)
        sched_ip = now - timedelta(minutes=60)
        entry_ip = now - timedelta(minutes=20)
        bk_ip = Booking(reference=_ref(), direction="inbound")
        db.add(bk_ip)
        db.flush()
        db.add(Cargo(booking_reference=bk_ip.reference, quantity=Decimal("24000"),
                     state="solid", description="Ceramic tiles"))
        db.flush()
        appt_ip = Appointment(
            booking_reference=bk_ip.reference,
            driver_license=driver2.drivers_license,
            truck_license_plate="68BSH8",
            terminal_id=terminal_norte.id,
            gate_in_id=gate_entry.id, gate_out_id=None,
            scheduled_start_time=sched_ip,
            expected_duration=45,
            status="in_process",
            notes="Cargo: Ceramic tiles",
        )
        db.add(appt_ip)
        db.flush()
        shift_ip = _shift_for(entry_ip)
        db.add(Visit(
            appointment_id=appt_ip.id, shift_gate_id=shift_ip.gate_id,
            shift_type=shift_ip.shift_type, shift_date=shift_ip.date,
            entry_time=entry_ip, out_time=None, state="unloading",
        ))
        db.flush()

        # 2 completed (earlier today)
        for plate, drv, cargo_desc, offset_h in [
            ("92BLN3", driver,  "Paper pulp",    3),
            ("82BTN5", driver2, "Salt (Salinas)", 5),
        ]:
            sched_c = now - timedelta(hours=offset_h)
            bk_c = Booking(reference=_ref(), direction="inbound")
            db.add(bk_c)
            db.flush()
            db.add(Cargo(booking_reference=bk_c.reference, quantity=Decimal("20000"),
                         state="solid", description=cargo_desc))
            db.flush()
            truck_obj = db.query(Truck).filter_by(license_plate=plate).first()
            appt_c = Appointment(
                booking_reference=bk_c.reference,
                driver_license=drv.drivers_license,
                truck_license_plate=plate,
                terminal_id=terminal_norte.id,
                gate_in_id=gate_entry.id, gate_out_id=gate_out.id,
                scheduled_start_time=sched_c,
                expected_duration=40,
                status="completed",
                notes=f"Cargo: {cargo_desc}",
            )
            db.add(appt_c)
            db.flush()
            entry_c = sched_c + timedelta(minutes=5)
            shift_c = _shift_for(entry_c)
            db.add(Visit(
                appointment_id=appt_c.id, shift_gate_id=shift_c.gate_id,
                shift_type=shift_c.shift_type, shift_date=shift_c.date,
                entry_time=entry_c, out_time=entry_c + timedelta(minutes=40),
                state="completed",
            ))
            db.flush()

        # 1 scheduled (future)
        sched_f = datetime.combine(today, time(now.hour + 2 if now.hour < 22 else 23, 0))
        bk_f = Booking(reference=_ref(), direction="inbound")
        db.add(bk_f)
        db.flush()
        db.add(Cargo(booking_reference=bk_f.reference, quantity=Decimal("15000"),
                     state="solid", description="Auto parts"))
        db.flush()
        db.add(Appointment(
            booking_reference=bk_f.reference,
            driver_license=driver.drivers_license,
            truck_license_plate="68BSH8",
            terminal_id=terminal_norte.id,
            gate_in_id=gate_entry.id, gate_out_id=None,
            scheduled_start_time=sched_f,
            expected_duration=45,
            status="scheduled",
            notes="Cargo: Auto parts",
        ))
        db.flush()

        db.commit()

        print("\n" + "=" * 60)
        print("  TRIAL DATABASE INITIALIZED")
        print("=" * 60)
        print("""
┌──────────────────────────────────────────────────────────┐
│  LOGIN CREDENTIALS                                        │
├──────────────────────────────────────────────────────────┤
│  worker@porto.pt      │ password123  │ Operator           │
│  manager@example.pt   │ password123  │ Manager            │
├──────────────────────────────────────────────────────────┤
│  PT12345678  Oscar Almeida   │ driver123                 │
│  PT23456789  Sofia Rodrigues │ driver123                 │
└──────────────────────────────────────────────────────────┘

  DEMO FLOW (87AX60):
    1. status=in_transit, highway_infraction=False   ← seeded here
    2. AgentC detects HAZMAT placard → Decision Engine
       sets highway_infraction=True
    3. Truck arrives at gate → status=in_process
    4. Unloading → status=unloading → completed
""")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        db.rollback()
        raise


def _sync_to_keycloak(db) -> None:
    kc_url = os.getenv("KEYCLOAK_URL", "")
    kc_admin_pw = os.getenv("KC_ADMIN_PASSWORD", "")
    if not kc_url or not kc_admin_pw:
        print("\n  [KC-SYNC] KEYCLOAK_URL / KC_ADMIN_PASSWORD not set — skipping.")
        return

    try:
        import httpx as _httpx
    except ImportError:
        print("\n  [KC-SYNC] httpx not installed — skipping.")
        return

    kc_realm = os.getenv("KEYCLOAK_REALM", "intelligent-logistics")
    kc_admin_user = os.getenv("KC_ADMIN_USER", "admin")
    worker_pw = os.getenv("DEFAULT_WORKER_PASSWORD", "password123")
    driver_pw = os.getenv("DEFAULT_DRIVER_PASSWORD", "driver123")

    print(f"\n  [KC-SYNC] Syncing users to {kc_url} realm '{kc_realm}'...")
    try:
        r = _httpx.post(
            f"{kc_url}/realms/master/protocol/openid-connect/token",
            data={"grant_type": "password", "client_id": "admin-cli",
                  "username": kc_admin_user, "password": kc_admin_pw},
            timeout=15.0,
        )
        r.raise_for_status()
        token = r.json()["access_token"]
    except Exception as exc:
        print(f"\n  [KC-SYNC] Cannot reach Keycloak ({exc}) — skipping.")
        return

    admin_base = f"{kc_url}/admin/realms/{kc_realm}"
    headers = {"Authorization": f"Bearer {token}"}
    synced = 0

    def _assign_roles(user_id: str, role_names: list) -> None:
        r2 = _httpx.get(f"{admin_base}/roles", headers=headers, timeout=10.0)
        role_map = {ro["name"]: ro for ro in r2.json()}
        roles = [role_map[rn] for rn in role_names if rn in role_map]
        if roles:
            _httpx.post(f"{admin_base}/users/{user_id}/role-mappings/realm",
                        json=roles, headers=headers, timeout=10.0)

    def _upsert(username, password, email=None, first_name=None, realm_roles=None):
        nonlocal synced
        body = {"username": username, "enabled": True, "emailVerified": True}
        if email:
            body["email"] = email
        if first_name:
            body["firstName"] = first_name
        r2 = _httpx.post(f"{admin_base}/users", json=body, headers=headers, timeout=10.0)
        if r2.status_code == 409:
            return
        if r2.status_code not in (200, 201):
            print(f"  [KC-SYNC] Failed '{username}': {r2.status_code}")
            return
        r3 = _httpx.get(f"{admin_base}/users", params={"username": username, "exact": "true"},
                        headers=headers, timeout=10.0)
        users = r3.json()
        if not users:
            return
        user_id = users[0]["id"]
        _httpx.put(f"{admin_base}/users/{user_id}/reset-password",
                   json={"type": "password", "value": password, "temporary": False},
                   headers=headers, timeout=10.0)
        if realm_roles:
            _assign_roles(user_id, realm_roles)
        synced += 1

    for w in db.query(Worker).filter_by(active=True).all():
        role = "manager" if w.manager else "operator"
        _upsert(w.email, worker_pw, email=w.email, first_name=w.name, realm_roles=[role])

    for d in db.query(Driver).filter_by(active=True).all():
        _upsert(d.drivers_license, driver_pw, first_name=d.name, realm_roles=["driver"])

    print(f"  [KC-SYNC] Done — {synced} user(s) provisioned.")


def create_and_seed(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        init_trial_data(db)
        _sync_to_keycloak(db)
    finally:
        db.close()


if __name__ == "__main__":
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is required")
    print(f"\n  Connecting to: {DATABASE_URL}\n")
    create_and_seed(DATABASE_URL)

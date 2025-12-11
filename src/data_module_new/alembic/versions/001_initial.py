"""Initial schema for Port Logistics Management System

Revision ID: 001_initial
Revises: 
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE zone_type AS ENUM ('YARD', 'WAREHOUSE', 'GATE_COMPLEX', 'INSPECTION')")
    op.execute("CREATE TYPE gate_direction AS ENUM ('INBOUND', 'OUTBOUND')")
    op.execute("CREATE TYPE gate_operational_status AS ENUM ('OPEN', 'CLOSED', 'MAINTENANCE')")
    op.execute("CREATE TYPE location_usage_status AS ENUM ('EMPTY', 'OCCUPIED', 'RESERVED')")
    op.execute("CREATE TYPE chassis_type AS ENUM ('FLATBED', 'SKELETAL', 'BOX')")
    op.execute("CREATE TYPE emission_standard AS ENUM ('EURO5', 'EURO6', 'EV')")
    op.execute("CREATE TYPE appointment_direction AS ENUM ('IMPORT', 'EXPORT')")
    op.execute("CREATE TYPE appointment_status AS ENUM ('CREATED', 'CONFIRMED', 'COMPLETED', 'MISSED', 'CANCELLED')")
    op.execute("CREATE TYPE visit_stage AS ENUM ('AT_GATE', 'ROUTED', 'IN_YARD', 'SERVICING', 'EXIT_QUEUE', 'COMPLETE')")
    op.execute("CREATE TYPE event_type AS ENUM ('GATE_CHECK_IN', 'ARRIVED_AT_STACK', 'LIFT_ON_START', 'LIFT_ON_END', 'GATE_OUT')")
    op.execute("CREATE TYPE ai_reason_code AS ENUM ('OCR_ERROR', 'MISCLASSIFICATION', 'GLARE', 'OCCLUSION')")
    op.execute("CREATE TYPE shift_type AS ENUM ('MORNING', 'AFTERNOON', 'NIGHT')")

    # Infrastructure tables
    op.create_table('infrastructure_zones',
        sa.Column('zone_id', sa.Integer(), primary_key=True),
        sa.Column('zone_code', sa.String(10), unique=True, nullable=False),
        sa.Column('zone_name', sa.String(100), nullable=False),
        sa.Column('zone_type', postgresql.ENUM('YARD', 'WAREHOUSE', 'GATE_COMPLEX', 'INSPECTION', name='zone_type', create_type=False), nullable=False),
        sa.Column('is_hazmat_approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('geo_polygon', geoalchemy2.types.Geometry(geometry_type='POLYGON', srid=4326), nullable=True),
        sa.Column('max_capacity_teu', sa.Integer(), nullable=True),
    )

    op.create_table('gates',
        sa.Column('gate_id', sa.Integer(), primary_key=True),
        sa.Column('zone_id', sa.Integer(), sa.ForeignKey('infrastructure_zones.zone_id'), nullable=False),
        sa.Column('gate_label', sa.String(50), nullable=False),
        sa.Column('direction', postgresql.ENUM('INBOUND', 'OUTBOUND', name='gate_direction', create_type=False), nullable=False),
        sa.Column('camera_rtsp_url', sa.String(255), nullable=True),
        sa.Column('barrier_device_id', sa.String(50), nullable=True),
        sa.Column('operational_status', postgresql.ENUM('OPEN', 'CLOSED', 'MAINTENANCE', name='gate_operational_status', create_type=False), nullable=False, server_default='OPEN'),
    )

    op.create_table('internal_locations',
        sa.Column('location_id', sa.BigInteger(), primary_key=True),
        sa.Column('zone_id', sa.Integer(), sa.ForeignKey('infrastructure_zones.zone_id'), nullable=False),
        sa.Column('aisle_number', sa.String(5), nullable=True),
        sa.Column('bay_number', sa.String(5), nullable=True),
        sa.Column('tier_height', sa.Integer(), nullable=True),
        sa.Column('current_usage_status', postgresql.ENUM('EMPTY', 'OCCUPIED', 'RESERVED', name='location_usage_status', create_type=False), nullable=False, server_default='EMPTY'),
    )

    # Hauler/Fleet tables
    op.create_table('hauler_companies',
        sa.Column('hauler_id', sa.Integer(), primary_key=True),
        sa.Column('company_name', sa.String(150), nullable=False),
        sa.Column('tax_id', sa.String(50), nullable=True),
        sa.Column('api_key', sa.String(256), nullable=True),
        sa.Column('safety_rating', sa.DECIMAL(3, 2), nullable=True),
    )

    op.create_table('trucks',
        sa.Column('truck_id', sa.BigInteger(), primary_key=True),
        sa.Column('hauler_id', sa.Integer(), sa.ForeignKey('hauler_companies.hauler_id'), nullable=True),
        sa.Column('license_plate', sa.String(20), unique=True, nullable=False, index=True),
        sa.Column('country_of_registration', sa.String(3), nullable=True),
        sa.Column('chassis_type', postgresql.ENUM('FLATBED', 'SKELETAL', 'BOX', name='chassis_type', create_type=False), nullable=True),
        sa.Column('emission_standard', postgresql.ENUM('EURO5', 'EURO6', 'EV', name='emission_standard', create_type=False), nullable=True),
        sa.Column('last_seen_date', sa.DateTime(), nullable=True),
    )

    op.create_table('drivers',
        sa.Column('driver_id', sa.BigInteger(), primary_key=True),
        sa.Column('hauler_id', sa.Integer(), sa.ForeignKey('hauler_companies.hauler_id'), nullable=True),
        sa.Column('license_number', sa.String(50), unique=True, nullable=True),
        sa.Column('full_name', sa.String(100), nullable=False),
        sa.Column('mobile_device_token', sa.String(255), nullable=True),
        sa.Column('is_banned', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('biometric_hash', sa.String(255), nullable=True),
    )

    # Cargo/Booking tables
    op.create_table('cargos',
        sa.Column('cargo_id', sa.BigInteger(), primary_key=True),
        sa.Column('iso_code', sa.String(11), unique=True, index=True, nullable=True),
        sa.Column('size_type', sa.String(4), nullable=True),
        sa.Column('tare_weight_kg', sa.Integer(), nullable=True),
        sa.Column('max_payload_kg', sa.Integer(), nullable=True),
    )

    op.create_table('bookings',
        sa.Column('booking_id', sa.BigInteger(), primary_key=True),
        sa.Column('booking_ref', sa.String(50), unique=True, nullable=False),
        sa.Column('direction', postgresql.ENUM('IMPORT', 'EXPORT', name='appointment_direction', create_type=False), nullable=False),
        sa.Column('cargo_id', sa.BigInteger(), sa.ForeignKey('cargos.cargo_id'), nullable=True),
    )

    # Appointment table
    op.create_table('appointments',
        sa.Column('appointment_id', sa.BigInteger(), primary_key=True),
        sa.Column('booking_id', sa.BigInteger(), sa.ForeignKey('bookings.booking_id'), nullable=True),
        sa.Column('hauler_id', sa.Integer(), sa.ForeignKey('hauler_companies.hauler_id'), nullable=True),
        sa.Column('truck_id', sa.BigInteger(), sa.ForeignKey('trucks.truck_id'), nullable=True),
        sa.Column('driver_id', sa.BigInteger(), sa.ForeignKey('drivers.driver_id'), nullable=True),
        sa.Column('scheduled_start_time', sa.DateTime(), nullable=False),
        sa.Column('scheduled_end_time', sa.DateTime(), nullable=False),
        sa.Column('appointment_status', postgresql.ENUM('CREATED', 'CONFIRMED', 'COMPLETED', 'MISSED', 'CANCELLED', name='appointment_status', create_type=False), nullable=False, server_default='CREATED'),
    )

    # Gate visits
    op.create_table('gate_visits',
        sa.Column('visit_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('appointment_id', sa.BigInteger(), sa.ForeignKey('appointments.appointment_id'), nullable=True),
        sa.Column('truck_id', sa.BigInteger(), sa.ForeignKey('trucks.truck_id'), nullable=True),
        sa.Column('driver_id', sa.BigInteger(), sa.ForeignKey('drivers.driver_id'), nullable=True),
        sa.Column('entry_gate_id', sa.Integer(), sa.ForeignKey('gates.gate_id'), nullable=True),
        sa.Column('exit_gate_id', sa.Integer(), sa.ForeignKey('gates.gate_id'), nullable=True),
        sa.Column('gate_in_time', sa.DateTime(), nullable=True),
        sa.Column('gate_out_time', sa.DateTime(), nullable=True),
        sa.Column('visit_stage', postgresql.ENUM('AT_GATE', 'ROUTED', 'IN_YARD', 'SERVICING', 'EXIT_QUEUE', 'COMPLETE', name='visit_stage', create_type=False), nullable=False, server_default='AT_GATE'),
    )

    op.create_table('visit_event_log',
        sa.Column('log_id', sa.BigInteger(), primary_key=True),
        sa.Column('visit_id', sa.BigInteger(), sa.ForeignKey('gate_visits.visit_id'), nullable=False),
        sa.Column('event_type', postgresql.ENUM('GATE_CHECK_IN', 'ARRIVED_AT_STACK', 'LIFT_ON_START', 'LIFT_ON_END', 'GATE_OUT', name='event_type', create_type=False), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('location_id', sa.BigInteger(), sa.ForeignKey('internal_locations.location_id'), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
    )

    # AI Recognition tables
    op.create_table('ai_recognition_events',
        sa.Column('recognition_id', sa.BigInteger(), primary_key=True),
        sa.Column('gate_id', sa.Integer(), sa.ForeignKey('gates.gate_id'), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('object_class', sa.String(50), nullable=True),
        sa.Column('detected_text', sa.String(50), nullable=True),
        sa.Column('confidence_score', sa.Float(), nullable=True),
        sa.Column('bounding_box_json', postgresql.JSONB(), nullable=True),
        sa.Column('image_storage_path', sa.String(255), nullable=True),
        sa.Column('processing_duration_ms', sa.Integer(), nullable=True),
    )

    # Shift table
    op.create_table('shifts',
        sa.Column('shift_id', sa.Integer(), primary_key=True),
        sa.Column('shift_type', postgresql.ENUM('MORNING', 'AFTERNOON', 'NIGHT', name='shift_type', create_type=False), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('description', sa.String(100), nullable=True),
    )

    # Worker table
    op.create_table('workers',
        sa.Column('worker_id', sa.Integer(), primary_key=True),
        sa.Column('full_name', sa.String(150), nullable=False),
        sa.Column('email', sa.String(255), unique=True, nullable=True),
        sa.Column('password_hash', sa.String(255), nullable=True),
        sa.Column('role', sa.String(50), nullable=False, server_default='operator'),
        sa.Column('assigned_gate_id', sa.Integer(), sa.ForeignKey('gates.gate_id'), nullable=True),
        sa.Column('shift_id', sa.Integer(), sa.ForeignKey('shifts.shift_id'), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    )

    # AI Corrections table
    op.create_table('ai_corrections',
        sa.Column('correction_id', sa.BigInteger(), primary_key=True),
        sa.Column('recognition_id', sa.BigInteger(), sa.ForeignKey('ai_recognition_events.recognition_id'), nullable=False),
        sa.Column('corrected_value', sa.String(50), nullable=True),
        sa.Column('operator_id', sa.Integer(), sa.ForeignKey('workers.worker_id'), nullable=True),
        sa.Column('reason_code', postgresql.ENUM('OCR_ERROR', 'MISCLASSIFICATION', 'GLARE', 'OCCLUSION', name='ai_reason_code', create_type=False), nullable=True),
        sa.Column('is_retrained', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    )

    # System metrics table
    op.create_table('system_resource_metrics',
        sa.Column('metric_id', sa.BigInteger(), primary_key=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('node_id', sa.String(50), nullable=False),
        sa.Column('cpu_usage_pct', sa.Float(), nullable=True),
        sa.Column('gpu_usage_pct', sa.Float(), nullable=True),
        sa.Column('power_consumption_watts', sa.Float(), nullable=True),
        sa.Column('active_camera_streams', sa.Integer(), nullable=True),
        sa.Column('traffic_volume_in_gate', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('system_resource_metrics')
    op.drop_table('ai_corrections')
    op.drop_table('workers')
    op.drop_table('shifts')
    op.drop_table('ai_recognition_events')
    op.drop_table('visit_event_log')
    op.drop_table('gate_visits')
    op.drop_table('appointments')
    op.drop_table('bookings')
    op.drop_table('cargos')
    op.drop_table('drivers')
    op.drop_table('trucks')
    op.drop_table('hauler_companies')
    op.drop_table('internal_locations')
    op.drop_table('gates')
    op.drop_table('infrastructure_zones')
    
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS shift_type")
    op.execute("DROP TYPE IF EXISTS ai_reason_code")
    op.execute("DROP TYPE IF EXISTS event_type")
    op.execute("DROP TYPE IF EXISTS visit_stage")
    op.execute("DROP TYPE IF EXISTS appointment_status")
    op.execute("DROP TYPE IF EXISTS appointment_direction")
    op.execute("DROP TYPE IF EXISTS emission_standard")
    op.execute("DROP TYPE IF EXISTS chassis_type")
    op.execute("DROP TYPE IF EXISTS location_usage_status")
    op.execute("DROP TYPE IF EXISTS gate_operational_status")
    op.execute("DROP TYPE IF EXISTS gate_direction")
    op.execute("DROP TYPE IF EXISTS zone_type")

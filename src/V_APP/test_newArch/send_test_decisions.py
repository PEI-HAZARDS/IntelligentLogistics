#!/usr/bin/env python3
"""
Script para enviar decisões de teste via Kafka com headers corretos.
Simula fluxo: MANUAL_REVIEW (agent) → ACCEPTED (operator)
"""

import sys
import os
import time
from datetime import datetime, timezone

# When running inside container, shared is at /app/shared
# When running from host, shared is at ../shared
try:
    from shared.src.kafka_wrapper import KafkaProducerWrapper
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../shared/src'))
    from kafka_wrapper import KafkaProducerWrapper

# Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:29092")
GATE_ID = os.getenv("GATE_ID", "1")
LICENSE_PLATE = os.getenv("LICENSE_PLATE", "AB-12-CD")
TRUCK_ID = f"test-truck-{int(time.time())}"

def create_decision_message(decision, decision_reason, decision_source, route=""):
    """Create decision message in format expected by consumer."""
    return {
        "message_type": "decision_results",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "license_plate": LICENSE_PLATE,
        "license_crop_url": f"http://minio:9000/crops/lp_{TRUCK_ID}.jpg",
        "un": "1203",
        "kemler": "33",
        "hazard_crop_url": f"http://minio:9000/crops/hz_{TRUCK_ID}.jpg",
        "alerts": [],
        "route": route,
        "decision": decision,
        "decision_reason": decision_reason,
        "decision_source": decision_source
    }

def main():
    print("=" * 60)
    print("  Test Decision Flow - MANUAL_REVIEW → ACCEPTED")
    print("=" * 60)
    print(f"Gate ID: {GATE_ID}")
    print(f"Truck ID: {TRUCK_ID}")
    print(f"License Plate: {LICENSE_PLATE}")
    print(f"Kafka Bootstrap: {KAFKA_BOOTSTRAP}")
    print()
    
    # Initialize producer
    print(f"Connecting to Kafka at {KAFKA_BOOTSTRAP}...")
    producer = KafkaProducerWrapper(KAFKA_BOOTSTRAP)
    print("✓ Connected to Kafka")
    print()
    
    # Step 1: Send AGENT decision (MANUAL_REVIEW)
    print("[1/2] Sending AGENT decision - MANUAL_REVIEW...")
    agent_topic = f"agent-decision-{GATE_ID}"
    agent_message = create_decision_message(
        decision="MANUAL_REVIEW",
        decision_reason="license_plate_not_found",
        decision_source="automated"
    )
    
    producer.produce(
        topic=agent_topic,
        data=agent_message,
        headers={"truckId": TRUCK_ID}
    )
    producer.flush()  # Ensure message is sent to Kafka
    print(f"✓ Agent decision sent to {agent_topic}")
    print(f"  Headers: truckId={TRUCK_ID}")
    print()
    
    # Wait for processing
    print("Waiting 5 seconds for Data Module to process...")
    time.sleep(5)
    
    # Step 2: Send OPERATOR decision (ACCEPTED)
    print("[2/2] Sending OPERATOR decision - ACCEPTED...")
    operator_topic = f"operator-decision-{GATE_ID}"
    operator_message = create_decision_message(
        decision="ACCEPTED",
        decision_reason="manual_operator_approval",
        decision_source="operator",
        route="North Gate"
    )
    
    producer.produce(
        topic=operator_topic,
        data=operator_message,
        headers={"truckId": TRUCK_ID}
    )
    producer.flush()  # Ensure message is sent to Kafka
    print(f"✓ Operator decision sent to {operator_topic}")
    print(f"  Headers: truckId={TRUCK_ID}")
    print()
    
    # Wait for final processing
    print("Waiting 3 seconds for Data Module to correlate and persist...")
    time.sleep(3)
    
    print("=" * 60)
    print("✓ Test messages sent successfully!")
    print("=" * 60)
    print()
    
    # Verification commands
    print("=" * 60)
    print("  Verification Commands")
    print("=" * 60)
    print()
    print("1. Check Data Module logs for correlation:")
    print(f"   docker logs dm_data_module --tail=50 | grep '{TRUCK_ID}'")
    print()
    print("2. Run full verification:")
    print(f"   ./verify_decision.sh {LICENSE_PLATE}")
    print()
    print("Expected logs in Data Module:")
    print(f"  - 'Agent MANUAL_REVIEW for truck_id={TRUCK_ID}, waiting for operator decision'")
    print(f"  - 'Operator decision received for truck_id={TRUCK_ID}, merging with agent decision'")
    print(f"  - 'Persisting final decision for truck_id={TRUCK_ID}'")
    print(f"  - 'Decision event persisted with id=...'")
    print(f"  - 'Appointment updated for license_plate={LICENSE_PLATE}'")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

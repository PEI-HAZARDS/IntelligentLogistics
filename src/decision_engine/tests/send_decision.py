#!/usr/bin/env python3
"""
Simulates the Decision Engine publishing a decision to Kafka.
Useful for testing downstream consumers without running the full pipeline.
"""

import json
import os
import time
from confluent_kafka import Producer

# Configuration from environment variables (same as DecisionEngine)
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", 1)
KAFKA_PRODUCE_TOPIC = f"decision-results-{GATE_ID}"


def create_sample_decision(
    license_plate: str = "AA-00-BB",
    un_number: str = "1203",
    kemler_code: str = "33",
    decision: str = "MANUAL_REVIEW",
    alerts: list = ["Alert 1", "Alert 2"],
    route: dict = None,
    lp_crop_url: str = "https://static.vecteezy.com/system/resources/previews/030/486/333/non_2x/sporting-cp-club-logo-symbol-portugal-league-football-abstract-design-illustration-with-green-background-free-vector.jpg",
    hz_crop_url: str = "https://img.iol.pt/image/id/682a3de7d34ef72ee4462382/1024"
) -> dict:
    """
    Creates a sample decision payload following the DecisionEngine format.
    
    Args:
        license_plate: The detected license plate
        un_number: The UN hazard number (or None)
        kemler_code: The Kemler hazard code (or None)
        decision: One of 'ACCEPTED', 'REJECTED', 'MANUAL_REVIEW'
        alerts: List of alert messages
        route: Route information dict with gate_id, terminal_id, appointment_id (defaults to None)
        lp_crop_url: URL to the license plate crop image
        hz_crop_url: URL to the hazmat placard crop image
    
    Returns:
        dict: The decision payload in the expected format
    """
    if alerts is None:
        alerts = []
    
    # Route stays None by default (no route assigned)
    
    un_data = f"{un_number}: Sample UN Description" if un_number else "No UN number detected"
    kemler_data = f"{kemler_code}: Sample Kemler Description" if kemler_code else "No Kemler code detected"
    
    return {
        "timestamp": int(time.time()),
        "gate_id": GATE_ID,
        "licensePlate": license_plate,
        "UN": un_data,
        "kemler": kemler_data,
        "alerts": alerts,
        "lp_cropUrl": lp_crop_url,
        "hz_cropUrl": hz_crop_url,
        "route": route,
        "decision": decision
    }


def publish_decision(truck_id: str, decision_data: dict):
    """
    Publishes a decision to the Kafka topic.
    
    Args:
        truck_id: Unique identifier for the truck
        decision_data: The decision payload dict
    """
    print(f"[SendDecision] Connecting to Kafka at '{KAFKA_BOOTSTRAP}'...")
    
    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "log_level": 1
    })
    
    payload = json.dumps(decision_data).encode("utf-8")
    
    print(f"[SendDecision] Publishing to '{KAFKA_PRODUCE_TOPIC}' for truck_id='{truck_id}'")
    print(f"[SendDecision] Decision: {decision_data['decision']}")
    print(f"[SendDecision] Payload: {json.dumps(decision_data, indent=2)}")
    
    producer.produce(
        topic=KAFKA_PRODUCE_TOPIC,
        key=truck_id.encode("utf-8"),
        value=payload,
        headers={"truck_id": truck_id}
    )
    
    # Wait for delivery
    producer.flush(timeout=10)
    print(f"[SendDecision] Message published successfully!")


def main():
    """Main function with example usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Simulate Decision Engine publishing a decision")
    parser.add_argument("--truck-id", default=f"TRK{int(time.time())}", help="Truck ID (default: auto-generated)")
    parser.add_argument("--license-plate", default="AA-00-BB", help="License plate")
    parser.add_argument("--un", default="1203", help="UN number")
    parser.add_argument("--kemler", default="33", help="Kemler code")
    parser.add_argument("--decision", choices=["ACCEPTED", "REJECTED", "MANUAL_REVIEW"], default="ACCEPTED", help="Decision")
    parser.add_argument("--alert", action="append", dest="alerts", help="Add alert message (can be used multiple times)")
    parser.add_argument("--lp-crop-url", help="License plate crop URL")
    parser.add_argument("--hz-crop-url", help="Hazmat crop URL")
    
    args = parser.parse_args()
    
    # Build kwargs, only including crop URLs if explicitly provided via CLI
    kwargs = {
        "license_plate": args.license_plate,
        "un_number": args.un,
        "kemler_code": args.kemler,
        "decision": args.decision,
        "alerts": args.alerts or ["Sporting Clube de Portugal", "Sporting 6 - 0 AFS"],
    }
    if args.lp_crop_url is not None:
        kwargs["lp_crop_url"] = args.lp_crop_url
    if args.hz_crop_url is not None:
        kwargs["hz_crop_url"] = args.hz_crop_url
    
    decision_data = create_sample_decision(**kwargs)
    
    publish_decision(args.truck_id, decision_data)


if __name__ == "__main__":
    main()

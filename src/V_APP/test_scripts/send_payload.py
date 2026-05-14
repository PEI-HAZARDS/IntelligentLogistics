"""
Usage:
    python send_payload.py decision
    python send_payload.py infraction
"""

import argparse
import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))

from shared.src.kafka_protocol import (
    KafkaTopicFactory,
    DecisionResultsMessage,
    InfractionDecisionMessage,
)
from shared.src.kafka_wrapper import KafkaProducerWrapper


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BROKER   = "10.255.32.70:9092"
GATE_ID  = "1"
TRUCK_ID = "truck-001"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LP_IMAGE   = "lp.png"
HZ_IMAGE   = "hz.png"


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------

def to_data_uri(filename: str) -> str:
    path = os.path.join(SCRIPT_DIR, filename)
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(filename)[1].lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    return f"data:{mime};base64,{encoded}"


# ---------------------------------------------------------------------------
# Payloads
# ---------------------------------------------------------------------------

def make_decision_message(lp_url: str, hz_url: str) -> DecisionResultsMessage:
    return DecisionResultsMessage(
        license_plate="87AX60",
        license_crop_url=lp_url,
        un="1831: Sulfuric acid, fuming with less than 30% free sulfur trioxide",
        kemler="X886: Highly corrosive substance, toxic, which reacts dangerously with water (water not to be used except by approval of experts)",
        hazard_crop_url=hz_url,
        alerts=[],
        route="GATE_1 → ZONE_A",
        decision="ACCEPTED",
        decision_reason="All checks passed, truck is authorized.",
        decision_source="automated",
    )


def make_infraction_message(lp_url: str, hz_url: str) -> InfractionDecisionMessage:
    return InfractionDecisionMessage(
        license_plate="87AX60",
        license_crop_url=lp_url,
        un="1831: Sulfuric acid, fuming with less than 30% free sulfur trioxide",
        kemler="X886: Highly corrosive substance, toxic, which reacts dangerously with water (water not to be used except by approval of experts)",
        hazard_crop_url=hz_url,
        infraction=True,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("type", choices=["decision", "infraction"])
    args = parser.parse_args()

    lp_url = to_data_uri(LP_IMAGE)
    hz_url = to_data_uri(HZ_IMAGE)

    if args.type == "decision":
        topic   = KafkaTopicFactory.agent_decision("1")
        message = make_decision_message(lp_url, hz_url)
    else:
        topic   = KafkaTopicFactory.infraction_decision("2")
        message = make_infraction_message(lp_url, hz_url)

    headers = {"truck_id": TRUCK_ID}

    print(f"Broker : {BROKER}")
    print(f"Topic  : {topic}")
    print(f"Truck  : {TRUCK_ID}")

    with KafkaProducerWrapper(BROKER) as producer:
        producer.produce(topic=topic, data=message.to_dict(), headers=headers)
        producer.flush()

    print("Message delivered.")


if __name__ == "__main__":
    main()

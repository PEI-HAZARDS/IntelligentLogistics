#!/usr/bin/env python3
"""
kafka_simulate.py  —  Kafka message simulator
==============================================
Sends all message types defined in kafka_protocol.py through
KafkaProducerWrapper with hardcoded default payloads.
Every field can be overridden at runtime via CLI flags.

Usage examples
--------------
# Send all messages with defaults
python kafka_simulate.py --bootstrap localhost:9092 --gate 1

# Override truck-detected fields
python kafka_simulate.py --bootstrap localhost:9092 --gate 1 \\
    --td-confidence 0.97 --td-num-detections 3

# Send only specific message types
python kafka_simulate.py --bootstrap localhost:9092 --gate 1 \\
    --only truck-detected lp-results

# Dry-run (print payloads, don't connect to Kafka)
python kafka_simulate.py --dry-run --gate 1

# Full override example
python kafka_simulate.py --bootstrap localhost:9092 --gate 2 \\
    --truck-id TRUCK-99 \\
    --td-confidence 0.88 --td-num-detections 2 \\
    --lp-plate "AB-1234" --lp-crop "http://cdn/lp.jpg" --lp-confidence 0.91 \\
    --hz-un "1203" --hz-kemler "33" --hz-crop "http://cdn/hz.jpg" --hz-confidence 0.85 \\
    --dr-plate "AB-1234" --dr-lp-crop "http://cdn/lp.jpg" \\
    --dr-un "1203" --dr-kemler "33" --dr-hz-crop "http://cdn/hz.jpg" \\
    --dr-alerts "FLAMMABLE" "SPEED_LIMIT" --dr-route "A1-NORTH" \\
    --dr-decision "STOP" --dr-reason "Hazardous cargo" --dr-source "agent" \\
    --ra-reason "agent_decision" \\
    --id-plate "AB-1234" --id-lp-crop "http://cdn/lp.jpg" \\
    --id-un "1203" --id-kemler "33" --id-hz-crop "http://cdn/hz.jpg" --id-infraction \\
    --sc-mode "scale_up"
"""

import argparse
import json
import logging
import sys
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Inline stubs so the script is self-contained when the real packages are
# absent (useful for dry-run / CI). When confluent_kafka IS installed the
# real KafkaProducerWrapper is used instead.
# ---------------------------------------------------------------------------

try:
    from confluent_kafka import KafkaException  # noqa: F401 — just test import
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False

# ---------------------------------------------------------------------------
# Locate kafka_protocol next to this script or fall back to the upload path
# ---------------------------------------------------------------------------
import importlib.util, os, sys

def _load_module(name: str, candidates: list):
    for path in candidates:
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            # Register under the requested name AND any dotted aliases so that
            # internal imports like `from shared.src.kafka_protocol import …`
            # resolve correctly regardless of how the project is installed.
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
            return mod
    raise ImportError(
        f"Could not find '{name}'. Place kafka_protocol.py and kafka_wrapper.py "
        "in the same directory as this script."
    )

_HERE = os.path.dirname(os.path.abspath(__file__))

protocol = _load_module("kafka_protocol", [
    os.path.join(_HERE, "kafka_protocol.py"),
    "/mnt/user-data/uploads/kafka_protocol.py",
])

# kafka_wrapper imports `from shared.src.kafka_protocol import …`
# Inject the already-loaded module under every alias it might use.
for _alias in ("shared.src.kafka_protocol", "src.kafka_protocol"):
    sys.modules.setdefault(_alias, protocol)

if _KAFKA_AVAILABLE:
    wrapper = _load_module("kafka_wrapper", [
        os.path.join(_HERE, "kafka_wrapper.py"),
        "/mnt/user-data/uploads/kafka_wrapper.py",
    ])
    KafkaProducerWrapper = wrapper.KafkaProducerWrapper
else:
    KafkaProducerWrapper = None  # dry-run only

KafkaTopicFactory    = protocol.KafkaTopicFactory
KafkaMessageProto    = protocol.KafkaMessageProto

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("kafka_simulate")

# ---------------------------------------------------------------------------
# Defaults — edit these to change what gets sent without any CLI flags
# ---------------------------------------------------------------------------
DEFAULTS = {
    "bootstrap":        "localhost:9092",
    "gate":             "1",
    "truck_id":         "TRUCK-001",
    "delay":            0.2,           # seconds between messages

    # TruckDetectedMessage
    "td_confidence":    0.95,
    "td_num_detections": 2,

    # LicensePlateResultsMessage
    "lp_plate":         "AA-00-BB",
    "lp_crop":          "https://img.iol.pt/image/id/682907c3d34ef72ee4461c1a/1024",
    "lp_confidence":    0.93,

    # HazardPlateResultsMessage
    "hz_un":            "1202",
    "hz_kemler":        "30",
    "hz_crop":          "https://img.iol.pt/image/id/682907c3d34ef72ee4461c1a/1024",
    "hz_confidence":    0.89,

    # DecisionResultsMessage
    "dr_plate":         "AA-00-BB",
    "dr_lp_crop":       "https://img.iol.pt/image/id/682907c3d34ef72ee4461c1a/1024",
    "dr_un":            "1202",
    "dr_kemler":        "30",
    "dr_hz_crop":       "https://img.iol.pt/image/id/682907c3d34ef72ee4461c1a/1024",
    "dr_alerts":        ["FLAMMABLE LIQUID"],
    "dr_route":         "HIGHWAY-A1",
    "dr_decision":      "ACCEPTED",
    "dr_reason":        "All checks passed",
    "dr_source":        "agent",

    # ResetAgentAMessage
    "ra_reason":        "agent_decision",

    # InfractionDecisionMessage
    "id_plate":         "AA-00-BB",
    "id_lp_crop":       "https://img.iol.pt/image/id/682907c3d34ef72ee4461c1a/1024",
    "id_un":            "1202",
    "id_kemler":        "30",
    "id_hz_crop":       "http://storage.local/crops/hz_001.jpg",
    "id_infraction":    True,

    # ScaleNetworkMessage
    "sc_mode":          "scale_up",
}

ALL_MESSAGE_TYPES = [
    "truck-detected",
    "lp-results",
    "hz-results",
    "agent-decision",
    "operator-decision",
    "reset-agent-a",
    "infraction-decision",
    "scale-up",
    "scale-down",
]

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Simulate Kafka messages for the truck-inspection pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Connection
    conn = p.add_argument_group("connection")
    conn.add_argument("--bootstrap", default=DEFAULTS["bootstrap"],
                      metavar="HOST:PORT",
                      help=f"Kafka bootstrap servers (default: {DEFAULTS['bootstrap']})")
    conn.add_argument("--gate", default=DEFAULTS["gate"],
                      metavar="GATE_ID",
                      help=f"Gate ID used in topic names (default: {DEFAULTS['gate']})")
    conn.add_argument("--truck-id", default=DEFAULTS["truck_id"],
                      metavar="ID",
                      help=f"truck_id header value (default: {DEFAULTS['truck_id']})")
    conn.add_argument("--delay", type=float, default=DEFAULTS["delay"],
                      metavar="SECS",
                      help=f"Delay between messages in seconds (default: {DEFAULTS['delay']})")
    conn.add_argument("--dry-run", action="store_true",
                      help="Print payloads without connecting to Kafka")
    conn.add_argument("--only", nargs="+", choices=ALL_MESSAGE_TYPES,
                      metavar="MSG_TYPE",
                      help=f"Send only these message types. Choices: {ALL_MESSAGE_TYPES}")

    # TruckDetected
    td = p.add_argument_group("truck-detected  (topic: truck-detected-<gate>)")
    td.add_argument("--td-confidence", type=float, default=None,
                    metavar="FLOAT", help=f"Detection confidence (default: {DEFAULTS['td_confidence']})")
    td.add_argument("--td-num-detections", type=int, default=None,
                    metavar="INT", help=f"Number of detections (default: {DEFAULTS['td_num_detections']})")

    # LicensePlateResults
    lp = p.add_argument_group("lp-results  (topic: lp-results-<gate>)")
    lp.add_argument("--lp-plate", default=None, metavar="STR",
                    help=f"License plate string (default: {DEFAULTS['lp_plate']})")
    lp.add_argument("--lp-crop", default=None, metavar="URL",
                    help=f"License plate crop URL (default: {DEFAULTS['lp_crop']})")
    lp.add_argument("--lp-confidence", type=float, default=None, metavar="FLOAT",
                    help=f"LP confidence (default: {DEFAULTS['lp_confidence']})")

    # HazardPlateResults
    hz = p.add_argument_group("hz-results  (topic: hz-results-<gate>)")
    hz.add_argument("--hz-un", default=None, metavar="STR",
                    help=f"UN hazard code (default: {DEFAULTS['hz_un']})")
    hz.add_argument("--hz-kemler", default=None, metavar="STR",
                    help=f"Kemler code (default: {DEFAULTS['hz_kemler']})")
    hz.add_argument("--hz-crop", default=None, metavar="URL",
                    help=f"Hazard plate crop URL (default: {DEFAULTS['hz_crop']})")
    hz.add_argument("--hz-confidence", type=float, default=None, metavar="FLOAT",
                    help=f"Hazard confidence (default: {DEFAULTS['hz_confidence']})")

    # DecisionResults  (agent-decision + operator-decision share same payload)
    dr = p.add_argument_group("agent-decision / operator-decision  (topic: *-decision-<gate>)")
    dr.add_argument("--dr-plate", default=None, metavar="STR",
                    help=f"License plate (default: {DEFAULTS['dr_plate']})")
    dr.add_argument("--dr-lp-crop", default=None, metavar="URL",
                    help=f"LP crop URL (default: {DEFAULTS['dr_lp_crop']})")
    dr.add_argument("--dr-un", default=None, metavar="STR",
                    help=f"UN code (default: {DEFAULTS['dr_un']})")
    dr.add_argument("--dr-kemler", default=None, metavar="STR",
                    help=f"Kemler code (default: {DEFAULTS['dr_kemler']})")
    dr.add_argument("--dr-hz-crop", default=None, metavar="URL",
                    help=f"Hazard crop URL (default: {DEFAULTS['dr_hz_crop']})")
    dr.add_argument("--dr-alerts", nargs="+", default=None, metavar="ALERT",
                    help=f"Alert strings (default: {DEFAULTS['dr_alerts']})")
    dr.add_argument("--dr-route", default=None, metavar="STR",
                    help=f"Route (default: {DEFAULTS['dr_route']})")
    dr.add_argument("--dr-decision", default=None, metavar="STR",
                    help=f"Decision (default: {DEFAULTS['dr_decision']})")
    dr.add_argument("--dr-reason", default=None, metavar="STR",
                    help=f"Decision reason (default: {DEFAULTS['dr_reason']})")
    dr.add_argument("--dr-source", default=None, metavar="STR",
                    help=f"Decision source (default: {DEFAULTS['dr_source']})")

    # ResetAgentA
    ra = p.add_argument_group("reset-agent-a  (topic: reset-agentA-<gate>)")
    ra.add_argument("--ra-reason", default=None, metavar="STR",
                    help=f"Reset reason (default: {DEFAULTS['ra_reason']})")

    # InfractionDecision
    id_ = p.add_argument_group("infraction-decision  (topic: infraction-decision-<gate>)")
    id_.add_argument("--id-plate", default=None, metavar="STR",
                     help=f"License plate (default: {DEFAULTS['id_plate']})")
    id_.add_argument("--id-lp-crop", default=None, metavar="URL",
                     help=f"LP crop URL (default: {DEFAULTS['id_lp_crop']})")
    id_.add_argument("--id-un", default=None, metavar="STR",
                     help=f"UN code (default: {DEFAULTS['id_un']})")
    id_.add_argument("--id-kemler", default=None, metavar="STR",
                     help=f"Kemler code (default: {DEFAULTS['id_kemler']})")
    id_.add_argument("--id-hz-crop", default=None, metavar="URL",
                     help=f"Hazard crop URL (default: {DEFAULTS['id_hz_crop']})")
    id_.add_argument("--id-infraction", action="store_true", default=None,
                     help=f"Set infraction=True (default: {DEFAULTS['id_infraction']})")
    id_.add_argument("--id-no-infraction", dest="id_infraction", action="store_false",
                     help="Set infraction=False")

    # ScaleNetwork
    sc = p.add_argument_group("scale-up / scale-down  (topics: scale-up / scale-down)")
    sc.add_argument("--sc-mode", default=None, choices=["scale_up", "scale_down"],
                    help=f"Scale mode (default: {DEFAULTS['sc_mode']})")

    return p


def d(args, key: str):
    """Return CLI override if set, else hardcoded default."""
    cli_val = getattr(args, key, None)
    return cli_val if cli_val is not None else DEFAULTS[key]


# ---------------------------------------------------------------------------
# Pretty print helpers
# ---------------------------------------------------------------------------
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def _banner(text: str):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")

def _sent(topic: str, truck_id: Optional[str], payload: dict):
    tid = f"  truck_id : {YELLOW}{truck_id}{RESET}" if truck_id else ""
    print(f"  {GREEN}✓ topic   : {topic}{RESET}{tid}")
    print(f"  payload  : {json.dumps(payload, indent=4)}")


# ---------------------------------------------------------------------------
# Sender abstraction
# ---------------------------------------------------------------------------

class MessageSender:
    def __init__(self, producer: Optional["KafkaProducerWrapper"], dry_run: bool):
        self.producer = producer
        self.dry_run  = dry_run

    def send(self, topic: str, message, truck_id: Optional[str] = None):
        payload = message.to_dict()
        headers = {"truck_id": truck_id} if truck_id else None

        _sent(topic, truck_id, payload)

        if not self.dry_run and self.producer:
            self.producer.produce(
                topic=topic,
                data=payload,
                key=truck_id,
                headers=headers,
            )


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def run(args):
    gate     = args.gate
    truck_id = args.truck_id
    only     = set(args.only) if args.only else set(ALL_MESSAGE_TYPES)

    # ── Producer setup ────────────────────────────────────────────────────
    producer = None
    if args.dry_run:
        log.info("DRY-RUN mode — no Kafka connection will be made")
    elif not _KAFKA_AVAILABLE:
        log.warning("confluent_kafka not installed — switching to dry-run mode")
        args.dry_run = True
    else:
        log.info(f"Connecting to Kafka at {args.bootstrap} …")
        try:
            producer = KafkaProducerWrapper(args.bootstrap)
            log.info("Producer ready")
        except Exception as exc:
            log.error(f"Could not create producer: {exc}")
            sys.exit(1)

    sender = MessageSender(producer, args.dry_run)

    # ── Build messages ────────────────────────────────────────────────────

    messages_to_send = []   # list of (label, topic, message, truck_id_or_None)

    # 1. TruckDetected
    if "truck-detected" in only:
        msg   = KafkaMessageProto.truck_detected(
            confidence     = d(args, "td_confidence"),
            num_detections = d(args, "td_num_detections"),
        )
        topic = KafkaTopicFactory.truck_detected(gate)
        messages_to_send.append(("TruckDetectedMessage", topic, msg, truck_id))

    # 2. LicensePlateResults
    if "lp-results" in only:
        msg   = KafkaMessageProto.license_plate_result(
            license_plate = d(args, "lp_plate"),
            crop_url      = d(args, "lp_crop"),
            confidence    = d(args, "lp_confidence"),
        )
        topic = KafkaTopicFactory.license_plate_results(gate)
        messages_to_send.append(("LicensePlateResultsMessage", topic, msg, truck_id))

    # 3. HazardPlateResults
    if "hz-results" in only:
        msg   = KafkaMessageProto.hazard_plate_result(
            un         = d(args, "hz_un"),
            kemler     = d(args, "hz_kemler"),
            crop_url   = d(args, "hz_crop"),
            confidence = d(args, "hz_confidence"),
        )
        topic = KafkaTopicFactory.hazard_plate_results(gate)
        messages_to_send.append(("HazardPlateResultsMessage", topic, msg, truck_id))

    # 4. AgentDecision  (DecisionResultsMessage)
    if "agent-decision" in only:
        msg   = KafkaMessageProto.decision_result(
            license_plate    = d(args, "dr_plate"),
            license_crop_url = d(args, "dr_lp_crop"),
            un               = d(args, "dr_un"),
            kemler           = d(args, "dr_kemler"),
            hazard_crop_url  = d(args, "dr_hz_crop"),
            alerts           = d(args, "dr_alerts"),
            route            = d(args, "dr_route"),
            decision         = d(args, "dr_decision"),
            decision_reason  = d(args, "dr_reason"),
            decision_source  = d(args, "dr_source"),
        )
        topic = KafkaTopicFactory.agent_decision(gate)
        messages_to_send.append(("DecisionResultsMessage [agent]", topic, msg, truck_id))

    # 5. OperatorDecision  (same payload, different topic)
    if "operator-decision" in only:
        msg   = KafkaMessageProto.decision_result(
            license_plate    = d(args, "dr_plate"),
            license_crop_url = d(args, "dr_lp_crop"),
            un               = d(args, "dr_un"),
            kemler           = d(args, "dr_kemler"),
            hazard_crop_url  = d(args, "dr_hz_crop"),
            alerts           = d(args, "dr_alerts"),
            route            = d(args, "dr_route"),
            decision         = d(args, "dr_decision"),
            decision_reason  = d(args, "dr_reason"),
            decision_source  = d(args, "dr_source"),
        )
        topic = KafkaTopicFactory.operator_decision(gate)
        messages_to_send.append(("DecisionResultsMessage [operator]", topic, msg, truck_id))

    # 6. ResetAgentA
    if "reset-agent-a" in only:
        msg   = KafkaMessageProto.reset_agent_a(reason=d(args, "ra_reason"))
        topic = KafkaTopicFactory.reset_agent_a(gate)
        # reset-agentA does NOT require truck_id (per KafkaTopicFactory.requires_truck_id)
        messages_to_send.append(("ResetAgentAMessage", topic, msg, None))

    # 7. InfractionDecision
    if "infraction-decision" in only:
        infraction_val = d(args, "id_infraction")
        msg   = KafkaMessageProto.infraction_decision(
            license_plate    = d(args, "id_plate"),
            license_crop_url = d(args, "id_lp_crop"),
            un               = d(args, "id_un"),
            kemler           = d(args, "id_kemler"),
            hazard_crop_url  = d(args, "id_hz_crop"),
            infraction       = bool(infraction_val),
        )
        topic = KafkaTopicFactory.infraction_decision(gate)
        messages_to_send.append(("InfractionDecisionMessage", topic, msg, truck_id))

    # 8. ScaleUp
    if "scale-up" in only:
        msg   = KafkaMessageProto.scale(gate_id=gate, mode="scale_up")
        topic = KafkaTopicFactory.scale_up()
        # Global topic — no truck_id
        messages_to_send.append(("ScaleNetworkMessage [scale_up]", topic, msg, None))

    # 9. ScaleDown
    if "scale-down" in only:
        msg   = KafkaMessageProto.scale(gate_id=gate, mode="scale_down")
        topic = KafkaTopicFactory.scale_down()
        # Global topic — no truck_id
        messages_to_send.append(("ScaleNetworkMessage [scale_down]", topic, msg, None))

    # ── Send ──────────────────────────────────────────────────────────────
    mode_label = "DRY-RUN" if args.dry_run else f"→ {args.bootstrap}"
    _banner(f"Kafka Message Simulator  [{mode_label}]  gate={gate}")
    print(f"  Sending {len(messages_to_send)} message(s)  |  delay={args.delay}s\n")

    for idx, (label, topic, msg, tid) in enumerate(messages_to_send, 1):
        print(f"{BOLD}[{idx}/{len(messages_to_send)}] {label}{RESET}")
        try:
            sender.send(topic, msg, truck_id=tid)
        except Exception as exc:
            log.error(f"Failed to send {label}: {exc}")

        if idx < len(messages_to_send) and args.delay > 0:
            time.sleep(args.delay)

    # ── Flush ─────────────────────────────────────────────────────────────
    if producer:
        log.info("Flushing producer …")
        producer.flush()
        producer.close()

    _banner(f"Done — {len(messages_to_send)} message(s) dispatched")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = build_parser()
    args   = parser.parse_args()
    run(args)
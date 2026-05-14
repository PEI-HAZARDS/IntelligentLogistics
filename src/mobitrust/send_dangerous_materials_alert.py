"""
Mobitrust Dangerous Materials Detection - MQTT Alert Sender
Sends activation and deactivation alerts to the Mobitrust MQTT broker over WebSocket (WSS).
"""

import json
import time
import ssl
import logging
import argparse
import paho.mqtt.client as mqtt  # type: ignore
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    broker_host: str
    broker_port: int
    broker_path: str
    mqtt_user: str
    mqtt_pass: str
    topic: str

    default_license_plate: str = "AA-00-BB"
    default_vehicle_type: str = "truck"
    default_latitude: float = 38.7169
    default_longitude: float = -9.1399
    default_zone_id: str = "ZONE-001"
    default_timer_duration_s: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra='ignore')

settings = Settings()


def build_payload(
    license_plate: str,
    vehicle_type: str,
    latitude: float,
    longitude: float,
    zone_id: str,
    active: bool,
    timer_duration_s: int | None = settings.default_timer_duration_s,
) -> dict:
    """Build the JSON payload according to the Mobitrust v3 spec."""
    payload = {
        "timestamp": int(time.time()),
        "event_type": "dangerous_materials_detection",
        "vehicle": {
            "license_plate": license_plate,
            "type": vehicle_type,
        },
        "location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "zone_id": zone_id,
        "control": {
            "mode": "timer" if timer_duration_s is not None else "manual",
            "active": active,
        },
    }
    if timer_duration_s is not None:
        payload["control"]["timer_duration_s"] = timer_duration_s
    return payload


def create_client() -> mqtt.Client:
    """Create and configure an MQTT client using WebSocket transport over TLS."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"mobitrust-sender-{int(time.time())}",
        transport="websockets",
    )

    # WebSocket path
    client.ws_set_options(path=settings.broker_path)

    # TLS (wss://)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)

    # Credentials
    client.username_pw_set(settings.mqtt_user, settings.mqtt_pass)

    # Callbacks
    client.on_connect    = _on_connect
    client.on_publish    = _on_publish
    client.on_disconnect = _on_disconnect

    return client


def _on_connect(client, userdata, flags, reason_code, properties):
    codes = {
        0: "Connected successfully",
        1: "Incorrect protocol version",
        2: "Invalid client identifier",
        3: "Server unavailable",
        4: "Bad username or password",
        5: "Not authorised",
    }
    logger.info(codes.get(reason_code.value, f"Unknown code {reason_code}"))


def _on_publish(client, userdata, mid, reason_code, properties):
    logger.info("Message delivered (mid=%s)", mid)


def _on_disconnect(client, userdata, flags, reason_code, properties):
    if reason_code.value == 0:
        logger.info("Clean disconnect.")
    else:
        logger.warning("Unexpected disconnect (rc=%s)", reason_code)


def send_alert(payload: dict) -> None:
    """Connect to the broker, publish one message, then disconnect."""
    client = create_client()

    logger.info("Connecting to wss://%s:%s%s …", settings.broker_host, settings.broker_port, settings.broker_path)
    try:
        client.connect(settings.broker_host, settings.broker_port, keepalive=30)
        client.loop_start()

        # Small delay to let the connection establish before publishing
        time.sleep(1)

        if not client.is_connected():
            logger.error("Failed to connect to broker. Check credentials and network.")
            client.loop_stop()
            return

        message = json.dumps(payload, indent=2)
        logger.info("Publishing to '%s':\n%s", settings.topic, message)

        result = client.publish(settings.topic, message, qos=1)
        result.wait_for_publish(timeout=10)

    except Exception as e:
        logger.exception("MQTT error")
    finally:
        client.loop_stop()
        client.disconnect()


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Send a Mobitrust dangerous-materials alert via MQTT over WSS."
    )
    parser.add_argument(
        "--action", choices=["activate", "deactivate"], default="activate",
        help="'activate' sets active=true; 'deactivate' sets active=false (default: activate)"
    )
    parser.add_argument("--plate",    default=settings.default_license_plate,    help="Vehicle licence plate")
    parser.add_argument("--type",     default=settings.default_vehicle_type,     help="Vehicle type (truck, van, …)")
    parser.add_argument("--lat",      type=float, default=settings.default_latitude,  help="Latitude (WGS84)")
    parser.add_argument("--lon",      type=float, default=settings.default_longitude, help="Longitude (WGS84)")
    parser.add_argument("--zone",     default=settings.default_zone_id,          help="Zone identifier")
    parser.add_argument("--timer",    type=int,   default=settings.default_timer_duration_s,
                        help="Timer duration in seconds (omit or 0 for manual mode)")

    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(message)s")
    args = parse_args()

    timer = args.timer if args.timer > 0 else None
    active = args.action == "activate"

    payload = build_payload(
        license_plate=args.plate,
        vehicle_type=args.type,
        latitude=args.lat,
        longitude=args.lon,
        zone_id=args.zone,
        active=active,
        timer_duration_s=timer,
    )

    send_alert(payload)


if __name__ == "__main__":
    main()

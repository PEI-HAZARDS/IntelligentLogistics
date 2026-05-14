# Mobitrust — Dangerous Materials Alert Sender

Sends **activation** and **deactivation** alerts to the Mobitrust MQTT broker over WebSocket (WSS).

## Files

| File | Purpose |
|------|---------|
| `send_dangerous_materials_alert.py` | Main script — builds payload, connects to broker, publishes alert |
| `.env` | Environment variables with real credentials/values |
| `.env.example` | Template showing which env vars are available |
| `requirements.txt` | Python dependencies |

## Configuration

All configuration is managed through **Pydantic `BaseSettings`**. Values are resolved in this priority (highest wins):

1. **System environment variables** (e.g. `export BROKER_HOST=...`)
2. **`.env` file** in the same directory
3. **Default values** hardcoded in the `Settings` class

| Env Variable | Description | Default |
|---|---|---|
| `BROKER_HOST` | MQTT broker hostname | **required** |
| `BROKER_PORT` | WSS port | **required** |
| `BROKER_PATH` | WebSocket path | **required** |
| `MQTT_USER` | Broker username | **required** |
| `MQTT_PASS` | Broker password | **required** |
| `TOPIC` | MQTT topic to publish on | **required** |
| `DEFAULT_LICENSE_PLATE` | Fallback plate for CLI | `AA-00-BB` |
| `DEFAULT_VEHICLE_TYPE` | Fallback vehicle type | `truck` |
| `DEFAULT_LATITUDE` | Fallback latitude (WGS84) | `40.633870` |
| `DEFAULT_LONGITUDE` | Fallback longitude (WGS84) | `-8.658579` |
| `DEFAULT_ZONE_ID` | Fallback zone identifier | `ZONE-001` |
| `DEFAULT_TIMER_DURATION_S` | Timer duration in seconds | `10` |

## How It Works

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  .env file   │────▶│  Pydantic        │────▶│  MQTT Client     │
│  + env vars  │     │  BaseSettings    │     │  (paho-mqtt v2)  │
└──────────────┘     └──────────────────┘     └────────┬─────────┘
                                                       │
                                                       │ WSS (TLS)
                                                       ▼
                                              ┌──────────────────┐
                                              │  Mobitrust MQTT  │
                                              │  Broker          │
                                              └──────────────────┘
```

1. **Settings are loaded** — `Settings()` reads from `.env` and environment variables, falling back to defaults.
2. **CLI arguments parsed** — the user can override payload fields (plate, location, zone, etc.) via command-line flags.
3. **Payload is built** — `build_payload()` constructs a JSON object following the Mobitrust v3 spec with vehicle info, location, and control mode (timer or manual).
4. **MQTT client connects** — `create_client()` sets up a paho-mqtt v2 client using **WebSocket transport over TLS (WSS)** on port 443.
5. **Alert is published** — the JSON payload is published to the configured MQTT topic with QoS 1 (at-least-once delivery).
6. **Client disconnects** — after the publish is acknowledged, the client cleanly disconnects.

## Usage

```bash
# Install dependencies
pip install -r requirements.txt

# Send an activation alert (defaults)
python send_dangerous_materials_alert.py

# Send a deactivation alert with custom plate and location
python send_dangerous_materials_alert.py --action deactivate --plate "AB-12-CD" --lat 41.1579 --lon -8.6291

# Manual mode (no timer)
python send_dangerous_materials_alert.py --timer 0
```

### CLI Arguments

| Flag | Description | Default |
|---|---|---|
| `--action` | `activate` or `deactivate` | `activate` |
| `--plate` | Vehicle licence plate | from settings |
| `--type` | Vehicle type | from settings |
| `--lat` | Latitude (WGS84) | from settings |
| `--lon` | Longitude (WGS84) | from settings |
| `--zone` | Zone identifier | from settings |
| `--timer` | Timer duration in seconds (0 = manual mode) | from settings |

## Example Payload

```json
{
  "timestamp": 1710765600,
  "event_type": "dangerous_materials_detection",
  "vehicle": {
    "license_plate": "AA-00-BB",
    "type": "truck"
  },
  "location": {
    "latitude": 38.7169,
    "longitude": -9.1399
  },
  "zone_id": "ZONE-001",
  "control": {
    "mode": "timer",
    "active": true,
    "timer_duration_s": 10
  }
}
```

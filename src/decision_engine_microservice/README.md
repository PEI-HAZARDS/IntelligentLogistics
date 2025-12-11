# Decision Engine

## Overview
The **Decision Engine** processes license plate (LP) and hazardous materials (HZ) recognition results for a given gate, queries the arrivals database, makes an access decision, publishes the decision, and stores it in Redis.

---

## Flow

### 1. Receive Recognition Results

The engine listens to two topics per gate:

#### **License Plate Results**
**Topic:** `lp-results-{GATE_ID}`

```json
{
  "timestamp": 123456789,
  "licensePlate": "AA-00-BB",
  "confidence": 87,
  "cropUrl": "http://image34567"
}
```

#### **Hazardous Materials Results**
**Topic:** `hz-results-{GATE_ID}`

```json
{
  "timestamp": 123456789,
  "UN": 1203,
  "kemler": 33,
  "confidence": 87,
  "cropUrl": "http://image68719"
}
```

---

### 2. Query Arrivals Database

The engine queries the Arrivals API to validate the incoming vehicle.

**Endpoint:**
```
GET http://localhost:8080/api/v1/decisions/query-arrivals
```

**Request Example:**
```bash
curl -X 'GET' \
  'http://localhost:8080/api/v1/decisions/query-arrivals' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "matricula": "AA-00-BB",
    "gate_id": 0
  }'
```

---

### 3. Make Decision

The decision logic is executed internally:

```text
self.make_decision()
```

The decision considers:
- License plate match
- Hazardous material classification (UN & Kemler codes)
- Database arrival permissions
- Confidence thresholds

---

### 4. Announce Decision

The final decision is published to a gate-specific topic.

#### **Topic:** `decision-{GATE_ID}`

```json
{
  "timestamp": 123451589,
  "licensePlate": "AA-00-BB",
  "UN": 1203,
  "kemler": 33,
  "alerts": [
    "Flammable liquid, toxic, corrosive, n.o.s.",
    "Flammable gas, which can spontaneously lead to violent reaction"
  ],
  "lp_cropUrl": "http://image68719",
  "hz_cropUrl": "http://image61948",
  "route": null,
  "decision": "ACCEPTED"
}
```

---

### 5. Persist Decision

The published decision is stored in the **Redis database** for:
- Auditing
- Monitoring
- Real-time dashboards
- Historical analysis

---

## Summary

```
LP Results + HZ Results
        ↓
Query Arrivals API
        ↓
Decision Engine Logic
        ↓
Publish decision-{GATE_ID}
        ↓
Store in Redis
```

✅ End of Decision Engine Flow
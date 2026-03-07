# Decision Flow Examples - MongoDB Documents

## Scenario 1: AUTOMATIC ACCEPTED

**Flow:** Agent detects → License plate matches → Automatic ACCEPTED → PostgreSQL updated

```json
{
  "_id": "65f1234567890abcdef12345",
  "decision_id": "dec_gate1_1708167002_42",
  "truck_id": "TRUCK-12345",
  "gate_id": 1,
  "appointment_id": 42,
  
  // AGGREGATED DETECTIONS (A+B+C)
  "agent_detections": {
    "truck_detection": {
      "detection_id": "det_AgentA_1708167000_001",
      "confidence": 0.98,
      "num_detections": 1,
      "crop_url": "http://minio:9000/crops/truck_12345.jpg",
      "timestamp": "2025-02-17T10:30:00Z"
    },
    "license_plate_detection": {
      "detection_id": "det_AgentB_1708167001_002",
      "license_plate": "AA-00-BB",
      "confidence": 0.87,
      "crop_url": "http://minio:9000/crops/lp_12345.jpg",
      "timestamp": "2025-02-17T10:30:01Z"
    },
    "hazmat_detection": {
      "detection_id": "det_AgentC_1708167001_003",
      "un_number": "1203",
      "kemler_code": "33",
      "confidence": 0.92,
      "crop_url": "http://minio:9000/crops/hz_12345.jpg",
      "timestamp": "2025-02-17T10:30:01Z"
    }
  },
  
  // DECISION ENGINE (AUTOMATED)
  "decision_engine": {
    "timestamp": "2025-02-17T10:30:02Z",
    "initial_decision": "ACCEPTED",  // Matched license plate
    "decision_reason": "license_plate_matched",
    "matched_license_plate": "AA-00-BB",
    "appointment_candidates": [
      { "appointment_id": 42, "license_plate": "AA-00-BB", "score": 0.95 }
    ],
    "processing_time_ms": 350,
    "decision_source": "automated"
  },
  
  // OPERATOR DECISION (NONE)
  "operator_decision": null,  // No human intervention needed
  
  // FINAL OUTCOME
  "final_decision": "ACCEPTED",  // From agent
  "final_decision_source": "agent",  // Automated
  
  // POSTGRESQL UPDATES
  "postgres_updates": {
    "appointment_updated": true,  // Appointment updated to IN_PROCESS
    "appointment_new_status": "IN_PROCESS",
    "alerts_created": 0,
    "update_timestamp": "2025-02-17T10:30:03Z"
  },
  
  // TIMING
  "timing": {
    "detection_to_decision_ms": 2000,
    "decision_to_persistence_ms": 150,
    "total_pipeline_ms": 2150,
    "manual_review_duration_ms": null  // No manual review
  },
  
  "created_at": "2025-02-17T10:30:03Z",
  "updated_at": "2025-02-17T10:30:03Z",
  "version": 1
}
```

---

## Scenario 2: MANUAL_REVIEW → ACCEPTED by Operator

**Flow:** Agent detects → License plate NOT found → MANUAL_REVIEW → Operator reviews → ACCEPTED → PostgreSQL updated

```json
{
  "_id": "65f1234567890abcdef67890",
  "decision_id": "dec_gate1_1708167302_43",
  "truck_id": "TRUCK-67890",
  "gate_id": 1,
  "appointment_id": 43,
  
  // AGGREGATED DETECTIONS (A+B+C)
  "agent_detections": {
    "truck_detection": {
      "detection_id": "det_AgentA_1708167300_004",
      "confidence": 0.95,
      "num_detections": 1,
      "crop_url": "http://minio:9000/crops/truck_67890.jpg",
      "timestamp": "2025-02-17T10:35:00Z"
    },
    "license_plate_detection": {
      "detection_id": "det_AgentB_1708167301_005",
      "license_plate": "XX-99-ZZ",  // Not in database
      "confidence": 0.75,
      "crop_url": "http://minio:9000/crops/lp_67890.jpg",
      "timestamp": "2025-02-17T10:35:01Z"
    },
    "hazmat_detection": {
      "detection_id": "det_AgentC_1708167301_006",
      "un_number": "1993",
      "kemler_code": "30",
      "confidence": 0.88,
      "crop_url": "http://minio:9000/crops/hz_67890.jpg",
      "timestamp": "2025-02-17T10:35:01Z"
    }
  },
  
  // DECISION ENGINE (AUTOMATED)
  "decision_engine": {
    "timestamp": "2025-02-17T10:35:02Z",
    "initial_decision": "MANUAL_REVIEW",  // License plate not found
    "decision_reason": "license_plate_not_found",
    "matched_license_plate": null,
    "appointment_candidates": [
      { "appointment_id": 43, "license_plate": "XX-00-ZZ", "score": 0.65 },  // Close but not enough
      { "appointment_id": 44, "license_plate": "XY-99-AA", "score": 0.45 }
    ],
    "processing_time_ms": 280,
    "decision_source": "automated"
  },
  
  // OPERATOR DECISION (ACCEPTED)
  "operator_decision": {
    "operator_decision": "ACCEPTED",  // Operator reviewed and accepted
    "operator_decision_reason": "Matrícula corrigida manualmente para XX-00-ZZ",
    "operator_timestamp": "2025-02-17T10:37:15Z"
  },
  
  // FINAL OUTCOME
  "final_decision": "ACCEPTED",  // From operator
  "final_decision_source": "operator",  // Human decision
  
  // POSTGRESQL UPDATES
  "postgres_updates": {
    "appointment_updated": true,  // Appointment updated after operator decision
    "appointment_new_status": "IN_PROCESS",
    "alerts_created": 0,
    "update_timestamp": "2025-02-17T10:37:16Z"
  },
  
  // TIMING
  "timing": {
    "detection_to_decision_ms": 2000,
    "decision_to_persistence_ms": 180,
    "total_pipeline_ms": 135180,  // Includes manual review time
    "manual_review_duration_ms": 133000  // ~2 minutes for operator review
  },
  
  "created_at": "2025-02-17T10:35:03Z",  // Initial agent decision
  "updated_at": "2025-02-17T10:37:16Z",  // Updated after operator decision
  "version": 1
}
```

---

## Scenario 3: MANUAL_REVIEW → REJECTED by Operator

**Flow:** Agent detects → MANUAL_REVIEW → Operator reviews → REJECTED → PostgreSQL NOT updated

```json
{
  "_id": "65f1234567890abcdef11111",
  "decision_id": "dec_gate1_1708167602_0",
  "truck_id": "TRUCK-11111",
  "gate_id": 1,
  "appointment_id": null,  // No appointment associated
  
  // AGGREGATED DETECTIONS (A+B+C)
  "agent_detections": {
    "truck_detection": {
      "detection_id": "det_AgentA_1708167600_007",
      "confidence": 0.91,
      "num_detections": 1,
      "crop_url": "http://minio:9000/crops/truck_11111.jpg",
      "timestamp": "2025-02-17T10:40:00Z"
    },
    "license_plate_detection": {
      "detection_id": "det_AgentB_1708167601_008",
      "license_plate": "ZZ-00-AA",
      "confidence": 0.82,
      "crop_url": "http://minio:9000/crops/lp_11111.jpg",
      "timestamp": "2025-02-17T10:40:01Z"
    },
    "hazmat_detection": {
      "detection_id": "det_AgentC_1708167601_009",
      "un_number": "N/A",
      "kemler_code": "N/A",
      "confidence": 0.0,
      "crop_url": null,
      "timestamp": "2025-02-17T10:40:01Z"
    }
  },
  
  // DECISION ENGINE (AUTOMATED)
  "decision_engine": {
    "timestamp": "2025-02-17T10:40:02Z",
    "initial_decision": "MANUAL_REVIEW",
    "decision_reason": "license_plate_not_found",
    "matched_license_plate": null,
    "appointment_candidates": [],
    "processing_time_ms": 200,
    "decision_source": "automated"
  },
  
  // OPERATOR DECISION (REJECTED)
  "operator_decision": {
    "operator_decision": "REJECTED",  // Operator rejected entry
    "operator_decision_reason": "Camião sem agendamento e sem documentação",
    "operator_timestamp": "2025-02-17T10:42:30Z"
  },
  
  // FINAL OUTCOME
  "final_decision": "REJECTED",  // From operator
  "final_decision_source": "operator",
  
  // POSTGRESQL UPDATES
  "postgres_updates": {
    "appointment_updated": false,  // NO update (rejected)
    "appointment_new_status": null,
    "alerts_created": 1,  // Alert created for rejected entry
    "update_timestamp": "2025-02-17T10:42:31Z"
  },
  
  // TIMING
  "timing": {
    "detection_to_decision_ms": 2000,
    "decision_to_persistence_ms": 150,
    "total_pipeline_ms": 150150,
    "manual_review_duration_ms": 148000  // ~2.5 minutes review
  },
  
  "created_at": "2025-02-17T10:40:03Z",
  "updated_at": "2025-02-17T10:42:31Z",
  "version": 1
}
```

---

## Summary Table

| Scenario | Agent Decision | Operator Decision | Final Decision | PostgreSQL Updated | Source |
|----------|----------------|-------------------|----------------|--------------------|--------|
| **Auto Accepted** | ACCEPTED | null | ACCEPTED | Yes (IN_PROCESS) | agent |
| **Manual → Accepted** | MANUAL_REVIEW | ACCEPTED | ACCEPTED | Yes (IN_PROCESS) | operator |
| **Manual → Rejected** | MANUAL_REVIEW | REJECTED | REJECTED | No | operator |

---

## Query Examples (Good for statistics)

### 1. Get all automatic accepted entries (last 24h)
```javascript
db.decision_events.find({
  "final_decision": "ACCEPTED",
  "final_decision_source": "agent",
  "created_at": { $gte: new Date(Date.now() - 86400000) }
})
```

### 2. Get all manual reviews pending operator decision
```javascript
db.decision_events.find({
  "decision_engine.initial_decision": "MANUAL_REVIEW",
  "operator_decision": null
})
```

### 3. Get operator performance (accepted vs rejected)
```javascript
db.decision_events.aggregate([
  { $match: { "final_decision_source": "operator" } },
  { $group: {
    _id: "$operator_decision.operator_decision",
    count: { $sum: 1 },
    avg_review_time_ms: { $avg: "$timing.manual_review_duration_ms" }
  }}
])
```

### 4. Get complete truck journey
```javascript
db.decision_events.findOne({ "truck_id": "TRUCK-12345" })
// Returns full document with all 3 agent detections + decisions
```

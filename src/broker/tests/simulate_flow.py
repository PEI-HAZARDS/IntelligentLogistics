import json
import time
import uuid
import os
import logging
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic

# Configuration
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", "1")

# Topics
TOPIC_TRUCK = f"truck-detected-{GATE_ID}"
TOPIC_LP = f"lp-results-{GATE_ID}"
TOPIC_HZ = f"hz-results-{GATE_ID}"
TOPIC_DECISION = f"decision-results-{GATE_ID}"

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SimulateFlow")

def get_producer():
    return Producer({
        'bootstrap.servers': KAFKA_BOOTSTRAP,
        'client.id': 'flow-simulator'
    })

def create_topics():
    """Create topics if they don't exist."""
    admin_client = AdminClient({'bootstrap.servers': KAFKA_BOOTSTRAP})
    
    # Check existing topics
    cluster_metadata = admin_client.list_topics(timeout=10)
    existing_topics = cluster_metadata.topics
    
    new_topics = []
    topics_to_check = [TOPIC_TRUCK, TOPIC_LP, TOPIC_HZ, TOPIC_DECISION]
    
    for topic in topics_to_check:
        if topic not in existing_topics:
            logger.info(f"Creating topic: {topic}")
            new_topics.append(NewTopic(topic, num_partitions=1, replication_factor=1))
        else:
            logger.info(f"Topic exists: {topic}")
            
    if new_topics:
        fs = admin_client.create_topics(new_topics)
        for topic, f in fs.items():
            try:
                f.result()  # The result itself is None
                logger.info(f"Topic created: {topic}")
            except Exception as e:
                logger.error(f"Failed to create topic {topic}: {e}")

def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")

def send_flow():
    create_topics()
    
    # Wait for consumers to register with partitions
    logger.info("Waiting 15 seconds for consumers to register...")
    time.sleep(15)
    
    producer = get_producer()
    truck_id = "TRK" + str(uuid.uuid4())[:8]
    
    logger.info(f"Starting simulation for Truck ID: {truck_id}")

    # --- Step 1: Truck Detected (Agent A) ---
    logger.info("--- Step 1: Sending Truck Detected (Agent A) ---")
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload_a = {
        "timestamp": timestamp,
        "confidence": 0.95,
        "detections": 1
    }
    
    producer.produce(
        TOPIC_TRUCK,
        key=truck_id.encode('utf-8'),
        value=json.dumps(payload_a).encode('utf-8'),
        headers={"truckId": truck_id},
        callback=delivery_report
    )
    producer.flush()
    time.sleep(2)

    # --- Step 2: License Plate (Agent B) ---
    logger.info("--- Step 2: Sending License Plate Results (Agent B) ---")
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload_b = {
        "timestamp": timestamp,
        "licensePlate": "58-76-TK",
        "confidence": 0.98,
        "cropUrl": "http://10.255.32.82:9000/lp-crops/demo_lp.jpg"
    }

    producer.produce(
        TOPIC_LP,
        key=truck_id.encode('utf-8'),
        value=json.dumps(payload_b).encode('utf-8'),
        headers={"truckId": truck_id},
        callback=delivery_report
    )
    producer.flush()
    time.sleep(2)

    # --- Step 3: Hazard Plate (Agent C) ---
    logger.info("--- Step 3: Sending Hazard Plate Results (Agent C) ---")
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload_c = {
        "timestamp": timestamp,
        "un": "1203",
        "kemler": "33",
        "confidence": 0.92,
        "cropUrl": "http://10.255.32.82:9000/hz-crops/demo_hz.jpg"
    }

    producer.produce(
        TOPIC_HZ,
        key=truck_id.encode('utf-8'),
        value=json.dumps(payload_c).encode('utf-8'),
        headers={"truckId": truck_id},
        callback=delivery_report
    )
    producer.flush()
    time.sleep(2)

    # --- Step 4: Decision (Decision Engine) ---
    logger.info("--- Step 4: Sending Decision (Decision Engine) ---")
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Simulating an ACCEPTED decision
    payload_d = {
        "timestamp": timestamp,
        "licensePlate": "58-76-TK",
        "UN": "1203: GASOLINE",
        "kemler": "33: highly flammable liquid (flash-point below 23°C)",
        "alerts": [],
        "lp_cropUrl": "http://10.255.32.82:9000/lp-crops/demo_lp.jpg",
        "hz_cropUrl": "http://10.255.32.82:9000/hz-crops/demo_hz.jpg",
        "route": {
            "gate_id": "1",
            "terminal_id": "T1",
            "appointment_id": "APT-12345"
        },
        "decision": "ACCEPTED"
    }

    producer.produce(
        TOPIC_DECISION,
        key=truck_id.encode('utf-8'),
        value=json.dumps(payload_d).encode('utf-8'),
        headers={"truck_id": truck_id}, # Note: Decision Engine uses 'truck_id' based on my reading, matching it.
        callback=delivery_report
    )
    producer.flush()
    
    logger.info("--- Simulation Complete ---")

if __name__ == "__main__":
    send_flow()

import os
import time
import uuid
import json
import pytest
from confluent_kafka import Producer, Consumer, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic


# ---- Config ----
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
REQUIRED_TOPICS = ["truck_detected", "lp_detected"]

# Se puseres esta env var a 1, os testes não criam nada e falham se faltar
STRICT_TOPICS = os.getenv("KAFKA_STRICT_TOPICS", "0") == "1"


def _admin():
    return AdminClient({"bootstrap.servers": BOOTSTRAP_SERVERS})


def _producer():
    return Producer({"bootstrap.servers": BOOTSTRAP_SERVERS})


def _consumer(group_id: str, topic: str):
    """
    Consumer para testes: usa earliest para não depender do timing
    (subscribe/assignment vs produção).
    """
    c = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": group_id,
            "auto.offset.reset": "earliest",  # <-- PATCH: mais robusto
            "enable.auto.commit": False,
        }
    )
    c.subscribe([topic])
    return c


def _wait_for_assignment(consumer, timeout=5.0):
    """Make sure the consumer has partitions assigned before producing."""
    start = time.time()
    while time.time() - start < timeout:
        consumer.poll(0.1)  # triggers join/assignment
        if consumer.assignment():
            return
    raise TimeoutError("Consumer never got partition assignment.")


@pytest.fixture(scope="session", autouse=True)
def ensure_topics_exist():
    """
    Garante que os tópicos existem.
    - Modo normal: cria se faltarem.
    - Modo strict (KAFKA_STRICT_TOPICS=1): falha se faltarem.
    """
    admin = _admin()
    md = admin.list_topics(timeout=5.0)
    existing = set(md.topics.keys())

    missing = [t for t in REQUIRED_TOPICS if t not in existing]

    if missing and STRICT_TOPICS:
        pytest.fail(
            f"Missing required Kafka topics: {missing}. "
            "Create them manually before running tests."
        )

    if missing:
        new_topics = [NewTopic(t, num_partitions=1, replication_factor=1) for t in missing]
        fs = admin.create_topics(new_topics)

        # Esperar criação
        for t, f in fs.items():
            f.result(timeout=10)

        # pequena espera para metadata atualizar
        time.sleep(1)


# ---- Tests ----

def test_kafka_broker_is_reachable():
    """
    Basic smoke test: broker responds to metadata request.
    """
    admin = _admin()
    md = admin.list_topics(timeout=5.0)
    assert md.brokers, f"No brokers found at {BOOTSTRAP_SERVERS}"


@pytest.mark.parametrize("topic", REQUIRED_TOPICS)
def test_roundtrip_produce_consume(topic):
    """
    Produce a unique JSON message to topic and verify we can consume it.
    """
    producer = _producer()
    group_id = f"test-{topic}-{uuid.uuid4()}"
    consumer = _consumer(group_id, topic)

    try:
        # Ensure consumer has joined group & has assignment
        _wait_for_assignment(consumer)

        corr_id = str(uuid.uuid4())
        payload = {
            "correlationId": corr_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "test": True,
            "topic": topic,
        }

        def delivery_report(err, msg):
            if err is not None:
                raise KafkaException(err)

        producer.produce(
            topic=topic,
            key=corr_id,
            value=json.dumps(payload).encode("utf-8"),
            on_delivery=delivery_report,
        )

        # <-- PATCH: flush mais robusto e com verificação
        remaining = producer.flush(10.0)
        assert remaining == 0, (
            f"Producer still has {remaining} message(s) buffered. "
            "Broker unreachable or leader not elected."
        )

        # <-- PATCH: deadline maior para evitar flakiness
        deadline = time.time() + 15.0
        received = None

        while time.time() < deadline:
            msg = consumer.poll(0.5)
            if msg is None:
                continue
            if msg.error():
                continue

            try:
                val = json.loads(msg.value().decode("utf-8"))
            except Exception:
                continue

            if val.get("correlationId") == corr_id:
                received = val
                break

        assert received is not None, f"Did not receive produced message on {topic}"
        assert received["topic"] == topic
        assert received["test"] is True

    finally:
        consumer.close()

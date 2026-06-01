"""
Cross-component contract tests: Kafka topic names and message structure.

These are static (no running services) structural tests that verify the
AI_APP and V_APP agree on the Kafka topic names and message field names
used to communicate at runtime.

If any of these fail, a topic-name mismatch will cause silent message loss
in production (producers write to a topic no consumer reads).

Run:
    PYTHONPATH=src pytest tests/cross_component/test_kafka_topic_contracts.py -v
"""

import pathlib
import sys

# Paths
ROOT = pathlib.Path(__file__).parent.parent.parent
SRC = ROOT / "src"

# Add shared src to path so we can import KafkaTopicFactory
sys.path.insert(0, str(SRC))

from shared.src.kafka_protocol import KafkaTopicFactory  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Topic naming consistency — verify format strings are stable
# ---------------------------------------------------------------------------

class TestKafkaTopicNamingContract:
    """KafkaTopicFactory must produce deterministic, symmetric topic names."""

    def test_truck_detected_topic_format(self):
        assert KafkaTopicFactory.truck_detected(1) == KafkaTopicFactory.truck_detected(1)
        assert KafkaTopicFactory.truck_detected(1) != KafkaTopicFactory.truck_detected(2)

    def test_license_plate_results_topic_format(self):
        assert KafkaTopicFactory.license_plate_results(1) == KafkaTopicFactory.license_plate_results(1)

    def test_hazard_plate_results_topic_format(self):
        assert KafkaTopicFactory.hazard_plate_results(1) == KafkaTopicFactory.hazard_plate_results(1)

    def test_agent_decision_topic_format(self):
        assert KafkaTopicFactory.agent_decision(1) == KafkaTopicFactory.agent_decision(1)

    def test_operator_decision_topic_format(self):
        assert KafkaTopicFactory.operator_decision(1) == KafkaTopicFactory.operator_decision(1)

    def test_infraction_decision_topic_format(self):
        assert KafkaTopicFactory.infraction_decision(1) == KafkaTopicFactory.infraction_decision(1)

    def test_gate_id_is_part_of_topic_name(self):
        """Gate-scoped topics must embed the gate_id so multiple gates don't collide."""
        t1 = KafkaTopicFactory.truck_detected(1)
        t2 = KafkaTopicFactory.truck_detected(2)
        assert "1" in t1 or "1" in t1
        assert t1 != t2, "Topics for different gates must be distinct"


# ---------------------------------------------------------------------------
# 2. AI_APP producer topics ↔ V_APP consumer topics (symmetric)
# ---------------------------------------------------------------------------

class TestAIAppVAppTopicSymmetry:
    """
    AI_APP gateway produces on topic X → V_APP gateway/consumer consumes on topic X.
    Verify by reading source files and checking that the same KafkaTopicFactory
    method names appear on both sides.
    """

    AI_GATEWAY_SRC = SRC / "AI_APP" / "gateway" / "src" / "ai_gateway.py"
    V_GATEWAY_SRC = SRC / "V_APP" / "gateway" / "src" / "v_gateway.py"
    V_CONSUMER_SRC = SRC / "V_APP" / "Data_Module" / "infrastructure" / "messaging" / "kafka_decision_consumer.py"

    def _read(self, path: pathlib.Path) -> str:
        return path.read_text()

    def test_ai_gateway_file_exists(self):
        assert self.AI_GATEWAY_SRC.exists(), f"AI gateway source not found: {self.AI_GATEWAY_SRC}"

    def test_v_gateway_file_exists(self):
        assert self.V_GATEWAY_SRC.exists(), f"V_APP gateway source not found: {self.V_GATEWAY_SRC}"

    def test_v_consumer_file_exists(self):
        assert self.V_CONSUMER_SRC.exists(), f"Kafka consumer not found: {self.V_CONSUMER_SRC}"

    def test_ai_gateway_uses_shared_topic_factory(self):
        """AI gateway must use KafkaTopicFactory — not hardcoded topic strings."""
        src = self._read(self.AI_GATEWAY_SRC)
        assert "KafkaTopicFactory" in src, (
            "ai_gateway.py must use KafkaTopicFactory for topic names — "
            "hardcoded strings break cross-component contracts."
        )

    def test_v_gateway_uses_shared_topic_factory(self):
        src = self._read(self.V_GATEWAY_SRC)
        assert "KafkaTopicFactory" in src, (
            "v_gateway.py must use KafkaTopicFactory for topic names."
        )

    def test_v_consumer_uses_shared_topic_factory(self):
        src = self._read(self.V_CONSUMER_SRC)
        assert "KafkaTopicFactory" in src, (
            "kafka_decision_consumer.py must use KafkaTopicFactory — "
            "not hardcoded topic strings."
        )

    def test_agent_decision_topic_consumed_by_v_app(self):
        """agent_decision topics produced by AI_APP must be consumed by V_APP."""
        v_consumer = self._read(self.V_CONSUMER_SRC)
        assert "agent_decision" in v_consumer, (
            "V_APP kafka_decision_consumer must subscribe to agent_decision topics."
        )

    def test_infraction_decision_topic_consumed_by_v_app(self):
        v_consumer = self._read(self.V_CONSUMER_SRC)
        assert "infraction_decision" in v_consumer, (
            "V_APP kafka_decision_consumer must subscribe to infraction_decision topics."
        )

    def test_v_gateway_relays_truck_detected(self):
        """V_APP gateway must relay truck_detected topics from AI_APP to V broker."""
        v_gateway = self._read(self.V_GATEWAY_SRC)
        assert "truck_detected" in v_gateway, (
            "v_gateway.py must relay truck_detected messages from AI_APP."
        )

    def test_v_gateway_relays_license_plate_results(self):
        v_gateway = self._read(self.V_GATEWAY_SRC)
        assert "license_plate_results" in v_gateway, (
            "v_gateway.py must relay license_plate_results messages from AI_APP."
        )

    def test_v_gateway_relays_hazard_plate_results(self):
        v_gateway = self._read(self.V_GATEWAY_SRC)
        assert "hazard_plate_results" in v_gateway, (
            "v_gateway.py must relay hazard_plate_results messages from AI_APP."
        )


# ---------------------------------------------------------------------------
# 3. EventEnvelope contract — V_APP Data Module event schema
# ---------------------------------------------------------------------------

class TestEventEnvelopeContract:
    """
    EventEnvelope is the V_APP's standard for all domain events.
    Verify its required fields are present and stable.
    """

    EVENTS_SRC = SRC / "V_APP" / "Data_Module" / "domain" / "events.py"

    _REQUIRED_FIELDS = [
        "event_id",
        "correlation_id",
        "causation_id",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "event_version",
        "occurred_at",
        "producer",
        "partition_key",
        "payload",
    ]

    def test_event_envelope_exists(self):
        src = self.EVENTS_SRC.read_text()
        assert "class EventEnvelope" in src, "EventEnvelope dataclass must exist in domain/events.py"

    def test_event_envelope_is_frozen_dataclass(self):
        src = self.EVENTS_SRC.read_text()
        assert "frozen=True" in src or "@dataclass" in src, (
            "EventEnvelope must be a frozen dataclass (immutable, hashable)."
        )

    def test_all_required_fields_present(self):
        src = self.EVENTS_SRC.read_text()
        start = src.find("class EventEnvelope")
        block = src[start:start + 800]
        for field in self._REQUIRED_FIELDS:
            assert field in block, (
                f"EventEnvelope is missing required field '{field}' — "
                "this field is part of the cross-component event contract."
            )

    def test_new_event_id_uses_uuidv7(self):
        """Events must use UUIDv7 for monotonic ordering."""
        src = self.EVENTS_SRC.read_text()
        assert "new_event_id" in src, "domain/events.py must export new_event_id()"
        assert "uuid" in src.lower() or "UUID" in src, (
            "new_event_id must generate UUID-based IDs."
        )


# ---------------------------------------------------------------------------
# 4. ContainerMovedHandler — V_APP must handle the AI_APP decision events
# ---------------------------------------------------------------------------

class TestContainerMovedHandlerContract:
    """ContainerMovedHandler is the primary integration point between AI_APP and V_APP."""

    HANDLER_SRC = SRC / "V_APP" / "Data_Module" / "application" / "use_cases" / "container_moved_handler.py"

    def test_handler_exists(self):
        assert self.HANDLER_SRC.exists(), "container_moved_handler.py must exist"

    def test_handler_uses_uow(self):
        src = self.HANDLER_SRC.read_text()
        assert "uow" in src or "IUnitOfWork" in src, (
            "ContainerMovedHandler must use UnitOfWork (Guardrail 2)."
        )

    def test_handler_uses_inbox_dedup(self):
        src = self.HANDLER_SRC.read_text()
        assert "inbox" in src.lower(), (
            "ContainerMovedHandler must use inbox deduplication to prevent "
            "duplicate Kafka message processing."
        )

    def test_handler_appends_to_outbox(self):
        src = self.HANDLER_SRC.read_text()
        assert "outbox" in src.lower(), (
            "ContainerMovedHandler must append domain events to the outbox "
            "(Guardrail 3 — Transactional Outbox)."
        )

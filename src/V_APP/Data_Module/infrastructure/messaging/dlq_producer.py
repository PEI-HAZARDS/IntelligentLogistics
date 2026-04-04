"""
Dead Letter Queue (DLQ) Producer — Guardrail 8.

Routes permanently-failed messages to ``<source-topic>.DLQ`` with full
error metadata so operators can inspect and replay them.

Failure classification:
  - **Permanent** (route to DLQ immediately):
    - JSON decode errors, schema/contract violations, unknown event types,
      domain-logic rejections (e.g. invalid state transitions).
  - **Transient** (retry with backoff — handled by the caller):
    - Postgres/Mongo/Redis timeouts, Kafka network blips.

DLQ envelope fields (per refactor plan §4.2):
  - original_topic, original_partition, original_offset
  - original_key, original_headers, original_payload
  - error_class, error_message, stacktrace_hash
  - service, attempt_count, first_seen_at, last_seen_at
"""

import json
import hashlib
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from shared.src.kafka_wrapper import KafkaProducerWrapper
from shared.src.kafka_protocol import KafkaTopicFactory

logger = logging.getLogger("dlq_producer")

# Exceptions that indicate a permanent failure (no point retrying)
PERMANENT_ERROR_TYPES = (
    json.JSONDecodeError,
    KeyError,
    TypeError,
    ValueError,
    AttributeError,
)


class DLQProducer:
    """Publishes failed messages to the corresponding DLQ topic."""

    SERVICE_NAME = "data-module-decision-consumer"

    def __init__(self, bootstrap_servers: str):
        self._producer = KafkaProducerWrapper(bootstrap_servers)

    def close(self):
        self._producer.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_to_dlq(
        self,
        *,
        source_topic: str,
        source_partition: int,
        source_offset: int,
        key: Optional[str],
        headers: Optional[dict],
        payload: Any,
        error: Exception,
        attempt_count: int = 1,
    ) -> None:
        """Wrap the original message with error metadata and publish to DLQ."""
        now = datetime.now(timezone.utc).isoformat()
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb)

        dlq_envelope = {
            "original_topic": source_topic,
            "original_partition": source_partition,
            "original_offset": source_offset,
            "original_key": key,
            "original_headers": headers,
            "original_payload": payload,
            "error_class": type(error).__name__,
            "error_message": str(error),
            "stacktrace_hash": hashlib.md5(tb_str.encode()).hexdigest(),
            "service": self.SERVICE_NAME,
            "attempt_count": attempt_count,
            "first_seen_at": now,
            "last_seen_at": now,
        }

        dlq_topic = KafkaTopicFactory.dlq(source_topic)

        try:
            self._producer.produce(
                topic=dlq_topic,
                data=dlq_envelope,
                key=key,
            )
            logger.warning(
                "Message sent to DLQ topic=%s key=%s error_class=%s: %s",
                dlq_topic, key, type(error).__name__, error,
            )
        except Exception as dlq_err:
            # Last resort — log so the message is not silently lost (Guardrail 5)
            logger.critical(
                "FAILED to publish to DLQ topic=%s for key=%s: %s  "
                "Original error: %s",
                dlq_topic, key, dlq_err, error,
            )

    @staticmethod
    def is_permanent_error(error: Exception) -> bool:
        """Classify whether an error is permanent (DLQ) or transient (retry)."""
        return isinstance(error, PERMANENT_ERROR_TYPES)

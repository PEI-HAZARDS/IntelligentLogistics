"""Base Decision Engine for the V_APP gate management system.

This module provides a foundational class for engines that need to correlate
license-plate (LP) and hazard-plate (HZ) detection events across multiple gates.
"""

import logging
import time
import json
from abc import ABC, abstractmethod
from typing import Optional

from prometheus_client import Histogram  # type: ignore
from pydantic_settings import BaseSettings  # type: ignore
from pydantic import Field, field_validator  # type: ignore

from shared.src.utils import load_from_file
from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import (
    HazardPlateResultsMessage, LicensePlateResultsMessage, Message, KafkaTopicFactory
)
from V_APP.shared.src.plate_matcher import PlateMatcher
from V_APP.shared.src.database_client import DatabaseClient


class BaseDecisionEngineConfig(BaseSettings):
    """Common configuration for all decision engines.
    
    Supports three gate ID arrays to allow engines to subscribe to different
    physical cameras (e.g., port entry vs. highway approach).
    """
    kafka_bootstrap: str = Field(default="10.255.32.70:9092")
    gate_ids: str = Field(default='["1"]')            # Master list
    decision_gate_ids: str = Field(default='["1"]')   # Inbound/Entry gates
    infraction_gate_ids: str = Field(default='["1"]') # Highway/Approach gates
    
    api_url: str = Field(default="http://localhost:8080/api/v1")
    time_tolerance_minutes: int = Field(default=30)
    max_levenshtein_distance: int = Field(default=2)
    expiration_time_hours: int = Field(default=24)
    un_numbers_file: str = Field(default="./data/un_numbers.txt")
    kemler_codes_file: str = Field(default="./data/kemler_codes.txt")

    @field_validator("gate_ids", "decision_gate_ids", "infraction_gate_ids", mode="before")
    @classmethod
    def _parse_gate_ids(cls, v: str) -> str:
        """Validate that the field is a valid JSON array string."""
        try:
            parsed = json.loads(v) if isinstance(v, str) else v
            if not isinstance(parsed, list) or len(parsed) == 0:
                raise ValueError("Gate ID fields must be non-empty JSON arrays")
        except json.JSONDecodeError:
            raise ValueError(f"Value is not valid JSON: {v}")
        return v

    def _to_list(self, json_str: str) -> list[str]:
        return [str(gid) for gid in json.loads(json_str)]

    @property
    def gate_id_list(self) -> list[str]:
        return self._to_list(self.gate_ids)

    @property
    def decision_gate_id_list(self) -> list[str]:
        return self._to_list(self.decision_gate_ids)

    @property
    def infraction_gate_id_list(self) -> list[str]:
        return self._to_list(self.infraction_gate_ids)


class BaseDecisionEngine(ABC):
    """Abstract base class for gate-agnostic decision engines."""

    def __init__(
        self,
        config: Optional[BaseDecisionEngineConfig] = None,
        kafka_producer: Optional[KafkaProducerWrapper] = None,
        kafka_consumer: Optional[KafkaConsumerWrapper] = None,
        plate_matcher: Optional[PlateMatcher] = None,
        database_client: Optional[DatabaseClient] = None,
    ) -> None:
        self.running = False
        self.config = config or BaseDecisionEngineConfig()
        self.logger = logging.getLogger(self.__class__.__name__)

        # Get the list of gates THIS specific engine should listen to
        active_gates = self._get_active_gate_ids()

        # Build per-gate topic maps
        self._lp_topics: dict[str, str] = {} # topic_name -> gate_id
        self._hz_topics: dict[str, str] = {} # topic_name -> gate_id
        consume_topics = []

        for gid in active_gates:
            lp_t = KafkaTopicFactory.license_plate_results(gid)
            hz_t = KafkaTopicFactory.hazard_plate_results(gid)
            self._lp_topics[lp_t] = gid
            self._hz_topics[hz_t] = gid
            consume_topics.extend([lp_t, hz_t])

        # Load lookup data
        self.un_numbers = self._load_lookup_file(self.config.un_numbers_file, "UN numbers")
        self.kemler_codes = self._load_lookup_file(self.config.kemler_codes_file, "Kemler codes")

        # In-memory buffers keyed by (gate_id, truck_id)
        self.lp_buffer: dict[tuple[str, str], LicensePlateResultsMessage] = {}
        self.hz_buffer: dict[tuple[str, str], HazardPlateResultsMessage] = {}
        self.expiration_time_seconds = self.config.expiration_time_hours * 3600

        # Dependencies
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(self.config.kafka_bootstrap)
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap, self._get_consumer_group(), consume_topics
        )
        self.plate_matcher = plate_matcher or PlateMatcher()
        
        # Default DatabaseClient uses the first active gate if available
        default_gid = active_gates[0] if active_gates else "1"
        self.database_client = database_client or DatabaseClient(self.config.api_url, default_gid)

        # Last Truck detected used to prevent duplicate processing where detection starts before last truck leaves the camera view
        self.last_truck_detected = dict[str, str]()  # gate_id -> license_plate

        self._init_base_metrics()
        self._init_specific_metrics()

    @abstractmethod
    def _get_active_gate_ids(self) -> list[str]:
        """Return the specific list of gate IDs this engine should monitor."""
        pass

    @abstractmethod
    def _get_consumer_group(self) -> str:
        pass

    @abstractmethod
    def _init_specific_metrics(self) -> None:
        pass

    @abstractmethod
    def _execute_logic(
        self,
        gate_id: str,
        truck_id: str,
        lp_msg: LicensePlateResultsMessage,
        hz_msg: HazardPlateResultsMessage,
    ) -> None:
        pass

    def _init_base_metrics(self) -> None:
        self.processing_latency = Histogram(
            f'{self.__class__.__name__.lower()}_latency_seconds',
            f'Time spent in {self.__class__.__name__} logic',
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
        )

    def start(self) -> None:
        self.running = True
        self.logger.info(f"Starting main loop for gates: {list(self._lp_topics.values())} …")
        try:
            while self.running:
                try:
                    self._clear_stale_buffer_entries()
                    topic, message_obj, truck_id = self.kafka_consumer.consume_typed_message(timeout=1.0)

                    if message_obj is None or topic is None or truck_id is None:
                        continue

                    gate_id = self._lp_topics.get(topic) or self._hz_topics.get(topic)
                    if not gate_id:
                        self.logger.warning(f"Received message from unknown topic: {topic}")
                        continue

                    self._log_incoming_message(message_obj, truck_id, gate_id)
                    self._store_in_buffer(gate_id, topic, truck_id, message_obj)
                    self._try_process_truck(gate_id, truck_id)
                except Exception:
                    self.logger.exception("Unexpected error in main loop")
        finally:
            self._cleanup_resources()

    def stop(self) -> None:
        self.running = False

    def _cleanup_resources(self) -> None:
        self.logger.info("Freeing resources…")
        self.kafka_consumer.close()
        self.kafka_producer.flush()
        self.kafka_producer.close()

    def _try_process_truck(self, gate_id: str, truck_id: str) -> None:
        key = (gate_id, truck_id)
        if key not in self.lp_buffer or key not in self.hz_buffer:
            return

        lp_msg = self.lp_buffer[key]
        hz_msg = self.hz_buffer[key]

        self._execute_logic(gate_id, truck_id, lp_msg, hz_msg)

        del self.lp_buffer[key] # aleterbativa self.lp_buffer.pop(key, None)
        del self.hz_buffer[key]
        self.logger.debug(f"Buffers cleaned for gate_id='{gate_id}', truck_id='{truck_id}'")

    def _store_in_buffer(self, gate_id: str, topic: str, truck_id: str, msg: Message) -> None:
        key = (gate_id, truck_id)
        if topic in self._lp_topics:
            if isinstance(msg, LicensePlateResultsMessage):
                self.lp_buffer[key] = msg
            else:
                self.logger.warning(f"Expected LP message on {topic} but got {type(msg).__name__}")
        elif topic in self._hz_topics:
            if isinstance(msg, HazardPlateResultsMessage):
                self.hz_buffer[key] = msg
            else:
                self.logger.warning(f"Expected HZ message on {topic} but got {type(msg).__name__}")

    def _clear_stale_buffer_entries(self) -> None:
        current_time = time.time()
        for buffer in [self.lp_buffer, self.hz_buffer]:
            for key in list(buffer.keys()):
                if current_time - buffer[key].timestamp > self.expiration_time_seconds:
                    del buffer[key]
                    self.logger.debug(f"Cleared stale entry for {key}")

    def _load_lookup_file(self, path: str, label: str) -> dict:
        try:
            data = load_from_file(path, separator="|")
            self.logger.info(f"Loaded {len(data)} {label}.")
            return data
        except Exception:
            self.logger.exception(f"Error loading {label} from {path}")
            return {}

    def _log_incoming_message(self, message_obj: Message, truck_id: str, gate_id: str) -> None:
        if isinstance(message_obj, LicensePlateResultsMessage):
            self.logger.debug(f"Received LP for truck {truck_id} (gate {gate_id}): {message_obj.license_plate}")
        elif isinstance(message_obj, HazardPlateResultsMessage):
            self.logger.debug(f"Received HZ for truck {truck_id} (gate {gate_id}): UN={message_obj.un}")

    def _get_un_description(self, un_number: str) -> str:
        return self.un_numbers.get(str(un_number), "Unknown UN Number")

    def _get_kemler_description(self, kemler_code: str) -> str:
        return self.kemler_codes.get(str(kemler_code), "Unknown Kemler Code")

    def _enrich_hazard_codes(self, un: str, kemler: str) -> tuple[str, str]:
        un_desc = self._get_un_description(un) if un else None
        kemler_desc = self._get_kemler_description(kemler) if kemler else None
        full_un = f"{un}: {un_desc}" if un_desc and un else un
        full_kemler = f"{kemler}: {kemler_desc}" if kemler_desc and kemler else kemler
        return full_un, full_kemler

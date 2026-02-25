import logging
import json
import time
import threading

from shared.src.kafka_wrapper import KafkaConsumerWrapper, KafkaProducerWrapper
from shared.src.kafka_protocol import (
    KafkaTopicFactory,
    KafkaMessageProto,
    deserialize_message,
)
from V_APP.v_brain.config import VBrainConfig
from V_APP.v_brain.src.scale_correlator import ScaleCorrelator


logger = logging.getLogger("VBrain")


class VBrain:
    """
    V_Brain — central orchestrator for the V_APP.

    Gate-agnostic: a single V_Brain instance handles ALL gates.
    It subscribes to per-gate topics for every configured gate_id
    and routes messages to the correct gate based on the topic name.

    Responsibilities:
        1. Listen for truck-detected → scale UP + register truck in correlator
        2. Listen for lp-results / hz-results → update correlator
        3. Listen for agent-decision / infraction-decision → trigger scale DOWN + reset AgentA
        4. Timeout tracking → force scale DOWN + reset for stale trucks

    Kafka Topics Consumed (per gate):
        - truck-detected-{GATE_ID}
        - lp-results-{GATE_ID}
        - hz-results-{GATE_ID}
        - agent-decision-{GATE_ID}
        - infraction-decision-{GATE_ID}

    Kafka Topics Produced:
        - scale-up            (global)
        - scale-down           (global)
        - reset-agentA-{GATE_ID}  (per gate)
    """

    # ── Topic-type constants ─────────────────────────────────────
    _TRUCK_DETECTED = "truck_detected"
    _LP_RESULTS = "lp_results"
    _HZ_RESULTS = "hz_results"
    _AGENT_DECISION = "agent_decision"
    _INFRACTION_DECISION = "infraction_decision"

    def __init__(
        self,
        config: VBrainConfig | None = None,
        kafka_producer: KafkaProducerWrapper | None = None,
        kafka_consumer: KafkaConsumerWrapper | None = None,
    ) -> None:
        self.config = config or VBrainConfig()
        self.running = False

        gate_ids = self.config.gate_id_list

        # ── Build per-gate topic map: topic_name → (gate_id, topic_type) ─
        self._topic_map: dict[str, tuple[str, str]] = {}
        self.consume_topics: list[str] = []
        
        self.scale_status: bool = False # False = scaled down, True = scaled up

        for gid in gate_ids:
            mappings = {
                KafkaTopicFactory.truck_detected(gid): self._TRUCK_DETECTED,
                KafkaTopicFactory.license_plate_results(gid): self._LP_RESULTS,
                KafkaTopicFactory.hazard_plate_results(gid): self._HZ_RESULTS,
                KafkaTopicFactory.agent_decision(gid): self._AGENT_DECISION,
                KafkaTopicFactory.infraction_decision(gid): self._INFRACTION_DECISION,
            }
            for topic_name, topic_type in mappings.items():
                self._topic_map[topic_name] = (gid, topic_type)
                self.consume_topics.append(topic_name)

        # ── Kafka wrappers ───────────────────────────────────────
        self.kafka_consumer = kafka_consumer or KafkaConsumerWrapper(
            self.config.kafka_bootstrap,
            "v-brain-group",
            self.consume_topics,
        )
        self.kafka_producer = kafka_producer or KafkaProducerWrapper(
            self.config.kafka_bootstrap,
        )

        # ── Internal state ───────────────────────────────────────
        self.correlator = ScaleCorrelator(
            timeout_seconds=self.config.correlator_timeout_seconds,
        )

    # ─── Main Loop ───────────────────────────────────────────────

    def start(self) -> None:
        """Start the V_Brain consumer loop (blocking)."""
        self.running = True
        logger.info(
            f"V_Brain starting | gates={self.config.gate_id_list} | "
            f"Consuming {len(self.consume_topics)} topics | "
            f"Timeout: {self.config.correlator_timeout_seconds}s"
        )
        self.kafka_consumer.clear_stale_messages()

        # Background thread for timeout checks
        timeout_thread = threading.Thread(
            target=self._timeout_loop,
            name="v-brain-timeout",
            daemon=True,
        )
        timeout_thread.start()

        try:
            while self.running:
                msg = self.kafka_consumer.consume_message(timeout=1.0)
                if msg is None:
                    continue

                topic = msg.topic()
                truck_id = self.kafka_consumer.extract_truck_id_from_headers(msg.headers())

                # Parse JSON
                try:
                    data = json.loads(msg.value())
                except Exception as e:
                    logger.warning(f"Invalid JSON from topic '{topic}': {e}")
                    continue

                # Deserialize into typed message
                try:
                    typed_message = deserialize_message(data)
                except ValueError as e:
                    logger.warning(f"Could not deserialize from '{topic}': {e}")
                    continue

                # ── Route by topic ───────────────────────────────
                self._handle_message(topic, typed_message, truck_id)

        except KeyboardInterrupt:
            logger.info("V_Brain stopped by user")
        except Exception as e:
            logger.exception(f"V_Brain fatal error: {e}")
        finally:
            self.running = False
            self.kafka_consumer.close()
            self.kafka_producer.close()
            logger.info("V_Brain shut down")

    def stop(self) -> None:
        self.running = False

    # ─── Message Handling ────────────────────────────────────────

    def _handle_message(self, topic: str, message, truck_id: str | None) -> None:
        """Route a consumed message to the appropriate handler."""

        # procura no mapa: "truck-detected-1" → ("1", "truck_detected")
        lookup = self._topic_map.get(topic)
        if not lookup:
            logger.debug(f"Unhandled topic: {topic}")
            return

        # gate_id="1", topic_type="truck_detected"
        gate_id, topic_type = lookup

        if   topic_type == self._TRUCK_DETECTED:     self._on_truck_detected(truck_id, gate_id)
        elif topic_type == self._LP_RESULTS:         self._on_lp_results(truck_id, gate_id)
        elif topic_type == self._HZ_RESULTS:         self._on_hz_results(truck_id, gate_id)
        elif topic_type == self._AGENT_DECISION:     self._on_agent_decision(truck_id, gate_id)
        elif topic_type == self._INFRACTION_DECISION:self._on_infraction_decision(truck_id, gate_id)

    # ── Handlers ─────────────────────────────────────────────────

    def _on_truck_detected(self, truck_id: str | None, gate_id: str) -> None:
        """
        Truck detected by AgentA.
        → Register in correlator (with gate_id)
        → Scale UP (switch frontend to high-quality stream)
        """
        if not truck_id:
            logger.warning("truck-detected without truck_id, ignored")
            return

        logger.info(f"Truck detected: {truck_id} (gate {gate_id})")
        self.correlator.truck_detected(truck_id, gate_id)
        self._scale_up_try(truck_id, gate_id, reason="truck_detected")

    def _on_lp_results(self, truck_id: str | None, gate_id: str) -> None:
        """
        License plate results received.
        → Update correlator → if both LP+HZ done, scale down + reset
        """
        if not truck_id:
            return

        # Verifica se ja tem ambos LP e HZ, se sim, retorna ready=True else False
        ready = self.correlator.lp_received(truck_id)
        logger.info(f"LP results for {truck_id} (gate {gate_id}) | complete={ready}")

        # Dá scale-down se ja tiver o hz_results
        # Não da automaticamente pois precisa de checkar se mais algum truck ja não esta a precisar desse slice na rede
        if ready:
            self._scale_down_try(truck_id, gate_id, reason="results_complete")

    def _on_hz_results(self, truck_id: str | None, gate_id: str) -> None:
        """
        Hazard plate results received.
        → Update correlator → if both LP+HZ done, scale down + reset
        """
        if not truck_id:
            return

        # Verifica se ja tem ambos LP e HZ, se sim, retorna ready=True else False
        ready = self.correlator.hz_received(truck_id)
        logger.info(f"HZ results for {truck_id} (gate {gate_id}) | complete={ready}")

        # Da scale-down se ja tiver o lp_results
        # Não da automaticamente pois precisa de checkar se mais algum truck 
        # ja não esta a precisar desse slice na rede
        if ready:
            self._scale_down_try(truck_id, gate_id, reason="results_complete")


    def _on_agent_decision(self, truck_id: str | None, gate_id: str) -> None:
        """
        Decision engine produced a decision for this truck.
        → Scale down + reset AgentA (decision is final)
        """
        if not truck_id:
            return

        logger.info(f"Agent decision received for {truck_id} (gate {gate_id})")

        # Ve se esse truck id ja foi detetado em alguma instancia se sim, marca como decision_received
        if self.correlator.is_tracked(truck_id):
            self.correlator.decision_received(truck_id)

            # Quando deteta um tipo de decisão pode dar reset
            self._reset_agent_a(gate_id, reason="agent_decision")
            self.correlator.remove(truck_id)

        else:
            logger.warning(f"Decision for untracked truck {truck_id}, sending reset anyway")



    def _on_infraction_decision(self, truck_id: str | None, gate_id: str) -> None:
        """
        Infraction decision received — an infraction was detected.
        → Guarantee scale down + reset AgentA regardless of correlator state.
        """
        if not truck_id:
            return

        logger.info(f"Infraction decision received for {truck_id} (gate {gate_id})")

        # Ve se esse truck-id ja foi detetado em alguma instancia se sim, marca como decision_received
        if self.correlator.is_tracked(truck_id):
            self.correlator.decision_received(truck_id)

            # Quando deteta um tipo de decisão pode dar reset
            self._reset_agent_a(gate_id, reason="infraction_decision")
            self.correlator.remove(truck_id)

        else:
            logger.warning(f"Infraction for untracked truck {truck_id}, sending reset anyway")


    # ─── Scale Actions ───────────────────────────────────────────


    def _scale_up_try(self, truck_id: str, gate_id: str, reason: str = "unknown") -> None:
        """Publish scale-up event to V_Broker → API_Gateway → Frontend."""

        # Mandar a mensagem serve so para mudar qual stream é servida para o frontend, 
        # não tem impacto no estado do slice na rede, por isso, mesmo que esteja em scale-up, 
        # pode mandar a mensagem para garantir que o frontend muda para a stream de baixa qualidade

        msg = KafkaMessageProto.scale(gate_id=gate_id, mode="scale_up")
        self.kafka_producer.produce(
            topic=KafkaTopicFactory.scale_up(),
            data=msg.to_dict(),
        )
        logger.info(f"Scale UP published for gate {gate_id}")

        # Verifica se já não esta em scale-up, se não estiver, da o scale-up, se já estiver, não faz nada 
        # (evita dar scale-up desnecessário caso já tenha um truck a usar o slice dedicado)
        if not self.scale_status:
            logger.info(f"Scaling UP gate {gate_id} (reason={reason})")
            self.scale_status = True
            # TODO:
            # Chamada a API do 

            return
        
        logger.info(f"Network scale already {'UP' if self.scale_status else 'DOWN'} for gate {gate_id}, no action taken (reason={reason})")
        
        



    def _scale_down_try(self, truck_id: str, gate_id: str, reason: str = "unknown") -> None:
        """Publish scale-down event to V_Broker → API_Gateway → Frontend."""

        # Mandar a mensagem serve so para mudar qual stream é servida para o frontend, 
        # não tem impacto no estado do slice na rede, por isso, mesmo que esteja em scale-down, 
        # pode mandar a mensagem para garantir que o frontend muda para a stream de baixa qualidade
        msg = KafkaMessageProto.scale(gate_id=gate_id, mode="scale_down")
        self.kafka_producer.produce(
            topic=KafkaTopicFactory.scale_down(),
            data=msg.to_dict(),
        )
        logger.info(f"Scale DOWN published for gate {gate_id}")


        # Evita dar scale-down se ainda tiver algum truck a precisar do slice dedicado, ou seja, 
        # se tiver algum truck que ainda não recebeu decisão (agent-decision ou infraction-decision)

        for truckId, state in self.correlator._state.items():
            if state["decided"] is False:
                logger.info(f"Truck {truckId} still needs scale-up, skipping scale-down for gate {gate_id}")
                return 

        # TODO:
        # Chamada a API do Tiago
        self.scale_status = False
        logger.info(f"Scaling DOWN gate {gate_id} (reason={reason})")



    def _reset_agent_a(self, gate_id: str, reason: str = "unknown") -> None:
        """Publish reset-agentA to V_Broker → V_Gateway → IA_Gateway → AgentA."""
        msg = KafkaMessageProto.reset_agent_a(reason=reason)
        self.kafka_producer.produce(
            topic=KafkaTopicFactory.reset_agent_a(gate_id),
            data=msg.to_dict(),
        )
        logger.info(f"Reset AgentA published (reason={reason}) for gate {gate_id}")

    
    def _get_scale_status(self, gate_id: str) -> bool:
        """Returns the current scale status for the gate (True=UP, False=DOWN)."""
        return self.scale_status

    

    # ─── Timeout Loop ────────────────────────────────────────────

    def _timeout_loop(self) -> None:
        """
        Background thread that periodically checks for timed-out trucks.
        Runs every 5 seconds.
        """
        while self.running:
            time.sleep(5)
            timed_out = self.correlator.check_timeouts()
            for truck_id in timed_out:
                gate_id = self.correlator.get_gate_id(truck_id)
                if gate_id:
                    logger.warning(f"Timeout for {truck_id} (gate {gate_id}) — forcing scale down + reset")
                    self._reset_agent_a(gate_id, reason="timeout")
                    self.correlator.remove(truck_id)
                    self._scale_down_try(truck_id, gate_id, reason="timeout")
                else:
                    logger.error(f"Timeout for {truck_id} but no gate_id found, skipping")
                    self.correlator.remove(truck_id)

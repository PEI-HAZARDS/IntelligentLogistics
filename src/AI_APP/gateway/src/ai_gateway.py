from shared.src.base_gateway import BaseGateway
from shared.src.kafka_protocol import Message, KafkaTopicFactory


class AIGateway(BaseGateway):
    def get_topics_consume(self) -> list[str]:
        topics = []
        for gate_id in self.config.gate_ids:
            topics.append(KafkaTopicFactory.truck_detected(gate_id))
            topics.append(KafkaTopicFactory.license_plate_results(gate_id))
            topics.append(KafkaTopicFactory.hazard_plate_results(gate_id))
        return topics

    def get_gateway_name(self) -> str:
        return "AI_Gateway"

    def get_topics_produce(self) -> dict[str, str]:
        topics = {}
        for gate_id in self.config.gate_ids:
            # Reset AgentA relay: V_Brain → V_Gateway → IA_Gateway → AI_Broker (→ AgentA)
            topics[KafkaTopicFactory.reset_agent_a(gate_id)] = KafkaTopicFactory.reset_agent_a(gate_id)

        # Fallback by message_type (single-gate deployments only)
        if len(self.config.gate_ids) == 1:
            gate_id = self.config.gate_ids[0]
            topics["reset_agent_a"] = KafkaTopicFactory.reset_agent_a(gate_id)
        return topics

    def get_receivers(self) -> list[str]:
        return self.config.receivers

    def process_message(self, message: Message) -> Message:
        # For now, we just log the message and return it unchanged.
        self.logger.info(f"Processing \"{message.MESSAGE_TYPE}\" message before sending...")
        return message
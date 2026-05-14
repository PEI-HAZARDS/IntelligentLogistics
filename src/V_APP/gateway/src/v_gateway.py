from shared.src.base_gateway import BaseGateway
from shared.src.kafka_protocol import Message, KafkaTopicFactory


class VGateway(BaseGateway):
    def get_topics_consume(self) -> list[str]:
        topics = []
        for gate_id in self.config.gate_ids:
            # Consume reset-agentA from V_Broker (produced by V_Brain)
            # → BaseGateway forwards via HTTP to AI_Gateway → AI_Broker → AgentA
            topics.append(KafkaTopicFactory.reset_agent_a(gate_id))
        return topics

    def get_gateway_name(self) -> str:
        return "V_Gateway"

    def get_topics_produce(self) -> dict[str, str]:
        # Map source topic (AI broker) → destination topic (V broker).
        # Keyed on the full topic name so routing is unambiguous across multiple gates.
        topics = {}
        for gate_id in self.config.gate_ids:
            topics[KafkaTopicFactory.truck_detected(gate_id)] = KafkaTopicFactory.truck_detected(gate_id)
            topics[KafkaTopicFactory.license_plate_results(gate_id)] = KafkaTopicFactory.license_plate_results(gate_id)
            topics[KafkaTopicFactory.hazard_plate_results(gate_id)] = KafkaTopicFactory.hazard_plate_results(gate_id)
        return topics

    def get_receivers(self) -> list[str]:
        return self.config.receivers

    def process_message(self, message: Message) -> Message:
        # For now, we just log the message and return it unchanged.
        self.logger.info(f"Processing \"{message.MESSAGE_TYPE}\" message before sending...")
        return message
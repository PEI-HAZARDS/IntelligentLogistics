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
            # Primary key: X-Source-Topic header value sent by VGateway.
            # Unambiguous even with multiple gates.
            topics[KafkaTopicFactory.agent_decision(gate_id)] = KafkaTopicFactory.agent_decision(gate_id)
        # Fallback key: message_type field, used when X-Source-Topic header is absent.
        # Only safe for single-gate deployments; for multi-gate rely on X-Source-Topic.
        if len(self.config.gate_ids) == 1:
            topics["decision_results"] = KafkaTopicFactory.agent_decision(self.config.gate_ids[0])
        return topics

    def get_receivers(self) -> list[str]:
        return self.config.receivers

    def process_message(self, message: Message) -> Message:
        # For now, we just log the message and return it unchanged.
        self.logger.info(f"Processing \"{message.MESSAGE_TYPE}\" message before sending...")
        return message
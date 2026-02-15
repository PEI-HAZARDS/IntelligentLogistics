from shared.src.base_gateway import BaseGateway
from shared.src.kafka_protocol import Message


class AI_Gateway(BaseGateway):
    def get_topics_consume(self) -> list[str]:
        return [f"hz-results-{self.gate_id}", f"lp-results-{self.gate_id}"]

    def get_gateway_name(self) -> str:
        return "AI_Gateway"

    def get_topics_produce(self) -> dict[str, str]:
        return {
            "decision_results": f"decision-results-{self.gate_id}"
        }

    def get_recievers(self) -> list[str]:
        return ["http://10.255.32.70:8003"]  # V_APP Gateway base URL

    def process_message(self, message: Message) -> Message:
        # For now, we just log the message and return it unchanged.
        self.logger.info(f"Processing message: {message}")
        return message
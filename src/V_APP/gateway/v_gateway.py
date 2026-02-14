from shared.src.base_gateway import BaseGateway
from shared.src.kafka_protocol import Message


class V_Gateway(BaseGateway):
    def get_topics_consume(self) -> list[str]:
        return [f"decision-results-{self.gate_id}"]

    def get_gateway_name(self) -> str:
        return "V_Gateway"

    def get_topics_produce(self) -> dict[str, str]:
        return {
            "hazard_plate_results": f"hz-results-{self.gate_id}",
            "license_plate_results": f"lp-results-{self.gate_id}",
        }

    def get_recievers(self) -> list[str]:
        return ["http://10.255.32.110:8003"]  # AI_APP Gateway base URL

    def process_message(self, message: Message) -> Message:
        # For now, we just log the message and return it unchanged.
        self.logger.info(f"Processing message: {message}")
        return message
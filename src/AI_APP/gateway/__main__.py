from AI_APP.gateway.ai_gateway import AIGateway
from shared.src.base_gateway import BaseGatewayConfig


def main():
    config = BaseGatewayConfig()
    gateway = AIGateway(config)
    gateway.start()

if __name__ == "__main__":
    main()

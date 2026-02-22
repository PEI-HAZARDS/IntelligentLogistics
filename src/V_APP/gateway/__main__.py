from V_APP.gateway.src.v_gateway import VGateway
from shared.src.base_gateway import BaseGatewayConfig


def main():
    config = BaseGatewayConfig()
    gateway = VGateway(config)
    gateway.start()


if __name__ == "__main__":
    main()

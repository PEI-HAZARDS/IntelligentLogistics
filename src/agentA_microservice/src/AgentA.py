# AgentA.py — versão Kafka (KRaft/ZooKeeper-agnostic)
from shared_utils.RTSPstream import *
from agentA_microservice.src.YOLO_Truck import *
import os
import time
import uuid
from confluent_kafka import Producer # type: ignore
import json

RTSP_STREAM_LOW = "rtsp://10.255.35.86:554/stream2"
MESSAGE_INTERVAL = 30  # seconds
KAFKA_TOPIC = "truck-detected"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
logger = logging.getLogger("AgentA")


def _delivery_callback(err, msg):
    if err:
        logger.error(f"[AgentA/Kafka] Error sending: {err}")
    else:
        try:
            v = msg.value().decode() if isinstance(msg.value(), (bytes, bytearray)) else msg.value()
        except Exception:
            v = str(msg.value())
        logger.info(f"[AgentA/Kafka] Message delivered in {msg.topic()}@{msg.partition()}#{msg.offset()} value={v}")


class AgentA:
    """
    Agent A:
    - Monitora continuamente um RTSP de baixa qualidade.
    - Deteta camiões com YOLO.
    - Publica eventos 'truck-detected' no Kafka (tópico {KAFKA_TOPIC}).
    """

    def __init__(self, kafka_bootstrap: str | None = None):
        self.yolo = YOLO_Truck()
        self.running = True
        self.last_message_time = 0

        # Kafka Producer
        bootstrap = kafka_bootstrap or KAFKA_BOOTSTRAP
        logger.info(f"[AgentA/Kafka] Connecting to kafka via '{bootstrap}' …")
        self.producer = Producer({
            "bootstrap.servers": bootstrap,
            "log_level": 1, # only errors
            # podes acrescentar: "enable.idempotence": True, "acks": "all"
        })



    def _publish_truck_detected(self, max_conf: float, num_boxes: int):
        """
        Publica o evento 'truck-detected' no Kafka.
        - Usa correlationId (header) novo por evento.
        - Gera um pseudo 'truckId' (é um ID de deteção; o AgentB ligará isto à leitura de matrícula).
        """
        truck_id = "TRK" + str(uuid.uuid4())[:8]

        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "confidence": float(max_conf),
            "detections": int(num_boxes),
        }

        logger.info(f"[AgentA] Publishing 'truck-detected' (truckId={truck_id}, "
                         f"detections={num_boxes}, max_conf={max_conf:.2f}) …")
        self.producer.produce(
            topic=KAFKA_TOPIC,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id},
            callback=_delivery_callback
        )
        # drena callbacks sem bloquear muito; flush completo é feito no stop()
        self.producer.poll(0)



    def _loop(self):
        logger.info("[AgentA] Starting Agent A main loop…")

        cap = None
        try:
            logger.info(f"[AgentA] Connecting to RTSP stream: {RTSP_STREAM_LOW}")
            cap = RTSPStream(RTSP_STREAM_LOW)
        except Exception as e:
            logger.exception(f"[AgentA] Failed to initialize RTSP stream: {e}")
            return

        while self.running:
            try:
                frame = cap.read()
                if frame is None:
                    logger.debug("[AgentA] No frame available from RTSP stream yet.")
                    time.sleep(0.2)
                    continue

                logger.debug("[AgentA] Frame captured, running truck detection…")
                results = self.yolo.detect(frame)

                if results is None:
                    logger.warning("[AgentA] YOLO model returned no results (None).")
                    continue

                if self.yolo.truck_found(results):
                    now = time.time()
                    elapsed = now - self.last_message_time

                    if elapsed < MESSAGE_INTERVAL:
                        logger.info(
                            f"[AgentA] Truck detected, but waiting "
                            f"{MESSAGE_INTERVAL - elapsed:.1f}s before next message."
                        )
                        continue

                    # extrair confidências e publicar
                    try:
                        boxes = self.yolo.get_boxes(results)  # [x1,y1,x2,y2,conf]
                        num = len(boxes)
                        max_conf = max((b[4] for b in boxes), default=0.0)
                        self.last_message_time = now
                        self._publish_truck_detected(max_conf=max_conf, num_boxes=num)
                    except Exception as e:
                        logger.exception(f"[AgentA] Error preparing Kafka event: {e}")

                else:
                    logger.debug("[AgentA] No truck detected in this frame.")

            except Exception as e:
                logger.exception(f"[AgentA] Exception during detection loop: {e}")
                time.sleep(1)  # Avoid busy looping on errors

        # Cleanup once stopped
        if cap:
            try:
                cap.release()
                logger.debug("[AgentA] RTSP stream released.")
            except Exception as e:
                logger.exception(f"[AgentA] Error releasing RTSP stream: {e}")

        # garante envio de mensagens pendentes
        try:
            logger.info("[AgentA/Kafka] Flushing producer…")
            self.producer.flush(10)  # até 10s
        except Exception as e:
            logger.exception(f"[AgentA/Kafka] Error on flush: {e}")



    def stop(self):
        """Gracefully stop Agent A."""
        logger.info("[AgentA] Stopping Agent A…")
        self.running = False
        logger.info("[AgentA] Agent stopped successfully.")

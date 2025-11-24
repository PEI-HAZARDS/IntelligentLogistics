# AgentB.py — versão Kafka
from shared_utils import RTSPstream
from shared_utils.RTSPstream import *
from agentB_microservice.src.YOLO_License_Plate import *
from agentB_microservice.src.OCR import *

import os
import time
import cv2 # type: ignore
import json
import uuid
from queue import Queue, Empty
from confluent_kafka import Producer, Consumer, KafkaException # type: ignore
from shared_utils.RTSPstream import *

# URL do stream HIGH (4K) via Nginx RTMP
# Antes: rtsp://10.255.35.86:554/stream1
# Agora: rtmp://nginx-rtmp/streams_high/gate01
RTSP_STREAM_HIGH = os.getenv("RTSP_STREAM_HIGH", "rtmp://nginx-rtmp/streams_high/gate01")
CROPS_PATH = "agentB_microservice/data/lp_crops"
os.makedirs(CROPS_PATH, exist_ok=True)


# Configurações Kafka
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
TOPIC_CONSUME = "truck-detected"
TOPIC_PRODUCE = "license-plate-detected"
logger = logging.getLogger("AgentB")


class AgentB:
    """
    Agent B:
    - Consome 'truck-detected' do Kafka.
    - Ao receber, captura frames do RTSP (alta qualidade).
    - Deteta matrícula com YOLO e extrai texto com OCR.
    - Publica 'license-plate-detected' no Kafka, propagando correlationId.
    """

    def __init__(self, kafka_bootstrap: str | None = None):
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()
        self.running = True
        self.frames_queue = Queue()
        
        # NÃO conecta ao stream no __init__
        # Conecta on-demand quando recebe evento do Kafka
        self.stream = None

        bootstrap = kafka_bootstrap or KAFKA_BOOTSTRAP
        logger.info(f"[AgentB/Kafka] bootstrap: {bootstrap}")

        # Kafka Consumer
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap,
            "group.id": "agentB-group",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,        # simples para começar; mudar p/ manual se precisares de controle fino
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })
        self.consumer.subscribe([TOPIC_CONSUME])

        # Kafka Producer
        self.producer = Producer({
            "bootstrap.servers": bootstrap,
            # "enable.idempotence": True, "acks": "all"  # liga em produção se precisares de garantias fortes
        })


    def _get_frames(self, num_frames=1):
        """Captura alguns frames do RTMP/RTSP."""
        # Conectar ao stream se não estiver conectado
        if self.stream is None:
            logger.info(f"[AgentB] Connecting to RTMP stream (via Nginx): {RTSP_STREAM_HIGH}")
            try:
                self.stream = RTSPStream(RTSP_STREAM_HIGH)
            except Exception as e:
                logger.exception(f"[AgentB] Failed to connect to stream: {e}")
                return
        
        logger.info(f"[AgentB] reading {num_frames} frame(s) from RTMP…")
        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    logger.debug(f"[AgentB] Captured {captured}/{num_frames}.")
                else:
                    logger.debug("[AgentB] No frame yet, trying again…")
                    time.sleep(0.1)
            except Exception as e:
                logger.exception(f"[AgentB] Error when capturing frame {e}")
                time.sleep(0.2)


    def process_license_plate_detection(self):
        """Pipeline principal para detetar e extrair texto da matrícula."""

        logger.info("[AgentB] Starting license plate pipeline detection process…")
        self._get_frames(1)

        if self.frames_queue.empty():
            logger.warning("[AgentB] No frame captured from RTSP.")
            return None, None, None  # (texto, conf, crop_img)

        lp_results = []
        lp_crop = None

        while self.running and not self.frames_queue.empty():
            try:
                frame = self.frames_queue.get_nowait()
                logger.debug("[AgentB] Frame obtained from queue.")
            except Empty:
                logger.warning("[AgentB] Frames queue is empty.")
                time.sleep(0.05)
                continue

            try:
                logger.info("[AgentB] YOLO (LP) running…")
                results = self.yolo.detect(frame)

                if not results:
                    logger.debug("[AgentB] YOLO did not return a result for this frame.")
                    continue

                if self.yolo.found_license_plate(results):
                    boxes = self.yolo.get_boxes(results)
                    logger.info(f"[AgentB] {len(boxes)} license plates detected.")

                    for i, box in enumerate(boxes, start=1):
                        x1, y1, x2, y2, conf = map(float, box)
                        if conf < 0.5:
                            logger.debug(f"[AgentB] Ignored low confidence result (conf={conf:.2f}).")
                            continue

                        crop = frame[int(y1):int(y2), int(x1):int(x2)]
                        crop_path = f"{CROPS_PATH}/lp_crop_{int(time.time())}_{i}.jpg"
                        try:
                            cv2.imwrite(crop_path, crop)
                            logger.debug(f"[AgentB] Crop saved: {crop_path}")
                        except Exception as e:
                            logger.warning(f"[AgentB] Failed saving crop: {e}")

                        logger.info("[AgentB] OCR extracting text…")
                        try:
                            text, ocr_conf = self.ocr._extract_text(crop)
                            if text and ocr_conf > 0.0:  # Only append valid results
                                lp_results.append((text, float(ocr_conf)))
                                lp_crop = crop
                                logger.info(f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")
                            else:
                                logger.debug(f"[AgentB] OCR returned no text for crop {i}")
                        except Exception as e:
                            logger.exception(f"[AgentB] OCR failure: {e}")
                else:
                    logger.info("[AgentB] No license plate detected for this frame.")

            except Exception as e:
                logger.exception(f"[AgentB] Error on detection loop: {e}")

        if not lp_results:
            logger.warning("[AgentB] No valid license plates on any frame.")
            return None, None, None

        try:
            final_text, conf = self.consensus_Alg(lp_results)
            logger.info(f"[AgentB] Final license plate: '{final_text}' (conf={conf:.2f})")
            return final_text, conf, lp_crop
        except Exception as e:
            logger.exception(f"[AgentB] Error calculating results: {e}")
            return None, None, None

    def consensus_Alg(self, results):
        """Combina/seleciona o melhor resultado do OCR."""
        # TODO: implementar algoritmo de consenso mais robusto
        logger.debug("[AgentB] Obtaining final result.")
        return results[-1][0], results[-1][1]



    def _publish_lp_detected(self, timestamp, truck_id, plate_text, plate_conf):
        """Publica evento 'license-plate-detected' com propagação do correlationId."""

        # Payload com o conteudo da mensagem
        payload = {
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "licensePlate": plate_text,
            "confidence": float(plate_conf if plate_conf is not None else 0.0)
        }
        logger.info(f"[AgentB] Publishing '{TOPIC_PRODUCE}' (truckId={truck_id}, plate={plate_text}) …")

        # Publica o topico de deteção de matrícula
        self.producer.produce(
            topic=TOPIC_PRODUCE,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id or str(uuid.uuid4())}
        )
        self.producer.poll(0)



    def _loop(self):
        logger.info(f"[AgentB] Main loop starting… (topic in='{TOPIC_CONSUME}')")

        try:
            while self.running:
                msg = self.consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    # podes registar msg.error() se quiseres
                    continue

                # payload de entrada
                try:
                    data = json.loads(msg.value())
                except json.JSONDecodeError:
                    logger.warning("[AgentB] Invalid message (JSON). Ignored.")
                    continue

                # correlationId (propagar se existir)
                truck_id = None
                for k, v in (msg.headers() or []):
                    if k == "truckId" and v is not None:
                        truck_id = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        break
                if truck_id is None:
                    truck_id = str(uuid.uuid4())

                # dados de entrada (truckId, timestamp)
                in_timestamp = data.get("timestamp")
                
                logger.info("[AgentB] Recieved 'truck-detected'. Starting LP pipeline…")
                plate_text, plate_conf, _lp_img = self.process_license_plate_detection()

                if not plate_text:
                    logger.warning("[AgentB] No final text results — not publishing.")
                    # dependendo do teu desenho, poderias publicar mesmo assim com conf=0.0
                    continue
                
                # Publica a mensagem de matrícula detetada
                self._publish_lp_detected(
                    timestamp=in_timestamp,
                    truck_id=truck_id,
                    plate_text=plate_text,
                    plate_conf=plate_conf
                )
            

        except KeyboardInterrupt:
            logger.info("[AgentB] Interrupted by user.")
        except KafkaException as e:
            logger.exception(f"[AgentB/Kafka] Kafka error: {e}")
        except Exception as e:
            logger.exception(f"[AgentB] Unexpected error: {e}")
        finally:
            logger.info("[AgentB] Freeing resources…")
            try:
                if self.stream is not None:
                    self.stream.release()
                    logger.debug("[AgentB] RTMP stream released.")
            except Exception as e:
                logger.exception(f"[AgentB] Error releasing RTMP stream: {e}")
            try:
                self.producer.flush(5)
            except Exception:
                pass
            try:
                self.consumer.close()
            except Exception:
                pass
        


    def stop(self):
        """Para parar o agente de forma limpa."""

        logger.info("[AgentB] Stopping agent and freeing resources…")
        self.running = False
        logger.info("[AgentB] Stopped successfuly.")

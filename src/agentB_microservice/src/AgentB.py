# AgentB.py — versão Kafka
from shared_utils.Logger import *
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

RTSP_STREAM_HIGH = "rtsp://10.255.35.86:554/stream1"
CROPS_PATH = "agentB_microservice/data/lp_crops"
os.makedirs(CROPS_PATH, exist_ok=True)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_IN = "truck-detected"
TOPIC_OUT = "license-plate-detected"


class AgentB:
    """
    Agent B:
    - Consome 'truck-detected' do Kafka.
    - Ao receber, captura frames do RTSP (alta qualidade).
    - Deteta matrícula com YOLO e extrai texto com OCR.
    - Publica 'license-plate-detected' no Kafka, propagando correlationId.
    """

    def __init__(self, kafka_bootstrap: str | None = None):
        self.logger = GlobalLogger().get_logger()
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()
        self.running = True
        self.frames_queue = Queue()
        self.stream = RTSPStream(RTSP_STREAM_HIGH)

        bootstrap = kafka_bootstrap or KAFKA_BOOTSTRAP
        self.logger.info(f"[AgentB/Kafka] bootstrap: {bootstrap}")

        # Kafka Consumer
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap,
            "group.id": "agentB-group",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,        # simples para começar; muda p/ manual se precisares de controle fino
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })
        self.consumer.subscribe([TOPIC_IN])

        # Kafka Producer
        self.producer = Producer({
            "bootstrap.servers": bootstrap,
            # "enable.idempotence": True, "acks": "all"  # liga em produção se precisares de garantias fortes
        })

    def _get_frames(self, num_frames=1):
        """Captura alguns frames do RTSP."""
        self.logger.info(f"[AgentB] Lendo {num_frames} frame(s) do RTSP…")
        captured = 0
        while captured < num_frames and self.running:
            try:
                frame = self.stream.read()
                if frame is not None:
                    self.frames_queue.put(frame)
                    captured += 1
                    self.logger.debug(f"[AgentB] Capturado frame {captured}/{num_frames}.")
                else:
                    self.logger.debug("[AgentB] Sem frame ainda, tentando novamente…")
                    time.sleep(0.1)
            except Exception as e:
                self.logger.exception(f"[AgentB] Erro a capturar frame: {e}")
                time.sleep(0.2)

    def process_license_plate_detection(self):
        """Pipeline principal para detetar e extrair texto da matrícula."""
        self.logger.info("[AgentB] Início do pipeline de deteção de matrícula…")
        self._get_frames(1)

        if self.frames_queue.empty():
            self.logger.warning("[AgentB] Nenhum frame capturado do RTSP.")
            return None, None, None  # (texto, conf, crop_img)

        lp_results = []
        lp_crop = None

        while self.running and not self.frames_queue.empty():
            try:
                frame = self.frames_queue.get_nowait()
                self.logger.debug("[AgentB] Frame obtido da fila para processamento.")
            except Empty:
                self.logger.warning("[AgentB] Fila de frames vazia inesperadamente.")
                time.sleep(0.05)
                continue

            try:
                self.logger.info("[AgentB] YOLO (LP) a correr…")
                results = self.yolo.detect(frame)

                if not results:
                    self.logger.debug("[AgentB] YOLO retornou vazio para este frame.")
                    continue

                if self.yolo.found_license_plate(results):
                    boxes = self.yolo.get_boxes(results)
                    self.logger.info(f"[AgentB] Detetadas {len(boxes)} matrículas.")

                    for i, box in enumerate(boxes, start=1):
                        x1, y1, x2, y2, conf = map(float, box)
                        if conf < 0.5:
                            self.logger.debug(f"[AgentB] Ignorada deteção fraca (conf={conf:.2f}).")
                            continue

                        crop = frame[int(y1):int(y2), int(x1):int(x2)]
                        crop_path = f"{CROPS_PATH}/lp_crop_{int(time.time())}_{i}.jpg"
                        try:
                            cv2.imwrite(crop_path, crop)
                            self.logger.debug(f"[AgentB] Crop guardado: {crop_path}")
                        except Exception as e:
                            self.logger.warning(f"[AgentB] Falha a guardar crop: {e}")

                        self.logger.info("[AgentB] OCR a extrair texto…")
                        try:
                            text, ocr_conf = self.ocr.extract_text(crop)
                            lp_results.append((text, float(ocr_conf)))
                            lp_crop = crop
                            self.logger.info(f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")
                        except Exception as e:
                            self.logger.exception(f"[AgentB] Falha no OCR: {e}")
                else:
                    self.logger.info("[AgentB] Não foi detetada matrícula neste frame.")

            except Exception as e:
                self.logger.exception(f"[AgentB] Erro no loop de deteção: {e}")

        if not lp_results:
            self.logger.warning("[AgentB] Não houve matrículas válidas em nenhum frame.")
            return None, None, None

        try:
            final_text, conf = self.consensus_Alg(lp_results)
            self.logger.info(f"[AgentB] Matrícula final: '{final_text}' (conf={conf:.2f})")
            return final_text, conf, lp_crop
        except Exception as e:
            self.logger.exception(f"[AgentB] Erro ao consolidar resultados: {e}")
            return None, None, None

    def consensus_Alg(self, results):
        """Combina/seleciona o melhor resultado do OCR."""
        # TODO: implementar algoritmo de consenso mais robusto
        self.logger.debug("[AgentB] A calcular resultado final (consenso simples).")
        return results[-1][0], results[-1][1]

    def _publish_lp_detected(self, timestamp, truck_id, plate_text, plate_conf, correlation_id):
        """Publica evento 'license-plate-detected' com propagação do correlationId."""
        payload = {
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "truckId": truck_id,
            "licensePlate": plate_text,
            "confidence": float(plate_conf if plate_conf is not None else 0.0)
        }
        self.logger.info(f"[AgentB] A publicar '{TOPIC_OUT}' (truckId={truck_id}, plate={plate_text}) …")
        self.producer.produce(
            topic=TOPIC_OUT,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"correlationId": correlation_id or str(uuid.uuid4())}
        )
        self.producer.poll(0)

    def run(self):
        self.logger.info(f"[AgentB] Main loop a iniciar… (topic in='{TOPIC_IN}')")

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
                    self.logger.warning("[AgentB] Mensagem inválida (JSON). Ignorada.")
                    continue

                # correlationId (propagar se existir)
                correlation_id = None
                for k, v in (msg.headers() or []):
                    if k == "correlationId" and v is not None:
                        correlation_id = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        break
                if correlation_id is None:
                    correlation_id = str(uuid.uuid4())

                # dados de entrada (truckId, timestamp)
                in_timestamp = data.get("timestamp")
                truck_id = data.get("truckId")

                self.logger.info("[AgentB] Recebido 'truck-detected'. A iniciar pipeline LP…")
                plate_text, plate_conf, _lp_img = self.process_license_plate_detection()

                if not plate_text:
                    self.logger.warning("[AgentB] Sem texto de matrícula final — não vou publicar.")
                    # dependendo do teu desenho, poderias publicar mesmo assim com conf=0.0
                    continue

                self._publish_lp_detected(
                    timestamp=in_timestamp,
                    truck_id=truck_id,
                    plate_text=plate_text,
                    plate_conf=plate_conf,
                    correlation_id=correlation_id
                )

        except KeyboardInterrupt:
            self.logger.info("[AgentB] Interrompido por utilizador.")
        except KafkaException as e:
            self.logger.exception(f"[AgentB/Kafka] Erro de Kafka: {e}")
        except Exception as e:
            self.logger.exception(f"[AgentB] Erro inesperado: {e}")
        finally:
            self.logger.info("[AgentB] A fechar recursos…")
            try:
                self.producer.flush(5)
            except Exception:
                pass
            try:
                self.consumer.close()
            except Exception:
                pass

    def stop(self):
        self.logger.info("[AgentB] A parar agente e libertar recursos…")
        self.running = False
        try:
            self.yolo.close()
        except Exception as e:
            self.logger.exception(f"[AgentB] Erro ao fechar YOLO: {e}")
        self.logger.info("[AgentB] Parado com sucesso.")

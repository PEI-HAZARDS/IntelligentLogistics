from agentB_microservice.src.RTSPstream import RTSPStream
from agentB_microservice.src.YOLO_License_Plate import *
from agentB_microservice.src.OCR import *
from agentB_microservice.src.CropStorage import CropStorage
from agentB_microservice.src.PlateClassifier import PlateClassifier

import os
import time
import cv2
import json
import uuid
from queue import Queue, Empty
from confluent_kafka import Producer, Consumer, KafkaException, KafkaError
import logging
from typing import Optional, Tuple

# --- Configuration ---
# Load environment variables or fallback to default network settings
NGINX_RTMP_HOST = os.getenv("NGINX_RTMP_HOST", "10.255.32.35")
NGINX_RTMP_PORT = os.getenv("NGINX_RTMP_PORT", "1935")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
GATE_ID = os.getenv("GATE_ID", "gate01")
RTSP_STREAM_HIGH = os.getenv("RTSP_STREAM_HIGH", f"rtmp://{NGINX_RTMP_HOST}:{NGINX_RTMP_PORT}/streams_high/{GATE_ID}")

# MinIO Configuration
MINIO_CONF = {
    "endpoint": os.getenv("MINIO_HOST"),
    "access_key": os.getenv("ACCESS_KEY"),
    "secret_key": os.getenv("SECRET_KEY"),
    "secure": True  #use HTTPS
}

BUCKET_NAME = os.getenv("BUCKET_NAME", "lp-crops")

# --- Operational Constants ---
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 5  # seconds
TOPIC_CONSUME = f"truck-detected-{GATE_ID}"
TOPIC_PRODUCE = "lp-results-{GATE_ID}"

logger = logging.getLogger("AgentB")


class AgentB:
    """
    Agent B:
    - Consumes 'truck-detected' events from Kafka.
    - Upon receipt, connects to/reads from the High-Quality RTSP stream.
    - Detects license plates using YOLO and extracts text using OCR.
    - Uses a consensus algorithm to validate characters across multiple frames.
    - Publishes 'license-plate-detected' to Kafka, propagating the correlationId.
    """

    def __init__(self):
        # Initialize models
        self.yolo = YOLO_License_Plate()
        self.ocr = OCR()
        self.classifier = PlateClassifier()
        self.running = True
        self.frames_queue = Queue()

        # Connect on-demand when a Kafka event is received.
        self.stream = None

        # ============================================================
        # ESTADO DO CONSENSO
        # ============================================================
        # Contador dinâmico: cada posição mapeia {caractere: contagem}
        # Exemplo: {0: {'A': 3, 'B': 1}, 1: {'B': 4}, ...}
        self.counter = {}

        # Rastreio de caracteres já decididos: {posição: caractere}
        self.decided_chars = {}

        # Threshold para decisão (quantas vezes precisa aparecer)
        self.decision_threshold = 6

        # Percentagem mínima de posições decididas para consenso (80%)
        self.consensus_percentage = 0.8

        # Melhor crop até agora
        self.best_crop = None
        self.best_confidence = 0.0

        self.crop_storage = CropStorage(MINIO_CONF, BUCKET_NAME)

        # Initialize Kafka
        logger.info(f"[AgentB/Kafka] Connecting to kafka via '{KAFKA_BOOTSTRAP}' …")

        # Kafka Consumer configuration
        self.consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id": "agentB-group",
            #: "latest" para ir buscar a ultima mensagem disponivel de
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,  # :  maneira a ler em tempo real
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })

        self.consumer.subscribe([TOPIC_CONSUME])

        # Kafka Producer configuration
        self.producer = Producer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
        })

    def _reset_consensus_state(self):
        """Reseta o estado do algoritmo de consenso."""
        self.counter = {}
        self.decided_chars = {}
        self.best_crop = None
        self.best_confidence = 0.0
        logger.debug("[AgentB] Consensus state reset.")

    def _get_frames(self, num_frames=30):
        """
        Captures a burst of frames from the RTMP/RTSP stream.
        
        Args:
            num_frames: The number of frames to buffer for processing.
        """
        # Connect to stream if not already
        if self.stream is None:
            logger.info(
                f"[AgentB] Connecting to RTMP stream (via Nginx): {RTSP_STREAM_HIGH}")
            try:
                self.stream = RTSPStream(RTSP_STREAM_HIGH)
            
            except Exception as e:
                logger.exception(f"[AgentB] Failed to connect to stream: {e}")
                return

        logger.info(f"[AgentB] Reading {num_frames} frame(s) from RTMP…")

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
        """
        Main pipeline to detect and extract license plate text.
        
        Returns:
            tuple: (plate_text, confidence, crop_image) or (None, None, None)
        """
        logger.info(
            "[AgentB] Starting license plate pipeline detection process…")

        # Reset consensus state before starting new detection
        self._reset_consensus_state()
        
        # Capture frames
        self._get_frames(30)

        if self.frames_queue.empty():
            logger.warning("[AgentB] No frame captured from RTSP.")
            return None, None, None

        # Process frames until consensus is reached or queue is empty
        while self.running and not self.frames_queue.empty():
            try:
                frame = self.frames_queue.get_nowait()
                logger.debug("[AgentB] Frame obtained from queue.")

            except Empty:
                logger.warning("[AgentB] Frames queue is empty.")
                time.sleep(0.05)
                continue

            # Process single frame
            result = self._process_single_frame(frame)

            # Se atingiu consenso completo, retornar imediatamente
            if result:
                text, conf, crop = result
                logger.info(
                    f"[AgentB] Consensus reached: '{text}' (conf={conf:.2f})")

                # Limpar frames restantes da queue
                remaining = self.frames_queue.qsize()
                if remaining > 0:
                    logger.debug(f"[AgentB] Clearing {remaining} remaining frames from queue")
                    while not self.frames_queue.empty():
                        try:
                            self.frames_queue.get_nowait()
                        except Empty:
                            break

                return text, conf, crop

        # Se não atingiu consenso completo, retornar melhor resultado parcial
        return self._get_best_partial_result()

    def _process_single_frame(self, frame):
        """
        Processes a single video frame.
        Retuns (text, conf, crop) if consensus is reached, else None.
        """
        
        try:
            logger.info("[AgentB] YOLO (LP) running…")
            results = self.yolo.detect(frame)

            if not results:
                logger.debug(
                    "[AgentB] YOLO did not return a result for this frame.")
                return None

            if not self.yolo.found_license_plate(results):
                logger.info(
                    "[AgentB] No license plate detected for this frame.")
                return None

            boxes = self.yolo.get_boxes(results)
            logger.info(f"[AgentB] {len(boxes)} license plates detected.")

            for i, box in enumerate(boxes, start=1):
                x1, y1, x2, y2, conf = map(float, box)

                if conf < 0.4:
                    logger.info(
                        f"[AgentB] Ignored low confidence box (conf={conf:.2f}).")
                    continue

                # Extract Crop
                crop = frame[int(y1):int(y2), int(x1):int(x2)]

                # ============================================================
                # NOVO: Classificar o crop (matrícula vs placa de perigo)
                # ============================================================
                classification = self.classifier.classify(crop)

                if classification != PlateClassifier.LICENSE_PLATE:
                    # Salvar crop rejeitado para debug
                    rejected_path = f"{REJECTED_CROPS_PATH}/{classification}_{int(time.time())}_{i}.jpg"
                    try:
                        self.classifier.visualize_classification(
                            crop, classification, rejected_path)
                    except Exception as e:
                        logger.warning(
                            f"[AgentB] Failed saving rejected crop: {e}")

                    logger.warning(
                        f"[AgentB] ❌ Crop {i} rejected: classified as {classification.upper()}"
                    )
                    continue

                logger.info(f"[AgentB] ✅ Crop {i} accepted as LICENSE_PLATE")
                # ============================================================

                # Guardar crop aceito
                crop_path = f"{CROPS_PATH}/lp_crop_{int(time.time())}_{i}.jpg"
                logger.info(f"[AgentB] Saving crop {i} to {crop_path}…")

                try:
                    # Salvar com visualização
                    self.classifier.visualize_classification(
                        crop, classification, crop_path)
                except Exception as e:
                    logger.warning(f"[AgentB] Failed saving crop: {e}")

                # Run OCR
                logger.info("[AgentB] OCR extracting text…")
                try:
                    text, ocr_conf = self.ocr._extract_text(crop)

                    if not text or ocr_conf <= 0.0:
                        logger.debug(
                            f"[AgentB] OCR returned no valid text for crop {i}")
                        continue

                    logger.info(
                        f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")

                    # Atualizar melhor crop
                    if ocr_conf > self.best_confidence:
                        self.best_crop = crop
                        self.best_confidence = ocr_conf

                    # Adicionar ao consenso
                    self._add_to_consensus(text, ocr_conf)

                    # Verificar se atingiu consenso
                    if self._check_full_consensus():
                        final_text = self._build_final_text()
                        logger.info(
                            f"[AgentB] Full consensus achieved: '{final_text}'")
                        return final_text, 1.0, crop

                except Exception as e:
                    logger.exception(f"[AgentB] OCR failure: {e}")

        except Exception as e:
            logger.exception(f"[AgentB] Error processing frame: {e}")

        return None

    def _add_to_consensus(self, text: str, confidence: float):
        """
        Adiciona resultado do OCR ao algoritmo de consenso.
        Vota em cada caractere na sua posição.
        """

        # Ignorar confianças baixas
        if confidence < 0.5:
            logger.debug(
                f"[AgentB] Confidence too low ({confidence:.2f}), skipping")
            return

        # Normalizar texto (uppercase, remover espaços)
        text_normalized = text.upper().replace(" ", "").replace("-", "")

        # Ignorar se muito curto
        if len(text_normalized) < 4:
            logger.debug(
                f"[AgentB] Text too short ('{text_normalized}'), skipping")
            return

        logger.debug(
            f"[AgentB] Adding to consensus: '{text_normalized}' (conf={confidence:.2f})")

        # Expandir o dicionário dinamicamente para novas posições
        for pos in range(len(text_normalized)):
            if pos not in self.counter:
                self.counter[pos] = {}

        # Adicionar cada caractere ao consenso da posição correta
        for pos, char in enumerate(text_normalized):
            if char not in self.counter[pos]:
                self.counter[pos][char] = 0

            # Votos ponderados por confiança
            if confidence >= 0.8:
                self.counter[pos][char] += 2
            else:
                self.counter[pos][char] += 1

            # Verificar se esta posição atingiu threshold
            if self.counter[pos][char] >= self.decision_threshold:
                if pos not in self.decided_chars:
                    self.decided_chars[pos] = char
                    logger.debug(f"[AgentB] Position {pos} decided: '{char}'")
                elif self.decided_chars[pos] != char:
                    # Se mudou, atualizar
                    old_char = self.decided_chars[pos]
                    self.decided_chars[pos] = char
                    logger.debug(
                        f"[AgentB] Position {pos} changed: '{old_char}' -> '{char}'")

    def _check_full_consensus(self) -> bool:
        """
        Verifica se atingiu consenso baseado em percentagem de posições decididas.
        Exemplo: se tem 8 posições e 80% = 6.4, precisa de 7 posições decididas.
        """
        if not self.counter:
            return False

        total_positions = len(self.counter)
        decided_count = len(self.decided_chars)

        # Calcular quantas posições precisam estar decididas (arredondar para cima)
        import math
        required_positions = math.ceil(
            total_positions * self.consensus_percentage)

        if decided_count >= required_positions:
            logger.info(
                f"[AgentB] Consensus reached! {decided_count}/{total_positions} positions decided (need {required_positions}) ✓")
            return True

        logger.debug(
            f"[AgentB] Consensus check: {decided_count}/{total_positions} positions decided (need {required_positions})")
        return False

    def _build_final_text(self) -> str:
        """Constrói o texto final a partir dos caracteres decididos."""
        if not self.decided_chars:
            return ""

        # Construir texto na ordem das posições
        text_chars = []
        for pos in sorted(self.decided_chars.keys()):
            text_chars.append(self.decided_chars[pos])

        final_text = "".join(text_chars)
        logger.debug(f"[AgentB] Built final text: '{final_text}'")

        return final_text

    def _get_best_partial_result(self):
        """
        Retorna o melhor resultado parcial se consenso completo não foi atingido.
        Preenche posições não decididas com o caractere mais votado.
        """
        if not self.counter:
            logger.warning(
                "[AgentB] No valid license plates detected in any frame.")
            return None, None, None

        # Construir texto com posições decididas + melhores candidatos
        text_chars = []
        total_positions = max(self.counter.keys()) + 1

        for pos in range(total_positions):
            if pos in self.decided_chars:
                # Usar caractere decidido
                text_chars.append(self.decided_chars[pos])
            elif pos in self.counter and self.counter[pos]:
                # Usar o caractere com mais votos
                best_char = max(
                    self.counter[pos].items(), key=lambda x: x[1])[0]
                text_chars.append(best_char)
            else:
                # Posição sem dados (improvável)
                text_chars.append("_")

        partial_text = "".join(text_chars)

        # Calcular confiança baseada em percentagem de posições decididas
        decided_count = len(self.decided_chars)
        confidence = decided_count / total_positions
        # Máximo 0.95 para resultado parcial
        confidence = min(confidence, 0.95)

        logger.info(
            f"[AgentB] Partial result: '{partial_text}' ({decided_count}/{total_positions} decided, conf={confidence:.2f})")

        return partial_text, confidence, self.best_crop

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Construct JSON payload
        payload = {
            "timestamp": timestamp,
            "licensePlate": plate_text,
            "confidence": float(plate_conf if plate_conf is not None else 0.0),
            "cropUrl": crop_url
        }
        
        logger.info(
            f"[AgentB] Publishing '{TOPIC_PRODUCE}' (truckId={truck_id}, plate={plate_text}) …")

        # Send to Kafka
        self.producer.produce(
            topic=TOPIC_PRODUCE,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id},
            callback=self._delivery_callback
        )

        self.producer.poll(0)

    def _loop(self):
        """Main loop for Agent B."""
        logger.info(
            f"[AgentB] Main loop starting… (topic in='{TOPIC_CONSUME}')")

        try:
            while self.running:
                # SKIP OLD MESSAGES - Process only the latest
                msg = None
                msgs_buffer = []

                # Poll múltiplas vezes para drenar mensagens antigas
                while True:
                    temp_msg = self.consumer.poll(timeout=0.1)
                    if temp_msg is None:
                        break  # No more messages
                    if temp_msg.error():
                        continue
                    msgs_buffer.append(temp_msg)

                # Se há mensagens, pegar apenas a última
                if msgs_buffer:
                    msg = msgs_buffer[-1]  # ← Last message in buffer
                    skipped = len(msgs_buffer) - 1
                    if skipped > 0:
                        logger.info(
                            f"[AgentB] Skipped {skipped} old messages, processing latest only")
                else:
                    # Wait for new message
                    msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue
                if msg.error():
                    continue

                # Parse Input Payload
                try:
                    data = json.loads(msg.value())
                except json.JSONDecodeError:
                    logger.warning("[AgentB] Invalid message (JSON). Ignored.")
                    continue

                # Extract truckId (Propagate if exists)
                truck_id = None
                for k, v in (msg.headers() or []):
                    if k == "truckId" and v is not None:
                        truck_id = v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                        break
                if truck_id is None:
                    truck_id = str(uuid.uuid4())

                # dados de entrada (truckId, timestamp)
                in_timestamp = data.get("timestamp")

                logger.info(
                    f"[AgentB] Received 'truck-detected' (truckId={truck_id}). Starting LP pipeline…")

                # Processar detecção de matrícula
                plate_text, plate_conf, _lp_img = self.process_license_plate_detection()

                if not plate_text:
                    logger.warning(
                        "[AgentB] No final text results — not publishing.")
                    continue
                
                # Upload best crop to MinIO
                crop_url = None
                if self.best_crop is not None:
                    try:
                        # Generate unique object name
                        object_name = f"lp_{truck_id}_{plate_text}.jpg"
                        crop_url = self.crop_storage.upload_memory_image(self.best_crop, object_name)
                        
                        if crop_url:
                            logger.info(f"[AgentB] Crop uploaded to MinIO: {crop_url}")
                        else:
                            logger.warning("[AgentB] Failed to upload crop to MinIO")
                    except Exception as e:
                        logger.exception(f"[AgentB] Error uploading crop to MinIO: {e}")
                
                # Publish result

                # Publicar a mensagem de matrícula detetada
                self._publish_lp_detected(
                    truck_id=truck_id,
                    plate_text=plate_text,
                    plate_conf=plate_conf,
                    crop_url=crop_url
                )

                # Clear frames queue for next detection
                with self.frames_queue.mutex:
                    self.frames_queue.queue.clear()
                
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
        """Gracefully stop Agent B."""

        logger.info("[AgentB] Stopping agent and freeing resources…")
        self.running = False
        self.running = False
        logger.info("[AgentB] Stopped successfully.")

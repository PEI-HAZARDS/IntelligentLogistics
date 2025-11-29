# AgentB.py — versão Kafka (CORRIGIDA)
from agentB_microservice.src.RTSPstream import RTSPStream
from agentB_microservice.src.YOLO_License_Plate import *
from agentB_microservice.src.OCR import *

import os
import time
import cv2
import json
import uuid
from queue import Queue, Empty
from confluent_kafka import Producer, Consumer, KafkaException

# URL do stream HIGH (4K) via Nginx RTMP
NGINX_RTMP_HOST = os.getenv("NGINX_RTMP_HOST", "10.255.32.35")
NGINX_RTMP_PORT = os.getenv("NGINX_RTMP_PORT", "1935")
MAX_CONNECTION_RETRIES = 10
RETRY_DELAY = 5  # seconds

RTSP_STREAM_HIGH = os.getenv(
    "RTSP_STREAM_HIGH",
    f"rtmp://{NGINX_RTMP_HOST}:{NGINX_RTMP_PORT}/streams_high/gate01"
)
CROPS_PATH = "agentB_microservice/data/lp_crops"
os.makedirs(CROPS_PATH, exist_ok=True)

# Configurações Kafka
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "10.255.32.143:9092")
TOPIC_CONSUME = "truck-detected-gate01"
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

        # ============================================================
        # ESTADO DO CONSENSO 
        # ============================================================
        # Contador para consenso: cada posição (0-7) mapeia caractere
        self.counter = {
            0: {},  # Posição 0
            1: {},  # Posição 1
            2: {},  # Posição 2
            3: {},  # Posição 3
            4: {},  # Posição 4
            5: {},  # Posição 5
            6: {},  # Posição 6 
            7: {}   # Posição 7 
        }
        
        # Rastreio de caracteres já decididos
        self.decided_chars = {}
        
        # Threshold para decisão (quantas vezes precisa aparecer)
        self.decision_threshold = 5
        
        # Melhor crop até agora
        self.best_crop = None
        self.best_confidence = 0.0

        bootstrap = kafka_bootstrap or KAFKA_BOOTSTRAP
        logger.info(f"[AgentB/Kafka] bootstrap: {bootstrap}")

        # Kafka Consumer
        self.consumer = Consumer({
            "bootstrap.servers": bootstrap,
            "group.id": "agentB-group",
            "auto.offset.reset": "latest",  #: "latest" para ir buscar a ultima mensagem disponivel de    
            "enable.auto.commit": True,     #:  maneira a ler em tempo real
            "session.timeout.ms": 10000,
            "max.poll.interval.ms": 300000,
        })
        self.consumer.subscribe([TOPIC_CONSUME])

        # Kafka Producer
        self.producer = Producer({
            "bootstrap.servers": bootstrap,
        })



    def _reset_consensus_state(self):
        """Reseta o estado do algoritmo de consenso."""
        for pos in self.counter:
            self.counter[pos] = {}
        self.decided_chars = {}
        self.best_crop = None
        self.best_confidence = 0.0
        logger.debug("[AgentB] Consensus state reset.")



    def _get_frames(self, num_frames=30):
        """Captura alguns frames do RTMP/RTSP."""
        # Conectar ao stream se não estiver conectado
        if self.stream is None:
            logger.info(
                f"[AgentB] Connecting to RTMP stream (via Nginx): {RTSP_STREAM_HIGH}")
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
        """
        Pipeline principal para detetar e extrair texto da matrícula.
        
        Returns:
            tuple: (plate_text, confidence, crop_image) ou (None, None, None)
        """
        logger.info("[AgentB] Starting license plate pipeline detection process…")

        # Reset do estado de consenso
        self._reset_consensus_state()
        
        # Capturar frames
        self._get_frames(30)
        
        if self.frames_queue.empty():
            logger.warning("[AgentB] No frame captured from RTSP.")
            return None, None, None

        # Processar frames até atingir consenso ou acabarem os frames
        while self.running and not self.frames_queue.empty():
            try:
                frame = self.frames_queue.get_nowait()
                logger.debug("[AgentB] Frame obtained from queue.")
            except Empty:
                logger.warning("[AgentB] Frames queue is empty.")
                time.sleep(0.05)
                continue

            # Processar frame
            result = self._process_single_frame(frame)
            
            # Se atingiu consenso completo, retornar imediatamente
            if result:
                text, conf, crop = result
                logger.info(f"[AgentB] Consensus reached: '{text}' (conf={conf:.2f})")
                return text, conf, crop
        
        # Se não atingiu consenso completo, retornar melhor resultado parcial
        return self._get_best_partial_result()



    def _process_single_frame(self, frame):
        """
        Processa um único frame.
        Retorna (text, conf, crop) se atingir consenso, senão None.
        """
        try:
            logger.info("[AgentB] YOLO (LP) running…")
            results = self.yolo.detect(frame)

            if not results:
                logger.debug("[AgentB] YOLO did not return a result for this frame.")
                return None

            if not self.yolo.found_license_plate(results):
                logger.info("[AgentB] No license plate detected for this frame.")
                return None

            boxes = self.yolo.get_boxes(results)
            logger.info(f"[AgentB] {len(boxes)} license plates detected.")

            for i, box in enumerate(boxes, start=1):
                x1, y1, x2, y2, conf = map(float, box)
                
                if conf < 0.75:
                    logger.info(f"[AgentB] Ignored low confidence box (conf={conf:.2f}).")
                    continue

                # Extrair crop
                crop = frame[int(y1):int(y2), int(x1):int(x2)]
                
                # Guardar crop
                crop_path = f"{CROPS_PATH}/lp_crop_{int(time.time())}_{i}.jpg"
                try:
                    cv2.imwrite(crop_path, crop)
                    logger.debug(f"[AgentB] Crop saved: {crop_path}")
                except Exception as e:
                    logger.warning(f"[AgentB] Failed saving crop: {e}")

                # OCR
                logger.info("[AgentB] OCR extracting text…")
                try:
                    text, ocr_conf = self.ocr._extract_text(crop)
                    
                    if not text or ocr_conf <= 0.0:
                        logger.debug(f"[AgentB] OCR returned no valid text for crop {i}")
                        continue
                    
                    logger.info(f"[AgentB] OCR: '{text}' (conf={ocr_conf:.2f})")
                    
                    # Atualizar melhor crop
                    if ocr_conf > self.best_confidence:
                        self.best_crop = crop
                        self.best_confidence = ocr_conf
                    
                    # Adicionar ao consenso
                    self._add_to_consensus(text, ocr_conf)
                    
                    # Verificar se atingiu consenso
                    if self._check_full_consensus():
                        final_text = self._build_final_text()
                        logger.info(f"[AgentB] Full consensus achieved: '{final_text}'")
                        return final_text, 1.0, crop
                    
                except Exception as e:
                    logger.exception(f"[AgentB] OCR failure: {e}")

        except Exception as e:
            logger.exception(f"[AgentB] Error processing frame: {e}")
        
        return None



    def _add_to_consensus(self, text: str, confidence: float):
        """
        Adiciona resultado do OCR ao algoritmo de consenso.
        """


        # Ignorar confianças baixas
        if confidence < 0.5:
            logger.debug(f"[AgentB] Confidence too low ({confidence:.2f}), skipping")
            return

        logger.debug(f"[AgentB] Adding to consensus: '{text}'")

        # Expande o dicionário se o texto tiver mais posições do que as já vistas
        for pos in range(len(text)):
            if pos not in self.counter:
                self.counter[pos] = {}

        # Adiciona cada caractere ao consenso da posição correta
        for pos, char in enumerate(text):
            if char not in self.counter[pos]:
                self.counter[pos][char] = 0
            if confidence >= 0.8:
                self.counter[pos][char] += 2
            else:
                self.counter[pos][char] += 1

            # Verificar consenso por posição
            if self.counter[pos][char] >= self.decision_threshold:
                if pos not in self.decided_chars:
                    self.decided_chars[pos] = char
                    logger.debug(f"[AgentB] Position {pos} decided: '{char}'")




    def _check_full_consensus(self) -> bool:
        """
        Verifica se todas as posições necessárias foram decididas.
        
        """
        decided_count = len(self.decided_chars)
        total_simbols = len(self.counter)


        # Considera consenso se tiver pelo menos 6 caracteres decididos
        if decided_count == total_simbols:
            logger.debug(f"[AgentB] Consensus check: {decided_count}/6+ positions decided ✓")
            return True
        
        logger.debug(f"[AgentB] Consensus check: {decided_count}/6 positions decided")
        return False



    def _build_final_text(self) -> str:
        """Constrói o texto final a partir dos caracteres decididos."""
        # Construir texto na ordem das posições
        text_chars = []
        for pos in sorted(self.decided_chars.keys()):
            text_chars.append(self.decided_chars[pos])
        
        final_text = "".join(text_chars)
        
        return final_text
    

    def _get_best_partial_result(self):
        """
        Retorna o melhor resultado parcial se consenso completo não foi atingido.
        """
        if not self.decided_chars:
            logger.warning("[AgentB] No valid license plates detected in any frame.")
            return None, None, None
        
        # Construir texto parcial
        partial_text = self._build_partial_text()
        
        # Calcular confiança baseada em quantos caracteres foram decididos
        confidence = len(self.decided_chars) / 6.0  # Normalizar para 6 caracteres
        confidence = min(confidence, 0.95)  # Máximo 0.95 para resultado parcial
        
        logger.info(f"[AgentB] Partial result: '{partial_text}' (conf={confidence:.2f})")
        
        return partial_text, confidence, self.best_crop


    def _build_partial_text(self) -> str:
        """
        Constrói texto parcial, preenchendo posições não decididas com '_'.
        """

        # Determinar tamanho esperado 
        max_pos = max(self.counter.keys())
        expected_length = max_pos
        
        # Verifica se aparece muitas vezes uma placa com esse tamanho senão o tamanha passa a ser o maior encontrado - 1
        if len(self.counter[max_pos]) < 10:
            expected_length = max_pos - 1
        
        

        text_chars = []
        for pos in range(expected_length):
            if pos in self.decided_chars:
                text_chars.append(self.decided_chars[pos])
            else:
                # Usar o caractere com mais votos, se existir
                if pos in self.counter and self.counter[pos]:
                    # Faz uma tupla apartir dos itens do dicionario e obtem o maior valor de contagem
                    best_char = max(self.counter[pos].items(), key=lambda x: x[1])[0]
                    text_chars.append(best_char)
                else:
                    text_chars.append("_")
        
        final_text = "".join(text_chars)
        
        return final_text


    def _publish_lp_detected(self, timestamp, truck_id, plate_text, plate_conf):
        """Publica evento 'license-plate-detected' com propagação do correlationId."""

        # Payload com o conteúdo da mensagem
        payload = {
            "timestamp": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "licensePlate": plate_text,
            "confidence": float(plate_conf if plate_conf is not None else 0.0)
        }
        logger.info(
            f"[AgentB] Publishing '{TOPIC_PRODUCE}' (truckId={truck_id}, plate={plate_text}) …")

        # Publica o tópico de deteção de matrícula
        self.producer.produce(
            topic=TOPIC_PRODUCE,
            key=None,
            value=json.dumps(payload).encode("utf-8"),
            headers={"truckId": truck_id or str(uuid.uuid4())}
        )
        self.producer.poll(0)

    def _loop(self):
        logger.info(
            f"[AgentB] Main loop starting… (topic in='{TOPIC_CONSUME}')")

        try:
            while self.running:
                # ============================================================
                # SKIP MENSAGENS ANTIGAS - Pegar apenas a última
                # ============================================================
                msg = None
                msgs_buffer = []
                
                # Poll múltiplas vezes para drenar mensagens antigas
                while True:
                    temp_msg = self.consumer.poll(timeout=0.1)
                    if temp_msg is None:
                        break  # Não há mais mensagens
                    if temp_msg.error():
                        continue
                    msgs_buffer.append(temp_msg)
                
                # Se há mensagens, pegar apenas a última
                if msgs_buffer:
                    msg = msgs_buffer[-1]  # ← Última mensagem do buffer
                    skipped = len(msgs_buffer) - 1
                    if skipped > 0:
                        logger.info(f"[AgentB] Skipped {skipped} old messages, processing latest only")
                else:
                    # Aguardar por nova mensagem
                    msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                if msg.error():
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
                
                logger.info(f"[AgentB] Received 'truck-detected' (truckId={truck_id}). Starting LP pipeline…")
                
                # Processar detecção de matrícula
                plate_text, plate_conf, _lp_img = self.process_license_plate_detection()

                if not plate_text:
                    logger.warning("[AgentB] No final text results — not publishing.")
                    continue
                
                # Publicar a mensagem de matrícula detetada
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
        logger.info("[AgentB] Stopped successfully.")
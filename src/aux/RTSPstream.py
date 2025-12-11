import threading
import cv2  # type: ignore
import time

import logging
logger = logging.getLogger("RTSPStream")


class RTSPStream:
    """
    Stream reader genérico - suporta RTSP, RTMP e outros protocolos via FFmpeg.

    Exemplos de URLs suportadas:
    - RTSP: rtsp://10.255.35.86:554/stream1
    - RTMP: rtmp://nginx-rtmp/streams_low/gate01
    - HTTP: http://example.com/stream.m3u8
    """

    def __init__(self, url):
        logger.info(f"[RTSPStream] Starting stream from: {url}")

        # OpenCV com backend FFmpeg suporta múltiplos protocolos
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

        # Configurações para baixa latência
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Buffer mínimo

        if not self.cap.isOpened():
            raise ConnectionError(f"Failed to connect to stream: {url}")

        # Lock para não alterar o mesmo frame em threads diferentes
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        self.url = url

        # Thread em paralelo para ler a stream continuamente
        t = threading.Thread(target=self.update, daemon=True)
        t.start()
        logger.info(f"[RTSPStream] Stream started successfully.")

    def update(self):
        """Thread que lê frames continuamente"""
        consecutive_failures = 0
        max_failures = 10

        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
                consecutive_failures = 0  # Reset contador
            else:
                consecutive_failures += 1
                logger.warning(
                    f"[RTSPStream] Failed to read frame ({consecutive_failures}/{max_failures})")

                if consecutive_failures >= max_failures:
                    logger.error(
                        f"[RTSPStream] Too many failures, stopping stream.")
                    self.running = False
                    break

                time.sleep(0.5)  # Aguardar antes de tentar novamente

    # Frame bloqueado para evitar alteração enquanto se está a ler
    def read(self):
        """Retorna cópia thread-safe do último frame"""
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def release(self):
        """Libera recursos e para thread"""
        logger.info(f"[RTSPStream] Releasing stream: {self.url}")
        self.running = False
        time.sleep(0.2)  # Aguardar thread terminar
        self.cap.release()
        logger.info(f"[RTSPStream] Stream released successfully.")

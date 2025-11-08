import threading
import cv2 # type: ignore

import logging
logger = logging.getLogger("RTSPStream")

class RTSPStream:
    def __init__(self, url):
        logger.info(f"[RTSP stream] Starting RTSP stream...")
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
        self.cap.set(46, 1)

        # Lock para não alterar o mesmo frame em threads diferentes
        self.lock = threading.Lock()
        self.frame = None
        self.running = True

        # Thread em paralelo para ver a stream
        t = threading.Thread(target=self.update, daemon=True)
        logger.info(f"[RTSP stream] RTSP stream started on {url}.")
        t.start()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame

    # Frame bloqueado para evitar alteração enquanto se esta a ler
    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def release(self):
        self.running = False
        self.cap.release()

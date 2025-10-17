import threading
import cv2 # type: ignore
from src.Logger import *

class RTSPStream:
    def __init__(self, url):
        self.logger = GlobalLogger().get_logger()
        self.logger.info(f"Starting RTSP stream...")
        self.cap = cv2.VideoCapture(url)
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        t = threading.Thread(target=self.update, daemon=True)
        self.logger.info(f"RTSP stream started on {url}.")
        t.start()

    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame

    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def release(self):
        self.running = False
        self.cap.release()

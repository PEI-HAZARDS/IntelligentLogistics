import threading
import cv2  # type: ignore
import time

import logging
logger = logging.getLogger("StreamReader")


class StreamReader:
    """
    Generic stream reader - supports RTSP, RTMP and other protocols via FFmpeg.

    Supported URL examples:
    - RTSP: rtsp://10.255.35.86:554/stream1
    - RTMP: rtmp://nginx-rtmp/streams_low/gate01
    - HTTP: http://example.com/stream.m3u8
    """

    def __init__(self, url):
        logger.info(f"[StreamReader] Starting stream from: {url}")

        # OpenCV with FFmpeg backend supports multiple protocols
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

        # Settings for low latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimum buffer

        if not self.cap.isOpened():
            raise ConnectionError(f"Failed to connect to stream: {url}")

        # Lock to prevent modifying the same frame in different threads
        self.lock = threading.Lock()
        self.frame = None
        self.running = True
        self.url = url

        # Thread in parallel to read stream continuously
        t = threading.Thread(target=self.update, daemon=True)
        t.start()
        logger.info("[StreamReader] Stream started successfully.")

    def update(self):
        """Thread that reads frames continuously"""
        consecutive_failures = 0
        max_failures = 10

        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
                consecutive_failures = 0  # Reset counter
            else:
                consecutive_failures += 1
                logger.warning(
                    f"[StreamReader] Failed to read frame ({consecutive_failures}/{max_failures})")

                if consecutive_failures >= max_failures:
                    logger.error(
                        "[StreamReader] Too many failures, stopping stream.")
                    self.running = False
                    break

                time.sleep(0.5)  # Wait before trying again

    # Frame locked to avoid alteration while reading
    def read(self):
        """Returns thread-safe copy of the last frame"""
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def release(self):
        """Releases resources and stops thread"""
        logger.info(f"[StreamReader] Releasing stream: {self.url}")
        self.running = False
        time.sleep(0.2)  # Wait for thread to finish
        self.cap.release()
        logger.info("[StreamReader] Stream released successfully.")

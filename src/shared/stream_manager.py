import threading
import cv2  # type: ignore
import time
import logging

logger = logging.getLogger("StreamManager")

class StreamManager:
    """
    Generic stream manager - supports RTSP, RTMP and other protocols via FFmpeg.
    Self-healing: Automatically reconnects in the background if the stream is lost.
    """

    def __init__(self, url, max_retries=10, retry_delay=5):
        self.url = url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.cap = None
        self.frame = None
        self.lock = threading.Lock()
        self.running = True

        # The update thread will handle the initial connection.
        logger.info(f"[StreamManager] Initialized for: {url}")

        # Thread in parallel to read stream continuously
        self.thread = threading.Thread(target=self.update, daemon=True)
        self.thread.start()

    def _connect_with_retry(self):
        """
        Internal method: Attempts to connect to the stream with automatic retry.
        Blocks until connected or max retries reached.
        """
        for attempt in range(1, self.max_retries + 1):
            if not self.running:
                break

            try:
                logger.info(f"[StreamManager] Connection attempt {attempt}/{self.max_retries} to: {self.url}")
                
                # Initialize capture
                cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Low latency setting

                if cap.isOpened():
                    logger.info("[StreamManager] Stream connected successfully.")
                    return cap
                else:
                    logger.warning(f"[StreamManager] Failed to open stream (attempt {attempt}).")
            
            except Exception as e:
                logger.error(f"[StreamManager] Error during connection: {e}")

            # Wait before retry (if not cancelled)
            if attempt < self.max_retries and self.running:
                time.sleep(self.retry_delay)
        
        logger.error("[StreamManager] Max retries reached. Stream is unreachable.")
        return None

    def _reconnect(self):
        """
        Internal method: Releases current resources and attempts to reconnect.
        """
        logger.warning("[StreamManager] Stream lost. Attempting to reconnect...")
        
        # 1. Release old resource
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        
        # 2. Clear current frame so consumers know data is stale/missing
        with self.lock:
            self.frame = None

        # 3. Attempt new connection
        self.cap = self._connect_with_retry()

    def update(self):
        """
        Background thread: Reads frames continuously and handles reconnection.
        """
        self.cap = self._connect_with_retry()
        consecutive_failures = 0
        max_failures = 10

        while self.running:
            # 1. Ensure we have a valid connection before trying to read
            if not self._ensure_connection_active():
                time.sleep(self.retry_delay)
                continue

            # 2. Attempt to read and handle result
            try:
                ret, frame = self.cap.read() # type: ignore

                if ret:
                    self._handle_read_success(frame)
                    consecutive_failures = 0
                else:
                    consecutive_failures = self._handle_read_failure(
                        consecutive_failures, max_failures
                    )

            except Exception as e:
                logger.exception(f"[StreamManager] Unexpected error in read loop: {e}")
                self._reconnect()

    def _ensure_connection_active(self):
        """Checks if connection is alive; attempts reconnect if needed."""
        if self.cap is None or not self.cap.isOpened():
            self._reconnect()
            return self.cap is not None
        return True

    def _handle_read_success(self, frame):
        """Updates the shared frame safely."""
        with self.lock:
            self.frame = frame

    def _handle_read_failure(self, current_failures, max_failures):
        """
        Handles a failed frame read: logs, waits, or triggers reconnect.
        Returns the updated failure count.
        """
        new_count = current_failures + 1
        logger.warning(
            f"[StreamManager] Frame read failed ({new_count}/{max_failures})")

        if new_count >= max_failures:
            self._reconnect()
            return 0  # Reset counter after reconnect attempt
        
        time.sleep(0.1)  # Brief pause on glitch
        return new_count

    def read(self):
        """
        Returns thread-safe copy of the last frame.
        Returns None if stream is currently connecting/reconnecting.
        """
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def release(self):
        """Releases resources and stops thread"""
        logger.info(f"[StreamManager] Stopping stream manager: {self.url}")
        self.running = False
        
        # Wait briefly for thread to notice
        self.thread.join(timeout=1.0)
        
        if self.cap:
            self.cap.release()
        logger.info("[StreamManager] Stopped.")
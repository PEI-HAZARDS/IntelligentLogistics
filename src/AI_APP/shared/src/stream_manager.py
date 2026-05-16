import threading
import cv2  # type: ignore
import time
import logging
import queue
import os

logger = logging.getLogger("StreamManager")

class StreamManager:
    """
    Generic stream manager - optimized for low-latency AI inference.
    Self-healing: Automatically reconnects in the background if the stream is lost.
    """

    def __init__(self, url, max_retries=10, retry_delay=5):
        self.url = url
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.cap = None
        self.running = False
        self.thread = None

        # Queue for frames
        self.frame_queue = queue.Queue() 

        logger.info(f"Initialized for: {url}")

    def connect(self):
        """Starts the stream and background thread. Call when the stream is needed."""
        if self.running:
            logger.warning("Stream is already running.")
            return

        logger.info(f"Connecting to: {self.url}")
        self.running = True
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
                logger.info(f"Connection attempt {attempt}/{self.max_retries} to: {self.url}")
                
                # --- THE FFMPEG HACK ---
                # Force TCP, disable buffering, and skip stream analysis delays
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                        "rtsp_transport;tcp|"
                        "fflags;nobuffer|"
                        "analyzeduration;0|"
                        "probesize;32|"
                        "tune;zerolatency"
                    )
                # Initialize capture
                cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) # Double-tap on low latency

                if cap.isOpened():
                    logger.info("Stream connected successfully.")
                    return cap
                else:
                    logger.warning(f"Failed to open stream (attempt {attempt}).")
            
            except Exception as e:
                logger.exception("Error during connection")

            if attempt < self.max_retries and self.running:
                time.sleep(self.retry_delay)
        
        logger.error("Max retries reached. Stream is unreachable.")
        return None

    def _reconnect(self):
        """Releases current resources and attempts to reconnect."""
        logger.warning("Stream lost. Attempting to reconnect...")
        
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
        
        # Clear the queue so consumers know data is stale/missing
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break

        self.cap = self._connect_with_retry()

    def update(self):
        """Background thread: Reads frames continuously and handles reconnection."""
        self.cap = self._connect_with_retry()
        consecutive_failures = 0
        max_failures = 10

        while self.running:
            if not self._ensure_connection_active():
                time.sleep(self.retry_delay)
                continue

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
                logger.exception(f"Unexpected error in read loop: {e}")
                self._reconnect()

    def _ensure_connection_active(self):
        if self.cap is None or not self.cap.isOpened():
            self._reconnect()
            return self.cap is not None
        return True

    def _handle_read_success(self, frame):
        """Safely updates the queue with the freshest frame."""
        # If the GPU hasn't read the last frame yet, throw it in the trash
        if self.frame_queue.full():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                pass
        
        # Push the brand new frame
        self.frame_queue.put(frame)

    def _handle_read_failure(self, current_failures, max_failures):
        new_count = current_failures + 1
        logger.warning(f"Frame read failed ({new_count}/{max_failures})")

        if new_count >= max_failures:
            self._reconnect()
            return 0
        
        time.sleep(0.1)
        return new_count

    def read(self, timeout=1.0):
        """
        Returns the next UNIQUE frame directly from memory (zero-copy).
        BLOCKS the calling thread until a new frame physically arrives from the camera.
        """
        try:
            return self.frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def release(self):
        """Releases resources and stops the background thread."""
        logger.info(f"Stopping stream manager: {self.url}")
        self.running = False
        
        if self.thread is not None:
            self.thread.join(timeout=1.0)
            self.thread = None
        
        if self.cap:
            self.cap.release()
            self.cap = None

        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
            
        logger.info("Stopped.")
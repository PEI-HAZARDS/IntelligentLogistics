import logging
import os

class GlobalLogger:
    _instance = None  # Singleton pattern to avoid reinitialization

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return  # Prevent reinitialization

        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "system.log")

        self.logger = logging.getLogger("SystemLogger")
        self.logger.setLevel(logging.INFO)

        # Suppress noisy libraries (like ultralytics)
        #logging.getLogger("ultralytics").setLevel(logging.ERROR)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # File handler (append mode, UTF-8 clean)
        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)

        # Add handlers only if not already attached to this logger
        if not any(isinstance(h, logging.FileHandler) for h in self.logger.handlers):
            self.logger.addHandler(file_handler)
        if not any(isinstance(h, logging.StreamHandler) for h in self.logger.handlers):
            self.logger.addHandler(console_handler)

        # Avoid logger propagation to root (prevents double-printing)
        self.logger.propagate = False

        self._initialized = True

    def get_logger(self):
        return self.logger

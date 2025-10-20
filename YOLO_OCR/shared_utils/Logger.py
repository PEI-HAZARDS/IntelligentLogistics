import logging

class GlobalLogger:
    def __init__(self):
        self.logger = logging.getLogger("SystemLogger")
        logging.getLogger("ultralytics").setLevel(logging.ERROR)

        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s")

        # Clear file on each start
        file_handler = logging.FileHandler("logs.log", mode='w')
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # Avoid duplicate handlers if this class is reinitialized
        if not self.logger.hasHandlers():
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
    
    def get_logger(self):
        return self.logger

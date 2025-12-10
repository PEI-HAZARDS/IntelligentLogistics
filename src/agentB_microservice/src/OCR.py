import logging
import easyocr
import cv2
import numpy as np
from PIL import Image

class OCR:
    def __init__(self):
        self.reader = easyocr.Reader(['en'])
    
    def _to_cv_image(self, image):
        if isinstance(image, str):
            img = cv2.imread(image)
            return img
        if isinstance(image, Image.Image):
            arr = np.array(image)
            if arr.ndim == 3:
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            return arr
        if isinstance(image, np.ndarray):
            return image
        return None

    def _preprocess_plate(self, cv_img):
        """Convert image to grayscale (black and white)."""
        if cv_img is None:
            raise ValueError("Could not convert input to CV image")
        
        # Convert to grayscale if image has color channels
        if len(cv_img.shape) == 3:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv_img
        
        return gray
    
    def _extract_text(self, cv_img):
        cv_img = self._preprocess_plate(cv_img)

        # Define allowed characters: A-Z, 0-9, and hyphen
        allowed_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- '
        
        results = self.reader.readtext(
            cv_img,
            allowlist=allowed_chars
        )
        
        if not results:
            # Return empty string with 0 confidence instead of raising
            return "", 0.0

        full_text = " ".join([res[1] for res in results])
        avg_confidence = sum([res[2] for res in results]) / len(results)
        
        return full_text, avg_confidence
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
        # Resize a bit if very small (helps recognition)
        h, w = cv_img.shape[:2]
        if w < 200:
            scale = max(1.0, 200 / w)
            cv_img = cv2.resize(cv_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        # Try CLAHE for better local contrast
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)

        # Try both polarities (text dark on light and light on dark)
        thresh_inv = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                           cv2.THRESH_BINARY_INV, 25, 15)
        thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                       cv2.THRESH_BINARY, 25, 15)

        # Choose the one with higher overall stroke area (heuristic)
        if thresh_inv.sum() > thresh.sum():
            chosen = thresh_inv
        else:
            chosen = thresh

        # Optionally apply a small morphological open to remove speckles
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
        chosen = cv2.morphologyEx(chosen, cv2.MORPH_OPEN, kernel)

        # Convert back to BGR because PaddleOCR expects color images (it will convert internally)
        return cv2.cvtColor(chosen, cv2.COLOR_GRAY2BGR)
    
    def _extract_text(self, cv_img):
        results = self.reader.readtext(cv_img)
        if not results:
            raise ValueError("EasyOCR returned empty results")

        full_text = " ".join([res[1] for res in results])
        avg_confidence = sum([res[2] for res in results]) / len(results)
        
        return full_text, avg_confidence
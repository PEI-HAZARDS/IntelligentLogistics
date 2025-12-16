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
        """
        Apply comprehensive preprocessing for hazard plates with orange/red backgrounds.
        
        Pipeline:
        1. Extract red channel (text appears darker on orange/red background)
        2. Apply CLAHE for contrast enhancement
        3. Bilateral filter for noise reduction while preserving edges
        4. Adaptive thresholding for binarization
        5. Morphological operations to clean up text
        6. Resize for better OCR resolution
        """
        if cv_img is None:
            raise ValueError("Could not convert input to CV image")
        
        # Ensure we have a color image for channel extraction
        if len(cv_img.shape) == 3:
            # Extract the red channel - on orange/red hazard plates, 
            # the dark text has low red values while the background has high red values
            # This gives better contrast than simple grayscale conversion
            b, g, r = cv2.split(cv_img)
            
            # Use the red channel as it provides best contrast for orange/red plates
            # The text (darker) will have lower values than the bright orange background
            gray = r
        else:
            gray = cv_img
        
        # Step 1: Resize image to improve OCR (2x upscale)
        height, width = gray.shape[:2]
        gray = cv2.resize(gray, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
        
        # Step 2: Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        # This enhances local contrast and makes text more visible
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # Step 3: Apply bilateral filter to reduce noise while keeping edges sharp
        # This helps remove graininess from the image while preserving text edges
        gray = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)
        
        # Step 4: Apply adaptive thresholding for binarization
        # This handles varying lighting conditions across the image
        binary = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=21,  # Size of the neighborhood for threshold calculation
            C=10           # Constant subtracted from the mean
        )
        
        # Step 5: Morphological operations to clean up the text
        # Remove small noise spots
        kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
        
        # Fill small gaps in text
        kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        
        return binary
    
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
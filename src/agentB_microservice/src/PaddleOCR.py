
"""
PaddleOCR-based License Plate Text Extraction

Optimized for license plate recognition with:
- Intelligent image resizing for better OCR accuracy
- Adaptive preprocessing (grayscale, denoising, contrast enhancement)
- Multiple recognition attempts with fallback strategies
"""

import logging
import cv2
import numpy as np
from PIL import Image
from paddleocr import PaddleOCR

logger = logging.getLogger("PaddleOCR")


class OCR:
    """
    PaddleOCR-based OCR class optimized for license plate recognition.
    
    Uses PaddleOCR with optimized settings for short text lines like license plates.
    """
    
    # Minimum dimensions for valid plates
    MIN_HEIGHT = 10
    MIN_WIDTH = 20

    def __init__(self):
        """Initialize PaddleOCR with settings optimized for license plates."""
        self.ocr = PaddleOCR(
            use_angle_cls=True,           # Enable angle classification for rotated plates
            lang='en',                    # English language (A-Z, 0-9)
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )
        logger.info("[PaddleOCR] Initialized with license plate optimizations")
    
    def _to_cv_image(self, image):
        """
        Convert various image formats to OpenCV BGR format.
        """
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

    def _preprocess_plate(self, cv_img, mode='standard'):
        """
        Preprocessing pipeline for license plate images.
        
        Args:
            cv_img: OpenCV image (BGR)
            mode: 'standard', 'aggressive', or 'minimal'
            
        Returns:
            Preprocessed image ready for OCR
        """
        if cv_img is None:
            raise ValueError("Could not convert input to CV image")
        
        h, w = cv_img.shape[:2]
        
        # Validate minimum dimensions
        if h < self.MIN_HEIGHT or w < self.MIN_WIDTH:
            logger.warning(f"[PaddleOCR] Image too small: {w}x{h}")
            raise ValueError(f"Image too small: {w}x{h}")
        
        if mode == 'minimal':
            # Just return the original image - let PaddleOCR handle it
            return cv_img
        
        # Convert to grayscale
        if len(cv_img.shape) == 3:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = cv_img.copy()
        
        if mode == 'standard':
            # Apply CLAHE for contrast enhancement
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
            gray = clahe.apply(gray)
            
        elif mode == 'aggressive':
            # Apply CLAHE
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            # Apply Otsu's thresholding
            _, gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Convert back to 3-channel for PaddleOCR
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    def _filter_text(self, text):
        """
        Filter and clean OCR output for license plate format.
        """
        if not text:
            return ""
        
        # Allowed characters for license plates
        allowed_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789- ')
        
        text = text.upper()
        
        # Filter to allowed characters only
        filtered = ''.join(c for c in text if c in allowed_chars)
        
        return filtered.strip()

    def _parse_result(self, result):
        """
        Parse PaddleOCR result and extract text and confidence.
        
        PaddleOCR 3.x returns results in format:
        [{'rec_texts': [...], 'rec_scores': [...], ...}]
        or list of detection results with text and scores
        """
        if not result:
            return "", 0.0
        
        texts = []
        confidences = []
        
        # Handle different result formats
        try:
            # Format 1: New PaddleOCR 3.x predict() format
            if isinstance(result, list) and len(result) > 0:
                for item in result:
                    if isinstance(item, dict):
                        # New format with rec_texts and rec_scores
                        if 'rec_texts' in item and 'rec_scores' in item:
                            texts.extend(item['rec_texts'])
                            confidences.extend(item['rec_scores'])
                        # Alternative key names
                        elif 'text' in item and 'score' in item:
                            texts.append(item['text'])
                            confidences.append(item['score'])
                    elif isinstance(item, (list, tuple)):
                        # Old format: [[box, (text, conf)], ...]
                        if len(item) >= 2:
                            text_data = item[-1]  # Last element is (text, conf)
                            if isinstance(text_data, (list, tuple)) and len(text_data) >= 2:
                                texts.append(str(text_data[0]))
                                confidences.append(float(text_data[1]))
                            elif isinstance(text_data, str):
                                texts.append(text_data)
                                confidences.append(0.5)  # Default confidence
        except Exception as e:
            logger.debug(f"[PaddleOCR] Error parsing result: {e}")
            logger.debug(f"[PaddleOCR] Raw result: {result}")
            return "", 0.0
        
        if not texts:
            # Try to extract any string from the result
            try:
                result_str = str(result)
                logger.debug(f"[PaddleOCR] Result as string: {result_str[:200]}")
            except:
                pass
            return "", 0.0
        
        full_text = " ".join(str(t) for t in texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        
        return full_text, avg_confidence

    def _extract_text_with_mode(self, cv_img, mode='standard'):
        """
        Single extraction attempt with specified preprocessing mode.
        """
        try:
            processed = self._preprocess_plate(cv_img, mode=mode)
            
            # Use predict() method for PaddleOCR 3.x
            result = self.ocr.predict(processed)
            
            text, conf = self._parse_result(result)
            
            # Filter the text
            text = self._filter_text(text)
            
            if text:
                logger.info(f"[PaddleOCR] Mode '{mode}': '{text}' (conf={conf:.2f})")
            else:
                logger.info(f"[PaddleOCR] Mode '{mode}': No text extracted")
            
            return text, conf
            
        except Exception as e:
            logger.warning(f"[PaddleOCR] Mode '{mode}' failed: {e}")
            return "", 0.0

    def _extract_text(self, cv_img):
        """
        Extract text from license plate crop with fallback strategies.
        
        Attempts multiple preprocessing strategies and returns the best result.
        
        Args:
            cv_img: OpenCV image of cropped license plate (BGR)
            
        Returns:
            tuple: (text, confidence)
        """
        cv_img = self._to_cv_image(cv_img)
        
        if cv_img is None:
            logger.warning("[PaddleOCR] Invalid image input")
            return "", 0.0
        
        h, w = cv_img.shape[:2] if cv_img is not None else (0, 0)
        logger.debug(f"[PaddleOCR] Processing image of size {w}x{h}")
        
        best_text = ""
        best_conf = 0.0
        
        # Try different preprocessing modes
        modes = ['minimal', 'standard', 'aggressive']
        
        for mode in modes:
            text, conf = self._extract_text_with_mode(cv_img, mode=mode)
            
            if conf > best_conf and text:
                best_text, best_conf = text, conf
            
            # If confidence is very high, stop trying other modes
            if best_conf >= 0.90:
                break
        
        if best_text:
            logger.info(f"[PaddleOCR] Best result: '{best_text}' ({best_conf:.2f})")
        else:
            logger.warning("[PaddleOCR] No text extracted from image")
        
        return best_text, best_conf
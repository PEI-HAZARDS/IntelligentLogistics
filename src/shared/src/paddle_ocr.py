"""
PaddleOCR-based License Plate Text Extraction

Optimized for license plate recognition with:
- Intelligent image resizing for better OCR accuracy
- Adaptive preprocessing (grayscale, padding)
"""

import logging
import cv2 # type: ignore
import numpy as np # type: ignore
from PIL import Image # type: ignore
from paddleocr import PaddleOCR # type: ignore

logger = logging.getLogger("PaddleOCR")


class OCR:
    """
    PaddleOCR-based OCR class optimized for license plate recognition.
    
    Uses PaddleOCR with optimized settings for short text lines like license plates.
    """
    
    # Minimum dimensions for valid plates
    MIN_HEIGHT = 10
    MIN_WIDTH = 20

    def __init__(self, allowed_chars=None):
        """Initialize PaddleOCR with settings optimized for license plates."""
        self.paddle_ocr = PaddleOCR(
            use_angle_cls=True,           # Enable angle classification for rotated plates
            lang='en',                    # English language (A-Z, 0-9)
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
        )
        self.allowed_chars = allowed_chars if allowed_chars else 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'
        
        logger.info("Initialized with allowed chars: " + self.allowed_chars)
    
    def _to_cv_image(self, image):
        """Convert various image formats to OpenCV BGR format."""
        if isinstance(image, str):
            return cv2.imread(image)
        
        if isinstance(image, Image.Image):
            arr = np.array(image)
            if arr.ndim == 3:
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            return arr
        
        if isinstance(image, np.ndarray):
            return image
        
        return None

    def _resize_and_pad(self, img, target_height=64):
        """
        Resize image to target height while maintaining aspect ratio,
        and add padding to improve OCR accuracy.
        
        Args:
            img: Input image
            target_height: Target height for resizing (default: 64)
            
        Returns:
            Resized and padded image
        """
        h, w = img.shape[:2]
        
        # Scale to target height while maintaining aspect ratio
        scale = target_height / h
        new_w = int(w * scale)
        
        # Use Lanczos resampling for better quality upscaling
        resized = cv2.resize(img, (new_w, target_height), interpolation=cv2.INTER_LANCZOS4)
        
        # Add padding to prevent text from touching edges
        padding = 10
        padded = cv2.copyMakeBorder(
            resized, 
            top=padding, 
            bottom=padding, 
            left=padding, 
            right=padding, 
            borderType=cv2.BORDER_REPLICATE
        )
        
        return padded

    def _preprocess_plate(self, cv_img):
        """
        Preprocess license plate image for OCR.
        
        Args:
            cv_img: Input OpenCV image
            
        Returns:
            Preprocessed image ready for OCR
            
        Raises:
            ValueError: If image is None or too small
        """
        if cv_img is None:
            raise ValueError("Could not convert input to CV image")
        
        h, w = cv_img.shape[:2]
        if h < self.MIN_HEIGHT or w < self.MIN_WIDTH:
            logger.warning(f"Image too small: {w}x{h}")
            raise ValueError(f"Image too small: {w}x{h}")

        # Resize and pad
        processed = self._resize_and_pad(cv_img, target_height=64)

        # Convert to grayscale
        if len(processed.shape) == 3:
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        else:
            gray = processed.copy()

        # Convert back to BGR for PaddleOCR
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    def _filter_text(self, text):
        """
        Filter and clean OCR output to only allowed characters.
        
        Args:
            text: Raw OCR text
            
        Returns:
            Filtered and cleaned text
        """
        if not text:
            return ""
        
        text = text.upper()
        
        # Filter to allowed characters only
        filtered = ''.join(c for c in text if c in self.allowed_chars)
        
        return filtered.strip()

    def _parse_dict_item(self, item, texts, confidences):
        """Parse dictionary format item (new PaddleOCR)."""
        if 'rec_texts' in item and 'rec_scores' in item:
            texts.extend(item['rec_texts'])
            confidences.extend(item['rec_scores'])
        elif 'text' in item and 'score' in item:
            texts.append(item['text'])
            confidences.append(item['score'])

    def _parse_list_item(self, item, texts, confidences):
        """Parse list/tuple format item (old PaddleOCR)."""
        if len(item) < 2:
            return
        text_data = item[-1]  # Last element is (text, conf)
        if isinstance(text_data, (list, tuple)) and len(text_data) >= 2:
            texts.append(str(text_data[0]))
            confidences.append(float(text_data[1]))
        elif isinstance(text_data, str):
            texts.append(text_data)
            confidences.append(0.5)  # Default confidence

    def _parse_result(self, result):
        """
        Parse PaddleOCR result and extract text and confidence.
        
        Args:
            result: PaddleOCR prediction result
            
        Returns:
            tuple: (text, confidence)
        """
        if not result or not isinstance(result, list):
            return "", 0.0
        
        texts = []
        confidences = []
        
        try:
            for item in result:
                if isinstance(item, dict):
                    self._parse_dict_item(item, texts, confidences)
                elif isinstance(item, (list, tuple)):
                    self._parse_list_item(item, texts, confidences)
        except Exception as e:
            logger.debug(f"Error parsing result: {e}")
            return "", 0.0
        
        if not texts:
            return "", 0.0
        
        full_text = " ".join(str(t) for t in texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
        
        return full_text, avg_confidence

    def _extract_text(self, cv_img):
        """
        Extract text from license plate crop.
        
        Args:
            cv_img: OpenCV image of cropped license plate (BGR) or path to image
            
        Returns:
            tuple: (text, confidence)
        """
        cv_img = self._to_cv_image(cv_img)
        
        if cv_img is None:
            logger.warning("Invalid image input")
            return "", 0.0
        
        h, w = cv_img.shape[:2]
        logger.debug(f"Processing image of size {w}x{h}")
        
        try:
            # Preprocess the image
            processed = self._preprocess_plate(cv_img)
            
            # Run OCR
            result = self.paddle_ocr.predict(processed)
            
            # Parse results
            text, conf = self._parse_result(result)
            
            # Filter the text
            text = self._filter_text(text)
            
            if text:
                logger.info(f"Result: '{text}' (conf={conf:.2f})")
            else:
                logger.info("Result: No text extracted")
            
            return text, conf
            
        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return "", 0.0
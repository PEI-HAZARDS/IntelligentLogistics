"""
PaddleOCR-based License Plate Text Extraction

Optimized for license plate recognition with:
- Intelligent image resizing for better OCR accuracy
- Adaptive preprocessing (grayscale, padding)
"""

import logging
import cv2 # type: ignore
import os
import numpy as np # type: ignore
from PIL import Image # type: ignore
from paddleocr import PaddleOCR # type: ignore

logger = logging.getLogger("PlateOCR")


class OCR:
    """
    PaddleOCR-based OCR class optimized for license/hazard plate recognition.
    
    Uses PaddleOCR with optimized settings for short text lines like license/hazard plates.
    """
    
    # Minimum dimensions for valid plates
    MIN_HEIGHT = 10
    MIN_WIDTH = 20

    # Preprocessing defaults
    DEFAULT_TARGET_HEIGHT = 64
    DEFAULT_PADDING = 10

    # Used when PaddleOCR does not provide a confidence score
    DEFAULT_CONFIDENCE = 0.5

    def __init__(self, allowed_chars: str | None = None) -> None:
        """Initialize PaddleOCR with settings optimized for license/hazard plates."""
        try:
            import paddle
            device = (
                'gpu'
                if paddle.device.is_compiled_with_cuda()
                and paddle.device.cuda.device_count() > 0
                else 'cpu'
            )
            logger.info(f"PaddleOCR device selected: {device}")

            self.paddle_ocr = PaddleOCR(
                text_detection_model_name='PP-OCRv5_server_det',
                text_recognition_model_name='PP-OCRv5_server_rec',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_rec_score_thresh=0.5,
                device=device,
            )
            
        except Exception as e:
            logger.critical(f"Failed to initialize PaddleOCR model: {e}")
            raise RuntimeError("PaddleOCR model could not be loaded") from e

        self.allowed_chars = allowed_chars if allowed_chars else 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'
        
        logger.info("Initialized with allowed chars: " + self.allowed_chars)
    
    
    def extract_text(self, cv_img: str | Image.Image | np.ndarray) -> tuple[str, float]:
        """
        Extract text from license/hazard plate crop.
        
        Args:
            cv_img: OpenCV image of cropped license/hazard plate (BGR) or path to image
            
        Returns:
            tuple: (text, confidence)
        """
        try:
            img = self._to_cv_image(cv_img)
        except TypeError:
            logger.warning(f"Unsupported image type: {type(cv_img).__name__}")
            return "", 0.0
        
        if img is None:
            logger.warning("Invalid image input")
            return "", 0.0
        
        h, w = img.shape[:2]
        logger.debug(f"Processing image of size {w}x{h}")
        
        try:
            # Preprocess the image
            processed = self._preprocess_plate(img)
            
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
            
        except ValueError as e:
            logger.warning(f"Preprocessing failed: {e}")
            return "", 0.0
        
        except RuntimeError as e:
            logger.exception("PaddleOCR inference error")
            return "", 0.0
    
    def _to_cv_image(self, image: str | Image.Image | np.ndarray) -> np.ndarray | None:
        """Convert various image formats to OpenCV BGR format.
        
        Args:
            image: Input image as file path, PIL Image, or numpy array.
            
        Returns:
            OpenCV BGR image as numpy array, or None if cv2.imread fails.
            
        Raises:
            TypeError: If the input type is not supported.
        """
        
        if isinstance(image, str):
            img = cv2.imread(image)
            if img is None:
                logger.warning(f"cv2.imread failed for path: {image}")
            return img
        
        if isinstance(image, Image.Image):
            arr = np.array(image)
            if arr.ndim == 3:
                return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            return arr
        
        if isinstance(image, np.ndarray):
            return image
        
        raise TypeError(f"Unsupported image type: {type(image).__name__}")

    def _resize_and_pad(self, img: np.ndarray, target_height: int = DEFAULT_TARGET_HEIGHT) -> np.ndarray:
        """
        Resize image to target height while maintaining aspect ratio,
        and add padding to improve OCR accuracy.
        
        Args:
            img: Input image
            target_height: Target height for resizing
            
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
        padded = cv2.copyMakeBorder(
            resized, 
            top=self.DEFAULT_PADDING, 
            bottom=self.DEFAULT_PADDING, 
            left=self.DEFAULT_PADDING, 
            right=self.DEFAULT_PADDING, 
            borderType=cv2.BORDER_REPLICATE
        )
        
        return padded

    def _preprocess_plate(self, cv_img: np.ndarray | None) -> np.ndarray:
        """
        Preprocess license/hazard plate image for OCR.
        
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
        processed = self._resize_and_pad(cv_img, target_height=self.DEFAULT_TARGET_HEIGHT)

        # Convert to grayscale
        if len(processed.shape) == 3:
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        else:
            gray = processed

        # Convert back to BGR for PaddleOCR
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    def _filter_text(self, text: str) -> str:
        """Filter and clean OCR output to only allowed characters."""
        
        if not text:
            return ""
        
        text = text.upper()
        
        # Filter to allowed characters only
        filtered = ''.join(c for c in text if c in self.allowed_chars)
        
        return filtered.strip().strip('-')

    def _parse_dict_item(self, item: dict, texts: list[str], confidences: list[float]) -> None:
        """Parse dictionary format item (new PaddleOCR)."""
        
        if 'rec_texts' in item and 'rec_scores' in item:
            texts.extend(item['rec_texts'])
            confidences.extend(item['rec_scores'])
        
        elif 'text' in item and 'score' in item:
            texts.append(item['text'])
            confidences.append(item['score'])

    def _parse_list_item(self, item: list | tuple, texts: list[str], confidences: list[float]) -> None:
        """Parse list/tuple format item (old PaddleOCR)."""
        
        if len(item) < 2:
            logger.debug(f"Skipping malformed list item with length {len(item)}")
            return
        text_data = item[-1]  # Last element is (text, conf)
        
        if isinstance(text_data, (list, tuple)) and len(text_data) >= 2:
            texts.append(str(text_data[0]))
            confidences.append(float(text_data[1]))
        
        elif isinstance(text_data, str):
            texts.append(text_data)
            confidences.append(self.DEFAULT_CONFIDENCE)

    def _parse_result(self, result: list) -> tuple[str, float]:
        """
        Parse PaddleOCR result and extract text and confidence.
        
        Args:
            result: PaddleOCR prediction result
            
        Returns:
            tuple: (text, confidence)
        """
        if not result or not isinstance(result, list):
            return "", 0.0
        
        texts: list[str] = []
        confidences: list[float] = []
        
        try:
            for item in result:
                if isinstance(item, dict):
                    self._parse_dict_item(item, texts, confidences)
                
                elif isinstance(item, (list, tuple)):
                    self._parse_list_item(item, texts, confidences)
                    
        except (TypeError, KeyError, IndexError) as e:
            logger.warning(f"Error parsing OCR result structure: {e}")
            return "", 0.0
        
        if not texts:
            return "", 0.0
        
        full_text = " ".join(str(t) for t in texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else self.DEFAULT_CONFIDENCE
        
        return full_text, avg_confidence
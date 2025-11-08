from PIL import Image # type: ignore
import pytesseract # type: ignore
import numpy as np # type: ignore
import cv2 # type: ignore
import os
import warnings
import sys
import contextlib
from io import StringIO

# Suppress BEFORE importing PaddleOCR
os.environ['GLOG_minloglevel'] = '3'
os.environ['FLAGS_print_model_net_proto'] = '0'
warnings.filterwarnings('ignore', category=UserWarning, module='paddle')

import logging
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddle").setLevel(logging.ERROR)
logging.getLogger("paddleocr").setLevel(logging.ERROR)
logging.getLogger("paddlex").setLevel(logging.ERROR)

logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("ppocr_utils").setLevel(logging.ERROR)

try:
    silent = StringIO()
    with contextlib.redirect_stdout(silent), contextlib.redirect_stderr(silent):
        from paddleocr import PaddleOCR  # type: ignore
        #import paddle
    PADDLE_AVAILABLE = True
except Exception as e:
    print(f"[OCR] WARNING: PaddleOCR import failed: {e}")
    PaddleOCR = None
    paddle = None
    PADDLE_AVAILABLE = False


# Initialize logger
logger = logging.getLogger("OCR")


class OCR:
    def __init__(self, engine='paddle', min_confidence=0.3, lang='en'):
        logger.info(f"[OCR.__init__] Initializing OCR with engine='{engine}'")
        logger.info(f"[OCR.__init__] PaddleOCR available: {PADDLE_AVAILABLE}")
        
        self.engine = engine
        self.min_confidence = float(min_confidence)
        self.lang = lang
        self.ocr = None

        if engine == 'paddle' and PaddleOCR is not None:
            logger.info("[OCR.__init__] Attempting to initialize PaddleOCR...")
            try:
                self.ocr = PaddleOCR(
                    lang=lang,
                    use_angle_cls=True,
                )
                logger.info("[OCR.__init__] ✓ PaddleOCR initialized successfully!")
            except Exception as e:
                logger.error(f"[OCR.__init__] ✗ Failed to initialize PaddleOCR: {e}")
                logger.exception(e)
                self.ocr = None
        else:
            if engine == 'paddle':
                logger.warning("[OCR.__init__] PaddleOCR requested but not available, falling back to Tesseract")
            else:
                logger.info(f"[OCR.__init__] Using Tesseract (engine={engine})")

        logger.info(f"[OCR.__init__] Final state: self.ocr is {'set' if self.ocr else 'None'}")

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

    def _parse_paddle_results(self, ocr_results):
        if not ocr_results:
            logger.warning("PaddleOCR returned empty results")
            return "", 0.0

        result = ""
        conf_total = 0.0
        count = 0
        cumulative_conf = 0.0

        # Sometimes PaddleOCR returns list of dicts (newer versions)
        if isinstance(ocr_results[0], dict):
            best_text, best_conf = "", 0.0
            for res in ocr_results:
                texts = res.get("rec_texts", [])
                scores = res.get("rec_scores", [])
                for text, conf in zip(texts, scores):
                    logger.debug(f"→ Found text '{text}' with conf {conf:.2f}")
                    count += 1
                    conf_total += conf
                    cumulative_conf = conf_total / count if count > 0 else 0.0
                    if cumulative_conf < self.min_confidence:
                        return "", 0.0
                    else:
                        result += text + " "

            filtered = "".join(ch for ch in result if ch.isalnum() or ch == '-')
            return filtered, cumulative_conf

        return "", 0.0


    def _run_paddle(self, cv_img):
        pre = self._preprocess_plate(cv_img)
        try:
            # call without passing cls; angle classifier was enabled at init
            ocr_results = self.ocr.ocr(pre) # type: ignore
        except Exception as e:
            logger.error(f"PaddleOCR execution error: {e}")
            return "", 0.0
        return self._parse_paddle_results(ocr_results)

    def _run_tesseract(self, image):
        if isinstance(image, str):
            pil = Image.open(image)
        elif isinstance(image, np.ndarray):
            arr = image
            if arr.ndim == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(arr)
        elif isinstance(image, Image.Image):
            pil = image
        else:
            return "", 0.0

        try:
            # whitelist A-Z0-9 and use single-line PSM
            text = pytesseract.image_to_string(
                pil,
                config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            )
        except Exception:
            text = ""
        return text.strip(), 0.0

    def extract_text(self, image):
        logger.debug(f"[OCR.extract_text] Starting extraction (engine={self.engine}, ocr={'set' if self.ocr else 'None'})")
        cv_img = self._to_cv_image(image)

        if self.engine == 'paddle' and self.ocr is not None and cv_img is not None:
            logger.info("[OCR.extract_text] Using PaddleOCR engine (license plate optimized)")
            text, conf = self._run_paddle(cv_img)
            if text:
                logger.info(f"[OCR.extract_text] PaddleOCR detected: '{text}' (confidence={conf:.2f})")
                return text, conf
            else:
                logger.warning("[OCR.extract_text] PaddleOCR returned empty result, falling back to Tesseract")
            
        logger.info("[OCR.extract_text] Using Tesseract OCR engine")
        text, conf = self._run_tesseract(image)
        logger.info(f"[OCR.extract_text] Tesseract result: '{text}'")
        return text, conf

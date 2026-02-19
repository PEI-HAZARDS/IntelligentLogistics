from ultralytics import YOLO # type: ignore
import numpy as np
import os
import logging
logging.getLogger('ultralytics').setLevel(logging.WARNING)

logger = logging.getLogger("ObjectDetector")

class ObjectDetector:
    """Wrapper around Ultralytics YOLO for object detection."""

    def __init__(self, model_path: str, class_id: int = -1):
        """Initialize the detector with a YOLO model.

        Args:
            model_path: Path to the YOLO model weights file.
            class_id: YOLO class ID to filter detections. -1 means no filter.

        Raises:
            FileNotFoundError: If the model file does not exist.
            RuntimeError: If the model fails to load.
        """
        if not os.path.isfile(model_path):
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        self.model_path = model_path
        
        try:
            self.model = YOLO(self.model_path)
        except Exception as e:
            raise RuntimeError(f"Failed to load YOLO model from '{model_path}': {e}") from e
        
        self.class_id = class_id

    def detect(self, image: np.ndarray, suppress_output: bool = True) -> list:
        """Run YOLO inference on an image.

        Args:
            image: Input image as a NumPy array (HWC, BGR).
            suppress_output: If True, suppresses YOLO console output.

        Returns:
            List of YOLO result objects.

        Raises:
            ValueError: If image is None.
        """
        if image is None:
            raise ValueError("Cannot run detection on None image")

        kwargs: dict = {"verbose": not suppress_output}
        if self.class_id >= 0:
            kwargs["classes"] = [self.class_id]

        return self.model(image, **kwargs)

    def get_boxes(self, results: list) -> list[list[float]]:
        """Extract bounding boxes and confidence scores from results.

        Args:
            results: YOLO results list from detect().

        Returns:
            List of [x1, y1, x2, y2, confidence] lists with plain floats.
        """
        if not results or not results[0].boxes:
            return []
        
        boxes = []
        for r in results[0].boxes:
            x1, y1, x2, y2 = r.xyxy[0].tolist()
            conf = float(r.conf[0])
            boxes.append([x1, y1, x2, y2, conf])
            
        return boxes

    def object_found(self, results: list) -> bool:
        """Check whether any objects were detected.

        Args:
            results: YOLO results list from detect().

        Returns:
            True if at least one bounding box was found.
        """
        if not results:
            return False
        
        return len(results[0].boxes) > 0

    def close(self) -> None:
        """Release model resources."""
        self.model.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
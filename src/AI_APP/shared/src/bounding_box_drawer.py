import logging
import cv2 # type: ignore
import numpy as np # type: ignore
from typing import List, Tuple, Union

logger = logging.getLogger("BoundingBoxDrawer")

# A box is either (x1, y1, x2, y2) or (x1, y1, x2, y2, confidence)
Box = Union[
    Tuple[float, float, float, float],
    Tuple[float, float, float, float, float],
]

class BoundingBoxDrawer:
    """Draws bounding boxes and labels on images using OpenCV."""

    # BGR color lookup for common color names
    _COLOR_MAP = {
        "red": (0, 0, 255),
        "orange": (0, 165, 255),
        "green": (0, 255, 0),
        "blue": (255, 0, 0),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "yellow": (0, 255, 255),
    }

    # Sum of BGR channels; below this threshold -> white text, above -> black text
    _DARK_BG_THRESHOLD = 400

    def __init__(self, color: str = "black", thickness: int = 1, label: str = ""):
        """Initialize the drawer.

        Args:
            color: Color name for boxes (e.g. 'red', 'green'). Falls back to black if unknown.
            thickness: Line thickness in pixels. Must be >= 1.
            label: Optional label text to draw alongside each box.

        Raises:
            ValueError: If thickness < 1.
        """
        if thickness < 1:
            raise ValueError(f"thickness must be >= 1, got {thickness}")

        if color.lower() not in self._COLOR_MAP:
            logger.warning(f"Unknown color '{color}', defaulting to black")
            color = "black"

        self.color = color
        self.thickness = thickness
        self.label = label

    def _bgr(self) -> Tuple[int, int, int]:
        """Return the BGR tuple for the configured color."""
        return self._COLOR_MAP.get(self.color.lower(), (0, 0, 0))

    def draw_box(self, frame: np.ndarray, boxes: List[Box]) -> np.ndarray:
        """Draw boxes (and optional labels) on an image.

        Args:
            frame: The image (numpy array, HWC, BGR) to draw on.
            boxes: List of bounding boxes. Each box is either
                   (x1, y1, x2, y2) or (x1, y1, x2, y2, confidence).

        Returns:
            The same frame with drawings applied (modified in-place).
        """
        logger.debug(f"Drawing {len(boxes)} boxes with color {self.color} and thickness {self.thickness}")

        color = self._bgr()
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.5
        text_thickness = max(1, int(self.thickness / 2))

        for i, box in enumerate(boxes):
            try:
                # Skip invalid entries early
                if len(box) < 4:
                    continue

                x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
                # Convert to ints for drawing
                x1_i, y1_i, x2_i, y2_i = map(int, (x1, y1, x2, y2))

                # Draw rectangle
                cv2.rectangle(frame, (x1_i, y1_i), (x2_i, y2_i), color, self.thickness)

                # Build label text (include confidence when available)
                conf = box[4] if len(box) >= 5 and isinstance(box[4], (float, int)) else None
                label_text = (self.label or "") + (f" {conf:.2f}" if conf is not None else "")

                if label_text:
                    self._draw_label(frame, x1_i, y1_i, label_text, color, font, font_scale, text_thickness)

            except Exception as e:
                logger.warning(f"Skipping box {i}: {e}")
                continue

        return frame

    def _draw_label(
        self,
        frame: np.ndarray,
        x1_i: int,
        y1_i: int,
        label_text: str,
        color: Tuple[int, int, int],
        font: int = cv2.FONT_HERSHEY_SIMPLEX,
        font_scale: float = 0.5,
        text_thickness: int = 1,
    ) -> None:
        """Draw a label background rectangle and text for a single box.

        The label is placed above the box by default. If there is not enough
        room at the top of the image it is placed below instead.  Horizontal
        position is clamped so the label does not overflow the right edge.

        Args:
            frame: Image array to draw on (modified in-place).
            x1_i: Left x-coordinate of the bounding box (int pixels).
            y1_i: Top y-coordinate of the bounding box (int pixels).
            label_text: Text string to render.
            color: BGR background color for the label rectangle.
            font: OpenCV font constant.
            font_scale: Font scale factor.
            text_thickness: Thickness of the rendered text.
        """
        logger.debug(f"Drawing label '{label_text}' at ({x1_i}, {y1_i})")

        (tw, th), _ = cv2.getTextSize(label_text, font, font_scale, text_thickness)

        # Image dimensions
        try:
            img_h, img_w = frame.shape[:2]
            
        except AttributeError:
            logger.warning("Frame has no 'shape' attribute — skipping bounds checks")
            img_h, img_w = None, None

        pad = 6
        bg_w = tw + pad
        bg_h = th + pad

        # X: prefer aligned with box left, but shift left if it would overflow image
        x_tl = x1_i
        if img_w is not None and x_tl + bg_w > img_w:
            x_tl = max(0, img_w - bg_w)

        # Y: prefer placing above the box; if not enough room, place below
        y_bg_tl = y1_i - bg_h
        y_bg_br = y1_i
        if img_h is not None and y_bg_tl < 0:
            # Place below box
            y_bg_tl = y1_i
            y_bg_br = min(img_h, y1_i + bg_h)

        text_bg_tl = (int(x_tl), int(max(0, y_bg_tl)))
        text_bg_br = (int(x_tl + bg_w), int(max(0, y_bg_br)))

        cv2.rectangle(frame, text_bg_tl, text_bg_br, color, -1)

        # Compute text baseline position inside the background rectangle
        text_x = int(x_tl + 3)
        text_y = int(text_bg_br[1] - 4)
        if img_h is not None:
            text_y = max(text_y, th)  # make sure text baseline is visible

        text_color = (255, 255, 255) if sum(color) < self._DARK_BG_THRESHOLD else (0, 0, 0)
        cv2.putText(frame, label_text, (text_x, text_y), font, font_scale, text_color, text_thickness, cv2.LINE_AA)
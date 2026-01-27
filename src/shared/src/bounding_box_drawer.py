from logging import getLogger
import cv2
from typing import List, Tuple, Any


class BoundingBoxDrawer:
    def __init__(self, color: str = "black", thickness: int = 1, label: str = ""):
        self.color = color
        self.thickness = thickness
        self.label = label
        self.logger = getLogger("BoundingBoxDrawer")

        # Map simple color names to BGR tuples for OpenCV
        self._color_map = {
            "red": (0, 0, 255),
            "orange": (0, 165, 255),
            "green": (0, 255, 0),
            "blue": (255, 0, 0),
            "white": (255, 255, 255),
            "black": (0, 0, 0),
            "yellow": (0, 255, 255),
        }

    def _bgr(self):
        return self._color_map.get(self.color.lower(), (0, 0, 0))

    def draw_box(self, frame: Any, boxes: List[Tuple[float, float, float, float, float]]):
        """
        Draw boxes (and labels) on the provided image/frame using OpenCV.

        Parameters:
        - frame: The image/frame (numpy array) to draw on
        - boxes: Iterable of boxes. Each box can be either:
            - (x1, y1, x2, y2)
            - (x1, y1, x2, y2, conf)

        Returns:
        - The same frame object with drawings applied.
        """

        self.logger.debug(f"Drawing {len(boxes)} boxes with color {self.color} and thickness {self.thickness}") 

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

            except Exception:
                # If drawing fails for a box, skip it but continue drawing others
                continue

        # Return the modified frame so callers receive the updated image
        return frame

    def _draw_label(self, frame: Any, x1_i: int, y1_i: int, label_text: str, color: Tuple[int, int, int], font: int = cv2.FONT_HERSHEY_SIMPLEX, font_scale: float = 0.5, text_thickness: int = 1):
        """Draw label background and text for a single box."""

        self.logger.debug(f"Drawing label '{label_text}' at ({x1_i}, {y1_i})")

        (tw, th), _ = cv2.getTextSize(label_text, font, font_scale, text_thickness)

        # Image dimensions
        try:
            img_h, img_w = frame.shape[:2]
        except Exception:
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

        text_color = (255, 255, 255) if sum(color) < 400 else (0, 0, 0)
        cv2.putText(frame, label_text, (text_x, text_y), font, font_scale, text_color, text_thickness, cv2.LINE_AA)

        return frame